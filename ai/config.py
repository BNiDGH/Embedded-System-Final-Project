"""ค่าตั้งของ AI service (อ่าน .env ในโฟลเดอร์ ai/)"""
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


# auto = ใช้ YOLO ถ้าติดตั้ง ultralytics ไว้ / ไม่มีใช้ OpenCV HOG
AI_BACKEND = env("AI_BACKEND", "auto").lower()
AI_MODEL = env("AI_MODEL", "yolov8n.pt")
AI_CONF = float(env("AI_CONF", "0.35"))

# auto = ใช้ torchvision ถ้าติดตั้งไว้ / color = ใช้สี+สัดส่วนภาพอย่างเดียว
AI_CLASSIFIER = env("AI_CLASSIFIER", "auto").lower()
AI_DEVICE = env("AI_DEVICE", "cpu")

# token ที่ gateway แนบมาใน header X-Auth-Token (เว้นว่าง = ไม่ตรวจ)
INGEST_TOKEN = env("INGEST_TOKEN", "")

MAX_IMAGE_BYTES = int(env("MAX_IMAGE_BYTES", str(3 * 1024 * 1024)))
