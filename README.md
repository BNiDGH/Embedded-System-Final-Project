# WearWise — ของจริง แยก 4 ส่วน

ระบบตู้เสื้อผ้าอัจฉริยะตามโจทย์ Embedded System (CEDT) Final Project 2026
สร้างจากชุดจำลองใน `../wearwise_mock/` โดยแยกเป็น 4 โฟลเดอร์ที่รันแยกกันได้จริง

> อยากรู้ว่าไฟล์ไหนเปิดด้วยอะไร แก้ตรงไหน → ดู [`HOWTO.md`](HOWTO.md)

```
board/            เฟิร์มแวร์ ESP32 (ของจริง)
  sensor_node/    NA709: DHT22 + MQ-135 + BH1750 → ESP-NOW (ack/retry)
  gateway/        CB302: ESP-NOW + HC-SR04 + พัดลม + servo + OV7670
        │ HTTP (Wi-Fi)
        ├──────────────► cloud/        เก็บข้อมูลดิบ + เหตุการณ์ + นับการหยิบ
        │                    │
        │                    ├── Google Sheets (Apps Script / service account)
        │                    └── SQLite (โหมดสำรอง)
        │
        └──────────────► ai/           ตรวจคน + จำแนกเสื้อผ้า → x_norm
                             ▲
                             │ อ่าน /api/state
                    web_dashboard/         แสดงผล + ปุ่มหยุดฉุกเฉิน
```

## แต่ละโฟลเดอร์ทำอะไร

| โฟลเดอร์ | ภาษา | หน้าที่ | เริ่มที่ |
|---|---|---|---|
| `board/` | C++ (Arduino) | อ่านเซนเซอร์, ESP-NOW, ควบคุมพัดลม/servo, กล้อง, spool ข้อมูล | `board/README.md` |
| `cloud/` | Python (FastAPI) | รับแถว/เหตุการณ์, เขียน Sheets หรือ SQLite, แจ้งเตือน Discord, นับการหยิบ | `cloud/README.md` |
| `ai/` | Python (FastAPI + OpenCV) | ตรวจจับคน (YOLO/HOG) + จำแนกเสื้อผ้า + ตำแหน่ง x_norm | `ai/README.md` |
| `web_dashboard/` | Python + HTML/JS | dashboard อ่าน cloud, ส่งคำสั่งหยุดฉุกเฉิน | `web_dashboard/README.md` |

## สิ่งที่เปลี่ยนจากชุดจำลองเป็นของจริง

| ชุดจำลอง (`wearwise_mock/`) | ของจริง (`wearwise/`) |
|---|---|
| `mock_node.py` สุ่มค่าที่โน้ตบุ๊ก | `board/sensor_node/` อ่าน DHT22/MQ-135/BH1750 จริง |
| `mock_gateway.py` จำลอง HC-SR04/กล้อง/actuator | `board/gateway/` ISR ของ HC-SR04, รีเลย์พัดลม, servo, OV7670 |
| ส่ง HTTP แทน ESP-NOW | ESP-NOW + application-level ack/retry + คิวส่งซ้ำ |
| `ai.py` สุ่มผล | `ai/` ใช้โมเดลจริง (YOLO หรือ OpenCV HOG) + จำแนกสี/ชนิดผ้า |
| `server.py` รวม cloud+AI+dashboard | แยก `cloud/`, `ai/`, `web_dashboard/` คนละพอร์ต |
| ข้อมูลหายเมื่อเน็ตหลุด | gateway เขียน LittleFS ก่อนส่ง (store-and-forward) |

## วิธีรันทั้งระบบ

### 1. เตรียมเครื่องที่รัน cloud + AI + dashboard

```bash
cd cloud           && cp .env.example .env      # ไม่ตั้ง Google ก็ใช้ SQLite ได้
pip install -r requirements.txt
cd ../ai           && cp .env.example .env
pip install -r requirements.txt                 # ตัวเลือกโมเดลจริงดู ai/README.md
cd ../web_dashboard && cp .env.example .env
pip install -r requirements.txt
```

