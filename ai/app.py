"""WearWise vision service

  POST /ai/aim   รับภาพ JPEG/PNG (base64) คืนผลตรวจคน + ชนิดเสื้อผ้า + ตำแหน่ง x_norm
  GET  /health   บอกว่าใช้โมเดลอะไรอยู่

x_norm = ตำแหน่งแนวนอนของคน (0 = ซ้ายสุด, 1 = ขวาสุด)
gateway เอาไปแปลงเป็นมุม servo จึงเป็น closed loop ของ M4

รัน:  uvicorn app:app --host 0.0.0.0 --port 8001
"""
import base64
import time
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

import config
from detector import PersonDetector
from garment import GarmentClassifier

app = FastAPI(title="WearWise AI")
detector = PersonDetector()
garments = GarmentClassifier()


def check_token(token: Optional[str]):
    if config.INGEST_TOKEN and token != config.INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="bad X-Auth-Token")


class AimRequest(BaseModel):
    node_id: str = "CB302"
    image_b64: Optional[str] = None
    t_sent: Optional[float] = None
    approach: bool = False  # ใช้ฝั่ง cloud/gateway นับครั้งหยิบ ไม่มีผลกับโมเดล


def analyze(image_bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("decode ภาพไม่ได้ (ต้องเป็น JPEG/PNG)")

    dets = detector.detect(img)
    if not dets:
        return {"found": False, "label": None, "category": None,
                "confidence": 0.0, "x_norm": None}

    person = max(dets, key=lambda d: d.area)  # คนที่ใกล้/ใหญ่สุดในภาพ
    h, w = img.shape[:2]
    x_norm = round(min(1.0, max(0.0, (person.x1 + person.x2) / 2.0 / w)), 3)

    garment = garments.classify(img, (person.x1, person.y1, person.x2, person.y2))
    conf = round(person.confidence * (garment["confidence"] if garment else 1.0), 3)
    return {
        "found": True,
        "label": garment["label"] if garment else "ไม่ทราบ",
        "category": garment["category"] if garment else "อื่น ๆ",
        "confidence": conf,
        "x_norm": x_norm,
        "detector_conf": round(person.confidence, 3),
        "classifier": garment["classifier"] if garment else "none",
    }


@app.get("/health")
def health():
    return {"ok": detector.backend != "none", "detector": detector.info(),
            "classifier": garments.info(), "backend": detector.backend}


@app.post("/ai/aim")
def aim(a: AimRequest, x_auth_token: Optional[str] = Header(default=None)):
    check_token(x_auth_token)
    if not a.image_b64:
        raise HTTPException(status_code=400, detail="ต้องส่ง image_b64")
    try:
        image = base64.b64decode(a.image_b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="image_b64 ไม่ใช่ base64 ที่ถูกต้อง")
    if len(image) > config.MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="ภาพใหญ่เกิน MAX_IMAGE_BYTES")

    t0 = time.perf_counter()
    try:
        result = analyze(image)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="analyze ล้มเหลว: %s" % e)
    ai_ms = (time.perf_counter() - t0) * 1000
    net_ms = round(max(0.0, (time.time() - a.t_sent) * 1000), 1) if a.t_sent else None

    return {"ok": True, "node_id": a.node_id, **result,
            "ai_ms": round(ai_ms, 1), "net_ms": net_ms,
            "detector": detector.backend}


if __name__ == "__main__":
    import uvicorn
    print("detector:", detector.info())
    print("classifier:", garments.info())
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")
