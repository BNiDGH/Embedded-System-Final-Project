"""ค่าตั้งกลางของ cloud service

อ่าน .env ในโฟลเดอร์ cloud/ (ค่าที่ตั้งใน environment จริงมีสิทธิ์เหนือไฟล์)
"""
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


# ที่อยู่ gateway จริง (ESP32 เปิด WebServer พอร์ต 80)
GATEWAY_URL = env("GATEWAY_URL", "http://192.168.1.60:80")

# token ที่ gateway ต้องแนบมาใน header X-Auth-Token (เว้นว่าง = ไม่ตรวจ)
INGEST_TOKEN = env("INGEST_TOKEN", "")

# dashboard ถือว่าอุปกรณ์ออนไลน์ถ้าข้อมูลใหม่กว่านี้
ONLINE_WINDOW_S = int(env("ONLINE_WINDOW_S", "15"))

# กันนับ "หยิบ 1 ครั้ง" ซ้ำตอนมีคนยืนหน้าตู้หลายวินาที
PICK_COOLDOWN_S = float(env("PICK_COOLDOWN_S", "5"))

# ชนิดเหตุการณ์ที่ส่งแจ้งเตือน (คั่นด้วย ,)
NOTIFY_KINDS = {k.strip() for k in env("NOTIFY_KINDS", "humidity,gas,estop,fan").split(",") if k.strip()}

# บอร์ดและเซนเซอร์ตามแผนแยกบอร์ด (M1: node 3 ชนิด, gateway 2 ชนิด)
SENSOR_MAP = {
    "NA709": {"role": "sensor", "board": "ESP32", "sensors": ["DHT22", "MQ-135", "BH1750"]},
    "NA710": {"role": "sensor", "board": "ESP32", "sensors": ["DHT22", "MQ-135", "BH1750"]},
    "CB302": {"role": "gateway", "board": "ESP32-S3", "sensors": ["OV7670", "HC-SR04"]},
}
SENSOR_TYPES = 5  # OV7670, HC-SR04, DHT22, MQ-135, BH1750

# ชื่อเสื้อผ้าต้องตรงกับที่ ai/ ส่งมา (ai/garment.py ใช้รายการเดียวกัน)
WARDROBE = [
    ("เสื้อยืดสีขาว", "เสื้อ"),
    ("เสื้อเชิ้ตสีเบจ", "เสื้อ"),
    ("กางเกงยีนส์สีน้ำเงิน", "กางเกง"),
    ("กางเกงขาสั้นสีกรมท่า", "กางเกง"),
    ("กระโปรงสีดำ", "กระโปรง"),
    ("กระโปรงพลีทสีเทา", "กระโปรง"),
]