### 2. เปิด 3 บริการ (คนละเทอร์มินัล)

```bash
cd cloud           && uvicorn app:app --host 0.0.0.0 --port 8000
cd ai              && uvicorn app:app --host 0.0.0.0 --port 8001
cd web_dashboard   && uvicorn server:app --host 0.0.0.0 --port 8080
```

เปิด dashboard ที่ <http://127.0.0.1:8080>

### ทางเลือก: รันทั้งสามบริการด้วย Docker

ถ้ามี Docker Desktop ไม่ต้องติดตั้ง Python เอง:

```bash
docker compose up -d --build     # build ครั้งแรกประมาณ 1-3 นาที
# เปิด http://127.0.0.1:8080

docker compose logs -f cloud      # ดู log
docker compose down               # หยุด (ข้อมูลใน volume ยังอยู่)
docker compose down -v            # หยุด + ล้างข้อมูล SQLite
```

| service | พอร์ต | โฟลเดอร์ใน container |
|---|---|---|
| `cloud` | 8000 | `/app` (โค้ดจาก `cloud/`) |
| `ai` | 8001 | `/app` (โค้ดจาก `ai/`) |
| `dashboard` | 8080 | `/app` (โค้ดจาก `web_dashboard/`) |

- แต่ละ service build จาก `Dockerfile` เดียวกัน โดยส่ง `SERVICE=` เป็น build arg
- `.env` ของแต่ละโฟลเดอร์ถูกอ่านอัตโนมัติถ้ามี (ไม่ต้องแก้ compose) และ `environment:` ใน compose ชนะ `.env`
- ข้อมูล SQLite อยู่ใน volume `wearwise_cloud-data` ที่ `/data/cloud.db`
- dashboard คุยกับ cloud/AI ผ่านชื่อ service (`http://cloud:8000`, `http://ai:8001`) ไม่ใช่ `127.0.0.1`
- ใน container `GATEWAY_URL` ยังต้องเป็น IP ของ ESP32 ในวง LAN (bridge network ออก LAN ได้ปกติ)
- image ยังไม่มี `torch`/`ultralytics` (ตัวเลือก) — AI จึงรายงาน `backend:"hog"`; ถ้าต้องการ YOLO ให้เพิ่มใน `ai/requirements.txt` แล้ว `docker compose build ai`
- แก้โค้ดแล้วต้อง `docker compose up -d --build` ใหม่ (ไม่ได้ mount โค้ดเข้า container)

### 3. ตั้งค่าและอัปโหลดบอร์ด

1. `board/gateway/secrets.h.example` → `secrets.h` ใส่ Wi-Fi และ IP ของเครื่องที่รัน cloud/AI
   (ต้องเป็น IP ในวง LAN เช่น `192.168.1.50` ไม่ใช่ `127.0.0.1`)
2. อัปโหลด gateway → จดช่อง Wi-Fi ที่ Serial ปริ๊นต์
3. ตั้ง `NODE_CHANNEL` ใน `board/sensor_node/config.h` ให้ตรงช่องนั้น แล้วอัปโหลด node

ไม่ต้องใช้ Arduino IDE ก็ได้: `board/pio-node.ini` / `board/pio-gateway.ini` คอมไพล์ด้วย
PlatformIO (`pio run -c pio-gateway.ini`) — ดู `board/README.md`

### 4. ตรวจว่าไหลครบ

- dashboard ขึ้น "gateway ออนไลน์" และมีแถวใหม่ทุก 2 วินาที
- ยกมือ/เดินผ่านหน้า HC-SR04 → servo หมุนตามผล AI และมี event `ai → servo`
- ความชื้นเกิน 75% (หรือก๊าซเกิน 450) → พัดลมเปิด, event `พัดลม`
- กดหยุดฉุกเฉิน → gateway ปิดพัดลมทันที servo กลับ 90°

## สัญญาข้อมูลระหว่างชั้น

**node → gateway (ESP-NOW, โครงสร้างใน `board/common/wearwise_protocol.h`)**

