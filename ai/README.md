# ai/ — บริการ vision สำหรับ M4 (closed loop)

รับภาพจาก gateway แล้วตอบว่าเจอคนไหม อยู่ตำแหน่งไหน และจำแนกเสื้อผ้าเป็นอะไร
ผล `x_norm` ถูก gateway ใช้สั่ง servo จริง

## ติดตั้ง

```bash
cp .env.example .env
pip install -r requirements.txt                # fastapi, opencv, numpy
uvicorn app:app --host 0.0.0.0 --port 8001
```

ค่าเริ่มต้นใช้ **OpenCV HOG + SVM people detector** (โมเดลจริงที่มากับ OpenCV
ไม่ต้องโหลดอะไรเพิ่ม) และใช้กฎสีจำแนกชนิดผ้า

ถ้าต้องการความแม่นขึ้น เลือกติดตั้งเพิ่ม (ไม่บังคับ)

```bash
pip install ultralytics        # ตรวจจับคนด้วย YOLOv8n (ดาวน์โหลดโมเดลอัตโนมัติ)
pip install torch torchvision  # จำแนกชนิดผ้าด้วย MobileNetV3 (ImageNet)
```

แล้วตั้ง `AI_BACKEND=yolo` / `AI_CLASSIFIER=torch` หรือปล่อย `auto`
(ลำดับ auto: YOLO → HOG และ torch → color)

ขั้นตอนเปิดใช้ YOLO แบบละเอียด (ติดตั้ง ตั้งค่า ทดสอบ แก้ปัญหา) อยู่ที่
[`YOLO.md`](YOLO.md)

ตรวจว่ากำลังใช้อะไร: <http://127.0.0.1:8001/health>

## API

```http
POST /ai/aim
{"node_id":"CB302","image_b64":"<JPEG base64>","t_sent":1767000000.0,"approach":true}
```

```json
{"ok":true,"found":true,"label":"เสื้อยืดสีขาว","category":"เสื้อ",
 "confidence":0.71,"x_norm":0.62,"detector_conf":0.93,
 "ai_ms":96.2,"net_ms":140.0,"detector":"hog"}
```

- `found=false` → gateway หมุน servo กลับมุมปลอดภัย
- `x_norm` = จุดกลางแนวนอนของคนในภาพ (0 = ซ้าย, 1 = ขวา)

## หลักการทำงาน

1. `detector.py` หาคนที่ใหญ่ที่สุดในภาพ (ใกล้ที่สุด)
2. `garment.py` ครอปครึ่งบน/ครึ่งล่างของคนนั้น
   - ชนิดผ้า: MobileNetV3 (ImageNet) แมปคลาส jersey/skirt/jean/... เป็นคำไทย
   - สี: ช่วง HSV ที่กำหนดใน `COLOR_RANGES`
   - ไม่มี torch → ใช้กฎสี+ตำแหน่ง และรายงาน `classifier: "color"` ตามจริง
3. `app.py` รวมผลเป็น `label`, `category`, `confidence`, `x_norm` และวัด `ai_ms`

## วัดความแม่น (ใช้ในเล่ม)

เตรียมโฟลเดอร์ภาพทดสอบแยกตามชื่อจริง เช่น `testdata/เสื้อยืดสีขาว/*.jpg`
แล้วยิงเข้าบริการทีละภาพ เทียบ `label` กับชื่อโฟลเดอร์ คำนวณ precision/recall
รายงานจำนวนภาพและค่าที่วัดได้จริง (ห้ามใส่ตัวเลขสมมติ)

## ข้อจำกัดที่ควรเขียนในเล่ม

- ภาพจาก OV7670 ความละเอียด QVGA แสงน้อยอาจทำให้ HOG ตรวจคนพลาด
- ชนิดผ้าจาก MobileNet เป็น pretrained บน ImageNet ไม่ได้เทรนกับตู้จริง
  จึงควรวัด accuracy กับภาพชุดทดสอบของกลุ่มเอง
- การนับ "หยิบ" เกิดจาก edge detection + cooldown ไม่ใช่การติดตามมือ
