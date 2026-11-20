"""ชั้นเก็บข้อมูลดิบของ WearWise

รองรับ 3 โหมด เลือกอัตโนมัติตามค่าใน .env
  1. Google Sheets ผ่าน Apps Script Web App (GOOGLE_SCRIPT_URL)
  2. Google Sheets ผ่าน service account (GOOGLE_SHEET_ID + ไฟล์ JSON)
  3. SQLite ในเครื่อง (cloud.db) เมื่อยังไม่ตั้งค่าใด ๆ

โหมดที่ใช้ชีตจริงจะเขียนสำเนาลง SQLite ด้วย (mirror) และอ่านชีตในเธรดแยก
dashboard จึงไม่ต้องรอ Apps Script (ซึ่งใช้เวลา 2-5 วินาทีต่อครั้ง)
"""
import json
import queue
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

import config

RAW_COLS = ["ts", "iso", "node_id", "seq", "temp", "hum", "gas", "lux",
            "dist_cm", "person", "fan", "servo", "estop", "hop_ms", "note"]
EVENT_COLS = ["ts", "iso", "node_id", "kind", "text", "notify"]

BASE = Path(__file__).parent
# ใช้ไฟล์เดียวกับ app.py เพื่อให้ยอด uses กับแถวดิบอยู่ในฐานข้อมูลเดียวกัน
# (ตอนรันใน Docker ตั้ง WEARWISE_DB=/data/cloud.db ซึ่งเป็น volume ที่ไม่หาย)
LOCAL_DB = Path(config.env("WEARWISE_DB", str(BASE / "cloud.db")))
READ_TTL_S = float(config.env("CLOUD_READ_TTL_S", "8"))
HTTP_TIMEOUT_S = float(config.env("CLOUD_TIMEOUT_S", "20"))


def _num(v):
    """Sheets/SQLite คืนค่ามาเป็นข้อความ แปลงกลับเป็นตัวเลข"""
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    if s == "":
        return ""
    try:
        return float(s) if ("." in s or "e" in s.lower()) else int(s)
    except ValueError:
        return s


def _stamp(row, cols):
    row = {c: row.get(c, "") for c in cols}
    ts = row.get("ts")
    try:
        row["ts"] = float(ts) if ts not in ("", None) else time.time()
    except (TypeError, ValueError):
        row["ts"] = time.time()
    if not row.get("iso"):
        row["iso"] = datetime.fromtimestamp(row["ts"]).isoformat(timespec="seconds")
    return row


class _LocalTable:
    """โหมดสำรอง: ตาราง SQLite ที่ทำหน้าที่แทนชีต"""

    def __init__(self, name, cols):
        self.name, self.cols = name, cols
        self.detail = str(LOCAL_DB)
        with closing(sqlite3.connect(LOCAL_DB, timeout=10)) as con, con:
            con.execute("CREATE TABLE IF NOT EXISTS %s (%s)" % (
                name, ", ".join("%s NUMERIC" % c for c in cols)))

    def append(self, row):
        values = [row.get(c, "") for c in self.cols]
        with closing(sqlite3.connect(LOCAL_DB, timeout=10)) as con, con:
            con.execute("INSERT INTO %s (%s) VALUES (%s)" % (
                self.name, ", ".join(self.cols), ", ".join("?" * len(self.cols))), values)

    def rows(self, limit=50):
        with closing(sqlite3.connect(LOCAL_DB, timeout=10)) as con:
            con.row_factory = sqlite3.Row
            cur = con.execute("SELECT * FROM %s ORDER BY rowid DESC LIMIT ?" % self.name, (limit,))
            out = [{k: ("" if r[k] is None else r[k]) for k in r.keys()} for r in cur]
        out.reverse()
        return out

    def count(self):
        with closing(sqlite3.connect(LOCAL_DB, timeout=10)) as con:
            return con.execute("SELECT COUNT(*) FROM %s" % self.name).fetchone()[0]

    def clear(self):
        with closing(sqlite3.connect(LOCAL_DB, timeout=10)) as con, con:
            con.execute("DELETE FROM %s" % self.name)


class _ScriptError(Exception):
    """สคริปต์ตอบมาแบบที่ลองซ้ำไม่ได้ (ต้องแก้การตั้งค่า/โค้ดสคริปต์)"""


