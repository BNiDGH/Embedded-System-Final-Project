"""WearWise cloud service

  POST /cloud/rows     รับข้อมูลดิบจาก gateway (ทีละแถวหรือ {"rows":[...]})
  POST /cloud/events   รับเหตุการณ์ แล้วส่งแจ้งเตือน Discord
  POST /api/pick       นับ "หยิบเสื้อ 1 ครั้ง" จากผล AI (มี cooldown)
  GET  /api/state      ข้อมูลรวมสำหรับ dashboard
  POST /api/estop      ส่งคำสั่งหยุดฉุกเฉินต่อไปที่ gateway
  POST /api/reset      ล้างจำนวนครั้งที่ใช้ (และแถวในโหมด SQLite)

รัน:  uvicorn app:app --host 0.0.0.0 --port 8000
"""
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

import config
import notify
from store import Store

BASE = Path(__file__).parent
DB_PATH = os.environ.get("WEARWISE_DB", str(BASE / "cloud.db"))

app = FastAPI(title="WearWise cloud")
store = Store()


def db():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with closing(db()) as con, con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS wardrobe(
            id INTEGER PRIMARY KEY, name TEXT UNIQUE, category TEXT, uses INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS pick_state(
            node_id TEXT PRIMARY KEY, ts REAL);
        """)
        if con.execute("SELECT COUNT(*) FROM wardrobe").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO wardrobe(name, category, uses) VALUES (?,?,0)",
                [(n, c) for n, c in config.WARDROBE],
            )


init_db()


def check_token(token: Optional[str]):
    """ถ้าตั้ง INGEST_TOKEN ไว้ gateway ต้องแนบ header X-Auth-Token มาให้ตรง"""
    if config.INGEST_TOKEN and token != config.INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="bad X-Auth-Token")


class Pick(BaseModel):
    node_id: str = "CB302"
    label: str


class Estop(BaseModel):
    on: bool = True


@app.get("/health")
def health():
    return {"ok": True, "cloud": store.kind}


@app.post("/cloud/rows")
def ingest_rows(payload: dict, x_auth_token: Optional[str] = Header(default=None)):
    check_token(x_auth_token)
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else [payload]
    for r in rows:
        store.append_row(r)
    return {"ok": True, "stored": len(rows), "total": store.raw.count()}


@app.post("/cloud/events")
def ingest_event(payload: dict, x_auth_token: Optional[str] = Header(default=None)):
    check_token(x_auth_token)
    kind = str(payload.get("kind") or "")
    status = notify.send(payload.get("text", "")) if kind in config.NOTIFY_KINDS else ""
    payload = dict(payload, notify=status)
    store.append_event(payload)
    return {"ok": True, "notify": status, "total": store.events.count()}


@app.post("/api/pick")
def pick(p: Pick, x_auth_token: Optional[str] = Header(default=None)):
    """นับครั้งที่หยิบ โดยนับเฉพาะเมื่อพ้น cooldown ของ node นั้น (กันนับซ้ำ)"""
    check_token(x_auth_token)
    now = time.time()
    with closing(db()) as con, con:
        row = con.execute("SELECT ts FROM pick_state WHERE node_id = ?", (p.node_id,)).fetchone()
        last = row["ts"] if row else 0.0
        item = con.execute("SELECT uses FROM wardrobe WHERE name = ?", (p.label,)).fetchone()

        if item is None:
            # AI ส่งชื่อที่ไม่อยู่ในรายการ: เก็บไว้เพื่อไม่ให้ยอดหาย
            con.execute("INSERT INTO wardrobe(name, category, uses) VALUES (?,?,0)",
                        (p.label, "อื่น ๆ"))
            item = con.execute("SELECT uses FROM wardrobe WHERE name = ?", (p.label,)).fetchone()

        counted = now - last >= config.PICK_COOLDOWN_S
        if counted:
            con.execute("UPDATE wardrobe SET uses = uses + 1 WHERE name = ?", (p.label,))
            con.execute(
                "INSERT INTO pick_state(node_id, ts) VALUES (?, ?) "
                "ON CONFLICT(node_id) DO UPDATE SET ts = excluded.ts", (p.node_id, now))
            item = con.execute("SELECT uses FROM wardrobe WHERE name = ?", (p.label,)).fetchone()

    return {"ok": True, "counted": counted, "label": p.label,
            "uses": item["uses"] if item else None}


@app.get("/api/state")
def get_state():
    now = time.time()
    rows = store.raw.rows(80)
    events = store.events.rows(30)

    latest = {}
    for r in rows:
        nid = str(r.get("node_id") or "")
        if nid:
            latest[nid] = r  # แถวสุดท้ายของแต่ละอุปกรณ์ชนะ

    def age_of(row):
        try:
            return round(now - float(row["ts"]), 1)
        except (KeyError, TypeError, ValueError):
            return None

    ids = list(config.SENSOR_MAP)
    ids += sorted(nid for nid in latest if nid not in config.SENSOR_MAP)

    nodes = []
    for nid in ids:
        meta = config.SENSOR_MAP.get(nid, {"role": "sensor", "board": "ESP32", "sensors": []})
        row = latest.get(nid)
        age = age_of(row) if row else None
        nodes.append({
            "id": nid,
            "role": meta.get("role", "sensor"),
            "board": meta.get("board", "ESP32"),
            "sensors": meta.get("sensors", []),
            "last": row,
            "age_s": age,
            "online": age is not None and age < config.ONLINE_WINDOW_S,
        })

    gw_row = latest.get("CB302")
    gw_age = age_of(gw_row) if gw_row else None

    with closing(db()) as con:
        wardrobe = [dict(r) for r in con.execute(
            "SELECT name, category, uses FROM wardrobe ORDER BY uses DESC, name")]

    return {
        "now": now,
        "cloud": store.info(),
        "thresholds": {"hum_on": 75, "hum_off": 65, "gas_on": 450, "gas_off": 350},
        "servo": {"min": 20, "max": 160, "safe": 90},
        "sensor_types": config.SENSOR_TYPES,
        "pick_cooldown_s": config.PICK_COOLDOWN_S,
        "nodes": nodes,
        "gateway": {"online": gw_age is not None and gw_age < config.ONLINE_WINDOW_S,
                    "age_s": gw_age, "last": gw_row},
        "rows": rows[::-1][:15],
        "events": events[::-1][:15],
        "wardrobe": wardrobe,
    }


@app.post("/api/estop")
def estop(e: Estop):
    try:
        r = requests.post("%s/estop" % config.GATEWAY_URL, json={"on": e.on}, timeout=3)
        r.raise_for_status()
        return {"ok": True, **r.json()}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


@app.post("/api/reset")
def reset():
    with closing(db()) as con, con:
        con.execute("UPDATE wardrobe SET uses = 0")
        con.execute("DELETE FROM pick_state")
    cleared = store.reset()
    return {"ok": True, "cloud_cleared": cleared}


if __name__ == "__main__":
    import uvicorn
    print("cloud:", store.info())
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
