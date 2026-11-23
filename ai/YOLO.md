# วิธีทำ AI YOLO (ตรวจจับคนด้วย YOLO)

`detector.py` รองรับ YOLO อยู่แล้วผ่าน `ultralytics` — ไฟล์นี้คือขั้นตอนเปิดใช้จริง
ตั้งแต่ติดตั้ง ตั้งค่า ยิงทดสอบ ไปจนถึงแก้ปัญหาที่เจอบ่อย

YOLO ในโปรเจกต์นี้ทำหน้าที่เดียว: **หาคนในภาพ** แล้วคืนกรอบ + ความมั่นใจ
จากนั้น `app.py` แปลงเป็น `x_norm` (0 = ซ้าย, 1 = ขวา) ให้ gateway หมุน servo
(YOLO ไม่ได้จำแนกชนิดเสื้อผ้า — ส่วนนั้นเป็นงานของ `garment.py`)

## 0. ลำดับ backend ที่โค้ดเลือก

| `AI_BACKEND` | พฤติกรรม |
|---|---|
| `auto` (ค่าเริ่มต้น) | ลอง YOLO ก่อน ถ้า import ไม่ได้ค่อยตกไปใช้ OpenCV HOG |
| `yolo` | บังคับ YOLO ถ้าโหลดไม่ได้ `/health` จะรายงาน error (ไม่เงียบ) |
| `hog` | บังคับ HOG ไม่ต้องติดตั้งอะไรเพิ่ม |

ดูว่าตอนนี้ใช้ตัวไหน: `GET http://127.0.0.1:8001/health` → ดูฟิลด์ `backend`

## 1. ติดตั้ง (ใน venv ของโปรเจกต์)

`ultralytics` จะดึง `torch` + `torchvision` มาด้วย (โหลดหลายร้อย MB) แนะนำให้ลงใน
`.venv` ของโปรเจกต์ ไม่ใช่ Python ระบบ

```bash
# จากโฟลเดอร์ wearwise/
.venv/Scripts/python.exe -m pip install -r ai/requirements.txt   # ของเดิม
.venv/Scripts/python.exe -m pip install "ultralytics>=8.2"
```

ตรวจว่าลงสำเร็จ:

```bash
.venv/Scripts/python.exe -c "from ultralytics import YOLO; print('ultralytics ok')"
```

## 2. ตั้งค่า `ai/.env`

```bash
cp ai/.env.example ai/.env     # ถ้ายังไม่มี
```

แก้ค่าเหล่านี้:

```ini
AI_BACKEND=yolo           # auto = ลอง YOLO ก่อน / yolo = บังคับ
AI_MODEL=yolov8n.pt       # ชื่อโมเดล หรือ path ไปยังไฟล์ .pt/.onnx
AI_CONF=0.35              # เกณฑ์ความมั่นใจขั้นต่ำ (0-1)
AI_DEVICE=cpu             # cpu หรือ 0 (GPU ตัวแรก) ถ้ามี CUDA
```

ครั้งแรกที่รัน โมเดลจะถูกดาวน์โหลดอัตโนมัติมาไว้ที่ `ai/yolov8n.pt`
ถ้าเครื่องไม่มีเน็ต ให้โหลดไฟล์ `.pt` มาจากเครื่องอื่นแล้ววางใน `ai/`
และตั้ง `AI_MODEL` เป็น path ของไฟล์นั้น

## 3. รันและตรวจว่า YOLO ทำงานจริง

```bash
cd ai
../.venv/Scripts/python.exe app.py          # หรือ uvicorn app:app --host 0.0.0.0 --port 8001
```

```bash
curl -s http://127.0.0.1:8001/health
```

ต้องเห็น `"backend":"yolo"` และ `"model":"YOLO (yolov8n.pt)"`
ถ้าเห็น `"backend":"hog"` แปลว่ายัง import YOLO ไม่ได้ (ดูข้อ 6)

## 4. ยิงภาพทดสอบ

```bash
cd wearwise
.venv/Scripts/python.exe - <<'EOF'
import base64, json, time, urllib.request
img = open("test.jpg", "rb").read()          # ภาพที่มีคนจริง
body = json.dumps({"node_id": "CB302", "t_sent": time.time(),
                   "image_b64": base64.b64encode(img).decode()}).encode()
req = urllib.request.Request("http://127.0.0.1:8001/ai/aim", data=body,
                             headers={"Content-Type": "application/json"})
print(urllib.request.urlopen(req, timeout=30).read().decode())
EOF
```

ผลที่ควรได้: `"found":true`, `"detector":"yolo"`, `"x_norm"` เป็นตัวเลข 0-1
และ `"ai_ms"` บอกเวลาที่โมเดลใช้จริง (เอาไปใส่เล่มได้)

## 5. เลือกโมเดลให้พอดีกับเครื่อง

| โมเดล | ขนาด | CPU (ประมาณ) | เหมาะกับ |
|---|---|---|---|
| `yolov8n.pt` / `yolo11n.pt` | ~6 MB | เร็วที่สุด | ค่าเริ่มต้นของโปรเจกต์นี้ |
| `yolov8s.pt` / `yolo11s.pt` | ~22 MB | ช้ากว่า n ≈ 2-3 เท่า | มี GPU หรือภาพยาก |
| `yolov8m.pt` ขึ้นไป | 50 MB+ | ช้ามากบน CPU | ไม่แนะนำกับ gateway timeout 5 วิ |