class _ScriptTable:
    """แท็บ Google Sheets ผ่าน Apps Script Web App

    HTTP handler ไม่รอเน็ต: เขียนสำเนาลง SQLite ก่อนแล้วตอบกลับทันที
    การเขียนชีตทำในเธรดเบื้องหลังทีละแถว (Apps Script ช้าและมี quota)
    """

    def __init__(self, url, name, cols):
        self.url, self.name, self.cols = url, name, cols
        self.mirror = _LocalTable("mirror_" + name, cols)
        self.detail = "Apps Script web app"
        self.failures = 0
        self.sent = 0
        self.pending = 0
        self.last_error = ""
        self._cache = []
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._refresh, daemon=True).start()

    def append(self, row):
        self.mirror.append(row)
        self._queue.put(row)
        self.pending = self._queue.qsize()

    def _worker(self):
        while True:
            row = self._queue.get()
            last = None
            for _ in range(3):
                try:
                    self._post(row)
                    self.sent += 1
                    self.last_error = ""
                    break
                except _ScriptError as e:
                    self.failures += 1
                    self.last_error = str(e)
                    break
                except Exception as e:
                    last = e
                    time.sleep(1.5)
            else:
                self.failures += 1
                self.last_error = str(last)
            if self.last_error and self.failures % 10 == 1:
                print("[cloud] ส่งขึ้น Apps Script ไม่สำเร็จ (%d ครั้ง): %s" % (
                    self.failures, self.last_error))
            self.pending = self._queue.qsize()

    def _post(self, row):
        import requests
        r = requests.post(self.url, json={"table": self.name, "row": row},
                          timeout=HTTP_TIMEOUT_S)
        r.raise_for_status()
        try:
            payload = r.json()
        except ValueError:
            raise _ScriptError(
                "สคริปต์ตอบกลับไม่ใช่ JSON — ตรวจว่า Deploy เป็น Web app และ Who has access = Anyone")
        if not isinstance(payload, dict) or not payload.get("ok"):
            raise _ScriptError("สคริปต์ตอบ ok=false: %s" % (
                payload.get("error") if isinstance(payload, dict) else payload))

    def rows(self, limit=50):
        """อ่านจากแคชของชีต (รีเฟรชเบื้องหลัง) รวมกับสำเนาที่อาจยังไม่ขึ้นชีต"""
        with self._lock:
            sheet = list(self._cache)
        local = self.mirror.rows(max(limit, 200))
        if not sheet:
            return local[-limit:]
        seen = {(str(r.get("node_id")), str(r.get("seq")), str(r.get("ts"))) for r in sheet}
        merged = sheet + [r for r in local
                          if (str(r.get("node_id")), str(r.get("seq")), str(r.get("ts"))) not in seen]
        merged.sort(key=lambda r: float(r.get("ts") or 0))
        return merged[-limit:]

    def _refresh(self):
        while True:
            fetched = self._fetch(200)
            if fetched:
                with self._lock:
                    self._cache = fetched
            time.sleep(READ_TTL_S)

    def _fetch(self, limit):
        try:
            import requests
            r = requests.get(self.url, params={"table": self.name, "limit": max(limit, 200)},
                             timeout=HTTP_TIMEOUT_S)
            r.raise_for_status()
            payload = r.json()
            rows = payload.get("rows") if isinstance(payload, dict) else payload
            if not isinstance(rows, list):
                return None
            return [{c: _num(row.get(c, "")) for c in self.cols} for row in rows]
        except Exception:
            return None  # อ่านจากชีตไม่ได้ ใช้สำเนาในเครื่องแทน

    def count(self):
        return len(self.rows(limit=1000))

    def clear(self):
        self.mirror.clear()


class _SheetTable:
    """แท็บจริงใน Google Sheets ผ่าน service account"""

    def __init__(self, sh, name, cols):
        import gspread
        self.cols = cols
        self.detail = sh.id
        try:
            self.ws = sh.worksheet(name)
        except gspread.WorksheetNotFound:
            self.ws = sh.add_worksheet(title=name, rows=2000, cols=max(len(cols), 12))
        if self.ws.row_values(1)[:len(cols)] != cols:
            self.ws.update(values=[cols], range_name="A1")
        self._cache = (0.0, [])

    def append(self, row):
        self.ws.append_row([row.get(c, "") for c in self.cols], value_input_option="USER_ENTERED")
        self._cache = (0.0, [])

    def rows(self, limit=50):
        t, data = self._cache
        if time.time() - t > READ_TTL_S:
            values = self.ws.get_all_values()
            header = values[0] if values else self.cols
            data = [dict(zip(header, r)) for r in values[1:] if any(r)]
            self._cache = (time.time(), data)
        return [{k: _num(v) for k, v in r.items()} for r in data[-limit:]]

    def count(self):
        return len(self.rows(limit=10 ** 6))

    def clear(self):
        if self.ws.row_count > 1:
            self.ws.delete_rows(2, self.ws.row_count)


