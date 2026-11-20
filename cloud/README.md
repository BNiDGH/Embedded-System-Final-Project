# cloud/ — รับข้อมูลและเก็บลง cloud จริง

FastAPI service รับข้อมูลจาก gateway, เก็บลง Google Sheets หรือ SQLite,
ส่งแจ้งเตือน Discord และให้ dashboard อ่านสถานะ

## ติดตั้งและรัน

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

ตรวจ: <http://127.0.0.1:8000/health>

## ตั้ง Google Sheets (ไม่บังคับ)

ถ้าไม่ตั้งอะไรเลย ข้อมูลจะลง `cloud.db` (SQLite) ซึ่งใช้เดโมได้ทันที

**ทางที่ง่าย: Apps Script**

1. เปิดสเปรดชีตใหม่ → Extensions → Apps Script → วาง `apps_script.gs`
2. Deploy → New deployment → Web app, Execute as: Me, Who has access: Anyone
3. คัดลอก URL `/exec` ใส่ `.env` เป็น `GOOGLE_SCRIPT_URL`
4. แก้โค้ดสคริปต์แล้วต้อง deploy เวอร์ชันใหม่ทุกครั้ง

**ทางเลือก: service account**

1. เปิด Google Sheets API, สร้าง service account + key JSON
2. เก็บเป็น `service-account.json` (gitignore) แล้วแชร์ชีตให้อีเมล service account เป็น Editor
3. ใส่ `GOOGLE_SHEET_ID` และ `GOOGLE_SERVICE_ACCOUNT_FILE`

Apps Script ใช้เวลา 2–5 วินาทีต่อการเขียนหนึ่งแถว service นี้จึงตอบ gateway ทันที
แล้วเขียนชีตในเธรดเบื้องหลัง พร้อมสำเนา SQLite ให้ dashboard อ่านได้ตลอด
ถ้าคิวค้าง dashboard จะขึ้น "รอเขียนลงชีตอีก N แถว"

## API

| method | path | ใช้โดย | หมายเหตุ |
|---|---|---|---|
| POST | `/cloud/rows` | gateway | ทีละแถวหรือ `{"rows":[...]}` |
| POST | `/cloud/events` | gateway | ส่ง Discord ถ้า `kind` อยู่ใน `NOTIFY_KINDS` |
| POST | `/api/pick` | gateway | นับครั้งหยิบ; cooldown ตาม `PICK_COOLDOWN_S` |
| GET | `/api/state` | dashboard | ข้อมูลรวม + รายชื่อบอร์ด + ยอดเสื้อผ้า |
| POST | `/api/estop` | dashboard | ส่งต่อไปยัง `GATEWAY_URL/estop` |
| POST | `/api/reset` | dashboard | ล้างยอด; โหมด SQLite ล้างแถวด้วย |

ทุก endpoint ที่รับข้อมูล (ยกเว้น state) ตรวจ `X-Auth-Token` ถ้าตั้ง `INGEST_TOKEN`

## จำนวนครั้งที่หยิบ

gateway ส่ง `/api/pick` เฉพาะตอน "ไม่มีคน → มีคน" (rising edge) แล้ว cloud
ยังกันนับซ้ำด้วย cooldown 5 วินาทีต่อ node ยอดเก็บในตาราง `wardrobe`
(ชื่อต้องตรงกับ `ai/garment.py` ถ้า AI คืนชื่อใหม่ cloud จะเพิ่มแถวให้เอง)

## ไฟล์

- `app.py` — HTTP API
- `store.py` — ชั้นเก็บข้อมูล (Apps Script / service account / SQLite)
- `notify.py` — Discord
- `apps_script.gs` — โค้ดฝั่ง Google Apps Script