```c
SensorPacket { magic, type, node_id[12], seq, uptime_ms,
               temp, hum, gas, lux, rtt_ms, retries }
AckPacket    { magic, type, node_id[12], ack_seq, fan, estop }
```

**gateway → cloud**

```json
POST /cloud/rows
{"ts":1767000000.5,"node_id":"NA709","seq":12,"temp":27.4,"hum":58.2,
 "gas":310,"lux":120,"hop_ms":8.4,"note":"node -> gateway"}

POST /cloud/events
{"ts":1767000002,"node_id":"CB302","kind":"fan","text":"พัดลมเปิด: ..."}
```

**gateway → AI**

```json
POST /ai/aim
{"node_id":"CB302","image_b64":"<JPEG base64>","t_sent":1767000000.0,"approach":true}
```

```json
{"ok":true,"found":true,"label":"เสื้อยืดสีขาว","category":"เสื้อ",
 "confidence":0.71,"x_norm":0.62,"ai_ms":96.2,"detector":"hog"}
```

gateway แปลง `x_norm` เป็นมุม `20 + x_norm × 140` องศา (จำกัด 20°–160°)

**dashboard → cloud**

- `GET /api/state` — ข้อมูลรวมสำหรับวาดหน้า
- `POST /api/estop` — `{"on":true|false}` → cloud → gateway
- `POST /api/reset` — ล้างยอดการหยิบ

## ความปลอดภัยและการตั้งค่า

- รหัส Wi-Fi อยู่ที่ `board/gateway/secrets.h` (gitignore) ไม่ฝังในโค้ดที่ commit
- `INGEST_TOKEN` ใช้ตรวจ header `X-Auth-Token` ระหว่าง gateway → cloud/AI
  (ตั้งให้ตรงกัน 3 ที่: `board/gateway/secrets.h`, `cloud/.env`, `ai/.env`)
- ไม่มีไฟบ้านในวงจรพัดลมของเฟิร์มแวร์ตัวอย่างนี้: ใช้รีเลย์/มอสเฟตแยกไฟเลี้ยง
  และพัดลมต้องมีทางตัดไฟ (E-stop + timeout 180 วินาที) ตาม M7
- ห้าม commit `.env`, `secrets.h`, `service-account.json`, ไฟล์ `.db`

## ตรวจรับตามเกณฑ์

| ข้อ | หลักฐานในโค้ด |
|---|---|
| M1 | `board/README.md` ตารางขา: node 3 ชนิด, gateway 2 ชนิด |
| M2 | พัดลม (รีเลย์) + servo |
| M3 | ESP-NOW ระหว่าง node กับ gateway |
| M4 | OV7670 → `/ai/aim` → `x_norm` → มุม servo |
| M5 | ทุกแถวขึ้น `/cloud/rows` → Google Sheets/SQLite + dashboard |
| M6 | cloud ส่ง Discord ตาม `NOTIFY_KINDS` |
| M7 | E-stop, servo limit, fan max-on, node timeout, ไม่มีไฟบ้าน |
| M8 | โครงสร้างแยกโฟลเดอร์พร้อม commit ต่อคน |
| E1 | FreeRTOS 3 task (node) / 4 task (gateway) + queue |
| E2 | ISR ของ HC-SR04 แล้วประมวลผลใน task |
| E4 | ack/retry + LittleFS spool |
| E5 | token ระหว่าง gateway ↔ cloud/AI, ไม่มี secret ใน Git |

## ล้างข้อมูล

```bash
curl -X POST 127.0.0.1:8000/api/reset
```

โหมด SQLite จะลบแถวใน `cloud/cloud.db` ด้วย ถ้าใช้ Google Sheets จริงให้ลบแถวเอง
(หรือรัน `removeDuplicateRows` ใน Apps Script ถ้าเคยส่งซ้ำ)

ชุดจำลองเดิมยังอยู่ใน `../wearwise_mock/` ใช้เทียบพฤติกรรมหรือถ่ายวิดีโอสำรองได้