class Store:
    def __init__(self):
        self.kind, self.detail, self.error = "local", str(LOCAL_DB), ""
        choice = config.env("CLOUD_BACKEND", "auto").lower()
        script_url = config.env("GOOGLE_SCRIPT_URL") or config.env("GOOGLE_SHEETS_WEBAPP_URL")

        if choice in ("auto", "script") and script_url:
            self.raw = _ScriptTable(script_url, "raw", RAW_COLS)
            self.events = _ScriptTable(script_url, "events", EVENT_COLS)
            self.kind, self.detail = "script", "Google Sheets ผ่าน Apps Script"
            return
        if choice == "script":
            raise RuntimeError("CLOUD_BACKEND=script แต่ยังไม่ได้ตั้ง GOOGLE_SCRIPT_URL")

        if choice in ("auto", "sheets"):
            # ไม่พยายามต่อ service account เลยถ้ายังไม่ได้ตั้งค่า (กัน error รบกวน dashboard)
            configured = bool(config.env("GOOGLE_SHEET_ID") or
                              config.env("GOOGLE_SERVICE_ACCOUNT_JSON"))
            if choice == "sheets" or configured:
                try:
                    self._use_service_account()
                    self.kind = "sheets"
                    return
                except Exception as e:
                    self.error = "%s: %s" % (type(e).__name__, e)
                    if choice == "sheets":
                        raise

        self.raw = _LocalTable("raw", RAW_COLS)
        self.events = _LocalTable("event", EVENT_COLS)
        self.detail = self.raw.detail

    def _use_service_account(self):
        import gspread
        from google.oauth2.service_account import Credentials

        sheet_id = config.env("GOOGLE_SHEET_ID")
        if not sheet_id:
            raise RuntimeError("ยังไม่ได้ตั้ง GOOGLE_SHEET_ID ใน .env")

        raw_json = config.env("GOOGLE_SERVICE_ACCOUNT_JSON")
        if raw_json:
            info = json.loads(raw_json)
        else:
            path = Path(config.env("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json"))
            if not path.is_absolute():
                path = BASE / path
            if not path.exists():
                raise FileNotFoundError(str(path))
            info = json.loads(path.read_text(encoding="utf-8"))

        creds = Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        sh = gspread.authorize(creds).open_by_key(sheet_id)
        self.raw = _SheetTable(sh, config.env("GOOGLE_SHEET_TAB", "raw"), RAW_COLS)
        self.events = _SheetTable(sh, config.env("GOOGLE_SHEET_EVENTS_TAB", "events"), EVENT_COLS)
        self.detail = sheet_id

    def append_row(self, row):
        self.raw.append(_stamp(row, RAW_COLS))

    def append_event(self, row):
        self.events.append(_stamp(row, EVENT_COLS))

    def info(self):
        backend = {"script": "Google Sheets (Apps Script)",
                   "sheets": "Google Sheets (service account)"}.get(
                       self.kind, "SQLite (สำรองในเครื่อง)")
        error = self.error
        if self.kind == "script" and getattr(self.raw, "failures", 0):
            note = "ส่งขึ้น Apps Script ไม่สำเร็จ %d ครั้ง" % self.raw.failures
            if getattr(self.raw, "last_error", ""):
                note += ": " + self.raw.last_error
            note += " (กำลังแสดงข้อมูลจากสำเนาในเครื่อง)"
            error = (error + " · " if error else "") + note
        return {"backend": backend, "detail": self.detail, "error": error,
                "rows": self.raw.count(),
                "pending": getattr(self.raw, "pending", 0),
                "sent": getattr(self.raw, "sent", 0)}

    def reset(self):
        """ล้างข้อมูลได้เฉพาะโหมดสำรอง (ชีตจริงต้องลบแถวเองใน Google Sheets)"""
        if self.kind in ("local", "script"):
            self.raw.clear()
            self.events.clear()
            return self.kind == "local"
        return False
