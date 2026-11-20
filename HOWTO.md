# HOWTO — เปิดไฟล์ไหน ด้วยอะไร ทำอะไรต่อ

คู่มือทีละไฟล์ของโปรเจกต์ `wearwise/` (ทุกไฟล์ในโฟลเดอร์นี้อยู่ในตารางแล้ว)
ถ้าอยากรันทั้งระบบเร็วสุด ไปที่ [ทางลัด: Docker](#ทางลัด-docker-คำสั่งเดียวจบ) ได้เลย

## โปรแกรมที่ต้องมี

| งาน | เปิดด้วย |
|---|---|
| ไฟล์ `.py`, `.js`, `.html`, `.css`, `.md`, `.yml`, `Dockerfile`, `.env` | **VS Code** (หรือ Notepad/TextEdit ก็ได้) |
| ไฟล์ `.ino`, `.h` ของบอร์ด | **Arduino IDE 2.x** (ต้องเปิดผ่านโฟลเดอร์ sketch ไม่ใช่เปิดไฟล์เดี่ยว) |
| ไฟล์ `.gs` | เบราว์เซอร์ → Google Sheets → Extensions → Apps Script |
| หน้า dashboard | เบราว์เซอร์ เปิดที่ `http://127.0.0.1:8080` (ห้ามดับเบิลคลิก `index.html`) |
| ดู JSON ของ API | เบราว์เซอร์ หรือ `curl` |

ติดตั้ง VS Code extension ที่ช่วยได้: Python, Docker, Arduino (optional)

## ทางลัด: Docker คำสั่งเดียวจบ

```bash
cd wearwise
docker compose up -d --build
```

เปิด <http://127.0.0.1:8080> — จบ ไม่ต้องติดตั้ง Python หรือแก้ `.env` ก็รันได้ (ใช้ SQLite)

---

## ไฟล์ระดับบนสุด

| ไฟล์ | เปิดด้วย | ใช้ทำอะไร / ต้องแก้ไหม |
|---|---|---|
| `README.md` | VS Code (กด `Ctrl+Shift+V` เพื่อพรีวิว) | ภาพรวมสถาปัตยกรรม ตารางส่งงาน M1–M7 — อ่านก่อน |
| `HOWTO.md` | VS Code preview | ไฟล์นี้ |
| `docker-compose.yml` | VS Code | ตั้ง 3 service, พอร์ต, volume, healthcheck แก้เมื่อเปลี่ยนพอร์ต/イメージ |
| `Dockerfile` | VS Code | image กลาง เลือกโฟลเดอร์ด้วย `--build-arg SERVICE=` ไม่ต้องแก้ปกติ |
| `.dockerignore` | VS Code | กัน `.env`/`*.db`/`board/` ไม่ให้เข้า image |
| `.gitignore` | VS Code | กัน `secrets.h`, `.env`, `*.db` ขึ้น Git — อย่าลบ |

---

## `board/` — เฟิร์มแวร์ (เปิดใน Arduino IDE)

วิธีเปิด: **Arduino IDE → File → Open → เลือกโฟลเดอร์** `board/gateway/gateway.ino`
(ไฟล์ `.h` ที่อยู่ข้างกันจะขึ้นเป็นแท็บอัตโนมัติ ไม่ต้องเปิดแยก)

| ไฟล์ | เปิดด้วย | ต้องแก้อะไร |
|---|---|---|
| `board/README.md` | VS Code | ตารางขา, ไลบรารี, วิธีคาลิเบรต MQ-135 |
| `board/sensor_node/sensor_node.ino` | Arduino IDE (บอร์ด **ESP32 Dev Module**) | ไม่ต้องแก้ — แก้ที่ `config.h` |
| `board/sensor_node/config.h` | Arduino IDE (แท็บ) | `NODE_CHANNEL` ให้ตรงช่อง Wi-Fi ของ gateway, ขาเซนเซอร์, `MQ135_R0_KOHM` หลังคาลิเบรต, `DEEP_SLEEP_S` |
| `board/gateway/gateway.ino` | Arduino IDE (บอร์ด **ESP32S3 Dev Module**) | ไม่ต้องแก้ |
| `board/gateway/config.h` | Arduino IDE (แท็บ) | ขา TRIG/ECHO/รีเลย์/servo, ขา OV7670 ให้ตรงสายจริง, `WEARWISE_CAMERA 0` ถ้าไม่ใช้กล้อง, เกณฑ์พัดลม |
| `board/gateway/secrets.h.example` | VS Code → **Save As** เป็น `secrets.h` | ใส่ `WIFI_SSID`, `WIFI_PASS`, `CLOUD_URL`, `AI_URL`, `API_TOKEN` |
| `board/gateway/secrets.h` | VS Code (เกิดขึ้นหลังคัดลอก) | ไฟล์ลับ — gitignore ไว้ อย่า commit |
| `board/common/wearwise_protocol.h` | Arduino IDE (แท็บ) | โครงแพ็กเก็ต ESP-NOW ใช้ร่วมสองบอร์ด แก้ต้องแก้ทั้งคู่ |
| `board/pio-node.ini` | VS Code / terminal | ทางเลือก: คอมไพล์ node ด้วย PlatformIO (`pio run -c pio-node.ini`) |
| `board/pio-gateway.ini` | VS Code / terminal | ทางเลือก: คอมไพล์ gateway (`pio run -c pio-gateway.ini`) |

ลำดับอัปโหลด: **gateway ก่อน** → เปิด Serial Monitor 115200 จดช่อง Wi-Fi ที่พิมพ์ →
เอาไปใส่ `NODE_CHANNEL` → อัปโหลด node

หมายเหตุ: ถ้าเปิด `gateway.ino` แล้ว Arduino IDE ฟ้องหา `esp_camera.h` ให้ติดตั้ง
`esp32-camera` (Espressif) ก่อน หรือตั้ง `WEARWISE_CAMERA 0` ใน `config.h`

### ทางเลือก: คอมไพล์ด้วย PlatformIO (ไม่ต้องใช้ Arduino IDE)

```bash
pip install platformio
cd board
pio run -c pio-node.ini            # ตรวจว่า node คอมไพล์ผ่าน
pio run -c pio-gateway.ini         # ตรวจว่า gateway คอมไพล์ผ่าน
pio run -c pio-gateway.ini -t upload
pio device monitor -c pio-gateway.ini
```

มี 2 ไฟล์เพราะ PlatformIO ตั้ง `src_dir` ได้ระดับโปรเจกต์เท่านั้น (`pio-node.ini` ชี้
`sensor_node/`, `pio-gateway.ini` ชี้ `gateway/`) ไลบรารีติดตั้งเองจาก `lib_deps`

---

## `cloud/` — FastAPI + Google Sheets/SQLite

| ไฟล์ | เปิดด้วย | ต้องแก้อะไร |
|---|---|---|
| `cloud/README.md` | VS Code | วิธีตั้ง Sheets, รายการ endpoint |
| `cloud/app.py` | VS Code | เส้นทาง HTTP หลัก (`/cloud/rows`, `/api/state`, `/api/estop`) |
| `cloud/store.py` | VS Code | เลือก backend Sheets/SQLite + คิวเขียนเบื้องหลัง |
| `cloud/config.py` | VS Code | อ่าน `.env` และรายการ `WARDROBE` (ชื่อผ้า **ต้องตรงกับ `ai/garment.py`**) |
| `cloud/notify.py` | VS Code | ส่ง Discord webhook |
| `cloud/requirements.txt` | VS Code | ติดตั้งด้วย `pip install -r requirements.txt` |
| `cloud/apps_script.gs` | **เบราว์เซอร์**: เปิดสเปรดชีต → Extensions → Apps Script → วางทับ → Deploy > New deployment (Web app, Anyone) → คัดลอก URL `/exec` | ไม่ต้องเปิดใน VS Code |
| `cloud/.env.example` | VS Code → **คัดลอกเป็น `.env`** | แม่แบบค่า config ทั้งหมด |
| `cloud/.env` | VS Code | ไฟล์จริงที่ใส่ค่า — gitignore ไว้ |

เปิด service:

```bash
cd cloud
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

ทดสอบในเบราว์เซอร์: <http://127.0.0.1:8000/health> และ <http://127.0.0.1:8000/api/state>

---

## `ai/` — FastAPI + OpenCV

| ไฟล์ | เปิดด้วย | ต้องแก้อะไร |
|---|---|---|
| `ai/README.md` | VS Code | วิธีเลือก backend YOLO/HOG, ข้อจำกัดความแม่นยำ |
| `ai/app.py` | VS Code | endpoint `POST /ai/aim`, `GET /health` |
| `ai/detector.py` | VS Code | ตรวจจับคน (YOLO ถ้าติดตั้ง ultralytics / ไม่งั้น OpenCV HOG) |
| `ai/garment.py` | VS Code | จำแนกชนิด+สีเสื้อผ้า, รายการ `WARDROBE` ต้องตรงกับ `cloud/config.py` |
| `ai/config.py` | VS Code | อ่าน `.env` (`AI_BACKEND`, `AI_CONF`, token) |
| `ai/requirements.txt` | VS Code | เปิดคอมเมนต์ `torch`/`ultralytics` ถ้าต้องการโมเดลจริง |
| `ai/.env.example` → `.env` | VS Code | คัดลอกแล้วแก้ (ไม่บังคับ) |

เปิด service:

```bash
cd ai
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8001
```

ทดสอบ: <http://127.0.0.1:8001/health> บอกว่าใช้ `hog` หรือ `yolo` อยู่

---

## `web_dashboard/` — หน้าเว็บ + proxy

| ไฟล์ | เปิดด้วย | ต้องแก้อะไร |
|---|---|---|
| `web_dashboard/README.md` | VS Code | ภาพรวมและค่า env |
| `web_dashboard/server.py` | VS Code | proxy ไป cloud/AI, เสิร์ฟไฟล์ static, `/api/estop` |
| `web_dashboard/config.py` | VS Code | อ่าน `.env` (`CLOUD_URL`, `AI_URL`, `INGEST_TOKEN`) |
| `web_dashboard/requirements.txt` | VS Code | `pip install -r requirements.txt` |
| `web_dashboard/static/index.html` | VS Code (หรือเปิดผ่าน server ที่ `http://127.0.0.1:8080/`) | โครงหน้า — **อย่าดับเบิลคลิกไฟล์ตรง ๆ** เพราะ `fetch('/api/state')` จะพัง |
| `web_dashboard/static/app.js` | VS Code | วาดข้อมูล, ปุ่ม E-stop, poll ทุก 2 วินาที |
| `web_dashboard/static/styles.css` | VS Code | หน้าตา/ธีม |
| `web_dashboard/.env.example` → `.env` | VS Code | คัดลอกแล้วแก้ (ไม่บังคับ) |

เปิด service:

```bash
cd web_dashboard
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8080
```

แล้วเปิดเบราว์เซอร์: <http://127.0.0.1:8080>

---

## เปิดอะไร ที่พอร์ตไหน

| ที่อยู่ | คืออะไร |
|---|---|
| <http://127.0.0.1:8080> | dashboard (เปิดอันนี้) |
| <http://127.0.0.1:8000/health> | cloud |
| <http://127.0.0.1:8000/api/state> | JSON รวมสำหรับ dashboard |
| <http://127.0.0.1:8001/health> | AI (บอก backend ที่ใช้) |
| `http://<IP-ESP32>/status` | สถานะ gateway (WebServer พอร์ต 80) |
| `http://<IP-ESP32>/estop` | ยิงหยุดฉุกเฉินตรงที่บอร์ด |

## ลำดับที่ควรเปิด (แบบไม่ใช้ Docker)

1. `cloud` (8000) — เปิดก่อน dashboard จะได้ไม่ขึ้น error
2. `ai` (8001)
3. `web_dashboard` (8080)
4. อัปโหลด `gateway` แล้ว `sensor_node`

## ไฟล์ที่ห้าม commit / ห้ามส่งในรายงาน

`.env`, `board/gateway/secrets.h`, `cloud/service-account.json`, `*.db`
(ถูก `.gitignore` ไว้แล้ว — ถ้า `git status` เห็นไฟล์พวกนี้ ให้ตรวจ `.gitignore` ก่อน)
