"""ตรวจจับคนในภาพ

ลำดับการเลือก backend (ตั้ง AI_BACKEND เพื่อบังคับ)
  1. yolo   ใช้ ultralytics YOLO (โมเดล COCO) ตรวจคลาส person
  2. hog    ใช้ OpenCV HOG + SVM people detector ที่มากับ OpenCV (ไม่ต้องโหลดโมเดล)

ทั้งสองเป็นโมเดลจริง ไม่ใช่การสุ่ม คืนกรอบและความมั่นใจเพื่อให้ gateway
เอา x_norm ไปสั่ง servo ต่อ (M4 closed loop)
"""
import threading

import cv2
import numpy as np

import config


class Detection:
    __slots__ = ("x1", "y1", "x2", "y2", "confidence")

    def __init__(self, box, confidence):
        self.x1, self.y1, self.x2, self.y2 = [float(v) for v in box]
        self.confidence = float(confidence)

    @property
    def w(self):
        return max(1.0, self.x2 - self.x1)

    @property
    def h(self):
        return max(1.0, self.y2 - self.y1)

    @property
    def area(self):
        return self.w * self.h


class PersonDetector:
    def __init__(self):
        self.backend = "none"
        self.error = ""
        self.note = ""
        self._lock = threading.Lock()
        self._yolo = None
        self._hog = None

        backend = config.AI_BACKEND
        if backend in ("auto", "yolo"):
            if self._init_yolo():
                return
            if backend == "yolo":
                self.error = "โหลด YOLO ไม่ได้ (ตรวจ AI_MODEL / pip install ultralytics)"
                return
            self.error = ""  # auto: ไม่มี YOLO ก็ใช้ HOG ต่อได้ ไม่ถือเป็น error
        if backend in ("auto", "hog"):
            if self._init_hog() and not self.error:
                self.note = "ใช้ OpenCV HOG (ไม่ได้ติดตั้ง ultralytics)"

    # ---------------------------------------------------------------- YOLO
    def _init_yolo(self):
        try:
            from ultralytics import YOLO
            self._yolo = YOLO(config.AI_MODEL)
            self.backend = "yolo"
            self.model_name = "YOLO (%s)" % config.AI_MODEL
            return True
        except Exception as e:
            self.error = "YOLO: %s" % e
            return False

    # ----------------------------------------------------------------- HOG
    def _init_hog(self):
        try:
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self._hog = hog
            self.backend = "hog"
            self.model_name = "OpenCV HOG + SVM (people detector)"
            return True
        except Exception as e:
            self.error = "HOG: %s" % e
            return False

    # -------------------------------------------------------------- detect
    def detect(self, bgr):
        if self.backend == "yolo":
            return self._detect_yolo(bgr)
        if self.backend == "hog":
            return self._detect_hog(bgr)
        return []

    def _detect_yolo(self, bgr):
        with self._lock:
            results = self._yolo.predict(
                bgr, conf=config.AI_CONF, classes=[0], verbose=False, device=config.AI_DEVICE)
        out = []
        for r in results:
            if r.boxes is None:
                continue
            for box, conf in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist()):
                out.append(Detection(box, conf))
        return out

    def _detect_hog(self, bgr):
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=0.75, fy=0.75)  # ลดเวลา ประมาณ 2 เท่า
        with self._lock:
            rects, weights = self._hog.detectMultiScale(
                gray, winStride=(8, 8), padding=(8, 8), scale=1.05)
        out = []
        for (x, y, w, h), weight in zip(rects, weights):
            # HOG คืนพิกัดหลังย่อภาพ ต้องคูณกลับ
            box = (x / 0.75, y / 0.75, (x + w) / 0.75, (y + h) / 0.75)
            conf = float(np.clip(weight, 0.0, 1.0))
            if conf >= 0.2:
                out.append(Detection(box, conf))
        # เก็บกรอบที่ใหญ่สุด 3 อันพอ (กันภาพพื้นหลังรก)
        out.sort(key=lambda d: d.area, reverse=True)
        return out[:3]

    def info(self):
        return {"backend": self.backend, "model": getattr(self, "model_name", ""),
                "note": self.note, "error": self.error}
