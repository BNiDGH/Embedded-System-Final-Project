"""จำแนกชนิดและสีของเสื้อผ้าจากภาพคนที่ตรวจพบ

สองชั้น
  1. ชนิดเสื้อผ้า: MobileNetV3 (ImageNet, pretrained) ถ้าติดตั้ง torch/torchvision
     แล้วแมปคลาสที่เกี่ยวข้อง (jersey/skirt/jean/cardigan/...) เป็นคำไทย
  2. สี: วิเคราะห์ช่วงสี HSV ของบริเวณเสื้อ (ครึ่งบน) หรือกางเกง/กระโปรง (ครึ่งล่าง)

ถ้าไม่มี torch จะใช้กฎสี+ตำแหน่งเป็น fallback และรายงาน backend ตามจริงใน /health
ชื่อที่คืนต้องตรงกับรายการใน cloud/config.py (WARDROBE) เพื่อให้นับยอดได้
"""
import threading

import cv2
import numpy as np

import config

# (ชื่อ, หมวด) — ต้องตรงกับ cloud/config.py
WARDROBE = [
    ("เสื้อยืดสีขาว", "เสื้อ"),
    ("เสื้อเชิ้ตสีเบจ", "เสื้อ"),
    ("กางเกงยีนส์สีน้ำเงิน", "กางเกง"),
    ("กางเกงขาสั้นสีกรมท่า", "กางเกง"),
    ("กระโปรงสีดำ", "กระโปรง"),
    ("กระโปรงพลีทสีเทา", "กระโปรง"),
]

# คลาส ImageNet -> (คำไทย, หมวด)
IMAGENET_GARMENTS = {
    "jersey, t-shirt, tee shirt": ("เสื้อยืด", "เสื้อ"),
    "sweatshirt": ("เสื้อสเวตเตอร์", "เสื้อ"),
    "cardigan": ("เสื้อคาร์ดิแกน", "เสื้อ"),
    "suit, suit of clothes": ("เสื้อสูท", "เสื้อ"),
    "trench coat": ("เสื้อโค้ท", "เสื้อ"),
    "fur coat": ("เสื้อโค้ท", "เสื้อ"),
    "lab coat": ("เสื้อคลุม", "เสื้อ"),
    "kimono": ("เสื้อคลุม", "เสื้อ"),
    "poncho": ("เสื้อคลุม", "เสื้อ"),
    "bulletproof vest": ("เสื้อกั๊ก", "เสื้อ"),
    "jean, blue jean, denim": ("กางเกงยีนส์", "กางเกง"),
    "miniskirt": ("กระโปรงสั้น", "กระโปรง"),
    "skirt": ("กระโปรง", "กระโปรง"),
}

# ช่วง HSV สำหรับชื่อสีไทย (OpenCV: H 0-179, S/V 0-255)
COLOR_RANGES = {
    "ขาว": [((0, 0, 185), (179, 40, 255))],
    "ดำ": [((0, 0, 0), (179, 255, 65))],
    "เทา": [((0, 0, 66), (179, 45, 184))],
    "เบจ": [((12, 25, 110), (34, 130, 255))],
    "น้ำเงิน": [((95, 70, 80), (128, 255, 255))],
    "กรมท่า": [((95, 55, 25), (128, 255, 110))],
    "แดง": [((0, 80, 60), (9, 255, 255)), ((171, 80, 60), (179, 255, 255))],
    "ชมพู": [((140, 25, 120), (170, 130, 255))],
    "เขียว": [((35, 60, 40), (90, 255, 255))],
    "เหลือง": [((20, 90, 120), (34, 255, 255))],
    "น้ำตาล": [((7, 55, 35), (22, 200, 140))],
    "ม่วง": [((129, 60, 50), (155, 255, 255))],
    "ส้ม": [((10, 100, 130), (22, 255, 255))],
}


def dominant_color(bgr_region):
    """คืนชื่อสีที่ครอบคลุมพื้นที่มากที่สุด (ถ้าภาพเล็ก/มืดเกินไปคืน เทา)"""
    if bgr_region is None or bgr_region.size == 0 or bgr_region.shape[0] < 4 or bgr_region.shape[1] < 4:
        return "เทา"
    hsv = cv2.cvtColor(bgr_region, cv2.COLOR_BGR2HSV)
    total = hsv.shape[0] * hsv.shape[1]
    best, best_frac = "เทา", 0.0
    for name, ranges in COLOR_RANGES.items():
        mask = None
        for lo, hi in ranges:
            m = cv2.inRange(hsv, np.array(lo), np.array(hi))
            mask = m if mask is None else cv2.bitwise_or(mask, m)
        frac = float(cv2.countNonZero(mask)) / total
        if frac > best_frac:
            best, best_frac = name, frac
    return best if best_frac >= 0.05 else "เทา"