**ข้อจำกัดเวลาสำคัญ:** gateway ตั้ง `HTTP_TIMEOUT_MS` = 5000 ms และยิงทุก
`AI_INTERVAL_MS` = 4000 ms ถ้าโมเดลใช้เวลาเกิน ~5 วิ gateway จะตัดทิ้งและขึ้น
"เรียก AI ไม่สำเร็จ" — บน CPU ให้ใช้รุ่น `n` เท่านั้น

## 6. แก้ปัญหาที่เจอบ่อย

| อาการ | สาเหตุ / วิธีแก้ |
|---|---|
| `/health` ขึ้น `"backend":"hog"` | ยังไม่ลง ultralytics หรือลงคนละ Python → ตรวจด้วย `.venv/Scripts/python.exe -c "import ultralytics"` |
| `/health` ขึ้น `"backend":"none"` + error | ตั้ง `AI_BACKEND=yolo` แต่โหลดโมเดลไม่ได้ → ดูข้อความใน `"error"` |
| `ModuleNotFoundError: ultralytics` | ลงผิด env (ระบบ vs `.venv`) → ลงใหม่ด้วย `.venv/Scripts/python.exe -m pip install ultralytics` |
| ค้างนานครั้งแรก | ปกติ: กำลังดาวน์โหลด/โหลดโมเดล + warm-up ครั้งแรกช้ากว่าปกติมาก |
| โหลดโมเดลไม่ได้ (ออฟไลน์) | โหลด `.pt` จากเครื่องอื่นมาวางใน `ai/` แล้วตั้ง `AI_MODEL=ai/yolov8n.pt` |
| `found:false` ตลอด | ภาพมืด/เบลอจาก OV7670, `AI_CONF` สูงเกิน (ลอง 0.25), หรือคนอยู่นอกกรอบ |
| `CUDA error` | ตั้ง `AI_DEVICE=cpu` หรือติดตั้ง torch เวอร์ชัน CUDA ให้ตรงการ์ด |
| ช้าเกิน 5 วิ | ใช้รุ่น `n`, ลดขนาดภาพก่อนส่ง, หรือ export เป็น ONNX (ข้อ 7) |

## 7. เร่งความเร็ว (ไม่บังคับ)

- **ลดขนาดภาพ:** ส่ง JPEG QVGA (320×240) จาก gateway อยู่แล้ว — ไม่ต้องเพิ่ม
- **ONNX:** `yolo export model=yolov8n.pt format=onnx imgsz=320` แล้วตั้ง
  `AI_MODEL=yolov8n.onnx` (ultralytics ยังเรียกผ่าน `YOLO()` ได้เหมือนเดิม)
- **ปรับ imgsz:** ใน `detector.py` เพิ่ม `imgsz=320` ใน `self._yolo.predict(...)`
  ช่วยลดเวลาบน CPU แต่คนไกลอาจตรวจไม่เจอ
- **GPU:** ติดตั้ง torch แบบ CUDA แล้วตั้ง `AI_DEVICE=0`

## 8. เทรนโมเดลเอง (ถ้าต้องการความแม่นกับหน้างานจริง)

ไม่จำเป็นสำหรับเดโมนี้ เพราะ COCO มีคลาส `person` อยู่แล้ว แต่ถ้าจะเทรนกับภาพ
จากตู้จริง (แสง/มุมของตัวเอง):

1. ติดป้ายกรอบคนด้วย Roboflow / LabelImg (ฟอร์แมต YOLO: `class cx cy w h`)
2. จัดโฟลเดอร์ `dataset/images/{train,val}` และ `dataset/labels/{train,val}`
3. สร้าง `data.yaml` ที่มี `names: [person]`
4. `yolo train model=yolov8n.pt data=data.yaml epochs=50 imgsz=320`
5. เอา `runs/detect/train/weights/best.pt` มาวางใน `ai/` แล้วตั้ง `AI_MODEL`

> ถ้าเทรนใหม่ให้เหลือคลาสเดียว ต้องแก้ `classes=[0]` ใน `_detect_yolo`
> ให้ตรงกับ index ของคลาส person ในโมเดลใหม่ (คลาสเดียว = 0 อยู่แล้ว)

## 9. เชื่อมกับ gateway

- `board/gateway/config.h` → `AI_URL` ต้องชี้ IP:พอร์ตของเครื่องที่รัน AI
  (ค่าเริ่มต้น `http://192.168.1.50:8001`)
- gateway ส่ง `POST /ai/aim` ทุก 4 วิเมื่อตรวจพบคนใกล้ (< `PERSON_CM` 80 ซม.)
- `found=false` → servo กลับมุมปลอดภัย `SERVO_SAFE` (90°)
- `found=true` → `angle = SERVO_MIN + x_norm × (SERVO_MAX − SERVO_MIN)` = 20°–160°
- ทุก request แนบ `X-Auth-Token` ถ้าตั้ง `API_TOKEN` ไว้ ต้องตรงกับ `INGEST_TOKEN` ใน `ai/.env`
