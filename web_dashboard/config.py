"""ค่าตั้งของ dashboard (อ่าน .env ในโฟลเดอร์ web_dashboard/)"""
import os
from pathlib import Path

BASE = Path(__file__).parent


def _load_env():
    f = BASE / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not os.environ.get(key):
            os.environ[key] = value.strip().strip('"').strip("'")


_load_env()


def env(key, default=None):
    v = os.environ.get(key)
    return default if v is None or v == "" else v


CLOUD_URL = env("CLOUD_URL", "http://127.0.0.1:8000")
AI_URL = env("AI_URL", "http://127.0.0.1:8001")

# ใช้ 127.0.0.1 ไม่ใช้ localhost: บางเครื่องบน Windows แปลง localhost ช้า
HTTP_TIMEOUT_S = float(env("DASHBOARD_TIMEOUT_S", "5"))
UPLINK_TOKEN = env("INGEST_TOKEN", "")  # ส่งต่อให้ cloud เมื่อ cloud เปิดตรวจ token
