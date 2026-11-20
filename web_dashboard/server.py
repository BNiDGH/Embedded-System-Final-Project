"""WearWise dashboard server

dashboard เป็นชั้นอ่านข้อมูลเท่านั้น: ดึง /api/state จาก cloud แล้วแสดงผล
คำสั่งหยุดฉุกเฉินถูกส่งต่อไป cloud ซึ่งส่งต่อไป gateway อีกทอด

รัน:  uvicorn server:app --host 0.0.0.0 --port 8080
แล้วเปิด http://127.0.0.1:8080
"""
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config

BASE = Path(__file__).parent
STATIC = BASE / "static"

app = FastAPI(title="WearWise dashboard")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class Estop(BaseModel):
    on: bool = True


def _headers():
    return {"X-Auth-Token": config.UPLINK_TOKEN} if config.UPLINK_TOKEN else {}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    """ข้อมูลจาก cloud + สถานะ AI (ถ้า AI ไม่ตอบ ยังแสดง dashboard ได้)"""
    try:
        r = requests.get("%s/api/state" % config.CLOUD_URL, timeout=config.HTTP_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": "cloud ตอบไม่ได้: %s" % e}

    try:
        ai = requests.get("%s/health" % config.AI_URL, timeout=1.5).json()
    except Exception:
        ai = {"ok": False, "error": "AI service ไม่ตอบ"}

    data["ok"] = True
    data["ai"] = ai
    return data


@app.post("/api/estop")
def estop(e: Estop):
    try:
        r = requests.post("%s/api/estop" % config.CLOUD_URL, json={"on": e.on},
                          headers=_headers(), timeout=config.HTTP_TIMEOUT_S)
        r.raise_for_status()
        return r.json()
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


@app.post("/api/reset")
def reset():
    try:
        r = requests.post("%s/api/reset" % config.CLOUD_URL,
                          headers=_headers(), timeout=config.HTTP_TIMEOUT_S)
        r.raise_for_status()
        return r.json()
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


@app.get("/health")
def health():
    return {"ok": True, "cloud": config.CLOUD_URL, "ai": config.AI_URL}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