class GarmentClassifier:
    def __init__(self):
        self.backend = "color"
        self.error = ""
        self.note = ""
        self._lock = threading.Lock()
        self._model = None
        self._preprocess = None
        self._classes = []

        if config.AI_CLASSIFIER in ("auto", "torch") and self._init_torch():
            return
        if config.AI_CLASSIFIER == "torch":
            self.error = "โหลด torchvision ไม่ได้ (pip install torch torchvision)"
        else:
            self.error = ""
            self.note = "ใช้กฎสี (ไม่ได้ติดตั้ง torch/torchvision)"

    def _init_torch(self):
        try:
            import torch
            from torchvision import transforms
            from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

            weights = MobileNet_V3_Small_Weights.DEFAULT
            model = mobilenet_v3_small(weights=weights).eval()
            self._torch = torch
            self._preprocess = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                     std=[0.229, 0.224, 0.225]),
            ])
            self._classes = weights.meta["categories"]
            self._model = model
            self.backend = "torch"
            self.model_name = "MobileNetV3-Small (ImageNet)"
            return True
        except Exception as e:
            self.error = "torchvision: %s" % e
            return False

    # ------------------------------------------------------------ ชนิดผ้า
    def _torch_predict(self, crop_bgr):
        from PIL import Image

        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        tensor = self._preprocess(pil).unsqueeze(0)
        with self._lock, self._torch.no_grad():
            probs = self._torch.nn.functional.softmax(self._model(tensor)[0], dim=0)
        top = probs.topk(5)
        for idx, prob in zip(top.indices.tolist(), top.values.tolist()):
            name = self._classes[idx]
            if name in IMAGENET_GARMENTS:
                noun, category = IMAGENET_GARMENTS[name]
                return noun, category, float(prob)
        return None

    # -------------------------------------------------------------- classify
    def classify(self, img_bgr, box):
        """box = (x1, y1, x2, y2) ของคนทั้งตัว"""
        x1, y1, x2, y2 = [int(max(0, v)) for v in box]
        crop = img_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        h, w = crop.shape[:2]
        upper = crop[int(h * 0.08):int(h * 0.48), int(w * 0.12):int(w * 0.88)]
        lower = crop[int(h * 0.55):int(h * 0.95), int(w * 0.12):int(w * 0.88)]

        predicted = self._torch_predict(crop) if self.backend == "torch" else None

        if predicted:
            noun, category, prob = predicted
            color = dominant_color(upper if category == "เสื้อ" else lower)
            label = "%sสี%s" % (noun, color)
            return {"label": label, "category": category,
                    "confidence": round(prob, 3), "color": color,
                    "classifier": self.backend}
            # ไม่ตรงรายการ WARDROBE ก็ได้ cloud จะเก็บชื่อใหม่ให้เอง

        # fallback: กฎสี/ตำแหน่ง (รายงานตามจริงว่าเป็น color heuristic)
        upper_color = dominant_color(upper)
        lower_color = dominant_color(lower)
        if lower_color in ("น้ำเงิน",):
            noun, category = "กางเกงยีนส์", "กางเกง"
        elif lower_color in ("กรมท่า",):
            noun, category = "กางเกงขาสั้น", "กางเกง"
        elif lower_color == "ดำ":
            noun, category = "กระโปรง", "กระโปรง"
        elif lower_color == "เทา":
            noun, category = "กระโปรงพลีท", "กระโปรง"
        elif upper_color == "เบจ":
            noun, category = "เสื้อเชิ้ต", "เสื้อ"
        else:
            noun, category = "เสื้อยืด", "เสื้อ"

        return {"label": "%sสี%s" % (noun, upper_color if category == "เสื้อ" else lower_color),
                "category": category, "confidence": 0.45,
                "color": upper_color if category == "เสื้อ" else lower_color,
                "classifier": "color"}

    def info(self):
        return {"backend": self.backend, "model": getattr(self, "model_name", "color heuristic"),
                "note": self.note, "error": self.error}
