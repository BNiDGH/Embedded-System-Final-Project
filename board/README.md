# WearWise — board firmware (ของจริง)

เฟิร์มแวร์ ESP32 สองบอร์ด ใช้แทน `mock_node.py` / `mock_gateway.py` ในชุดจำลอง

| บอร์ด | ไฟล์เปิดใน Arduino IDE | หน้าที่ |
|---|---|---|
| Sensor node NA709 (ESP32) | `sensor_node/sensor_node.ino` | DHT22 + MQ-135 + BH1750 → ESP-NOW + ack/retry |
| Gateway CB302 (ESP32-S3) | `gateway/gateway.ino` | ESP-NOW RX, HC-SR04, พัดลม, servo, OV7670, ขึ้น cloud |

## อุปกรณ์

**Sensor node**

| อุปกรณ์ | ขา | หมายเหตุ |
|---|---|---|
| DHT22 | GPIO 4 | ดึงขึ้น 10 kΩ |
| MQ-135 (AO) | GPIO 34 | ต้องเป็น ADC1 |
| BH1750 (SDA/SCL) | GPIO 21 / 22 | I²C address 0x23 |
| LED สถานะ | GPIO 2 | กระพริบ = ยังทำงาน |

**Gateway (ESP32-S3)**

| อุปกรณ์ | ขา | หมายเหตุ |
|---|---|---|
| HC-SR04 TRIG / ECHO | GPIO 9 / 10 | ECHO ผ่าน ISR (ไม่ busy-poll) |
| รีเลย์พัดลม | GPIO 11 | active HIGH (แก้ `RELAY_ACTIVE_LEVEL` ได้) |
| Servo | GPIO 12 | 50 Hz, ช่วง 500–2400 µs |
| OV7670 | ดู `gateway/config.h` | ต้องแก้ให้ตรงสายจริง + เปิด PSRAM |

พัดลมใช้รีเลย์/มอสเฟตแยกไฟเลี้ยง ห้ามต่อ mains ลอย ๆ ตามกฎความปลอดภัย M7

## อีกทาง: คอมไพล์ด้วย PlatformIO (ไม่ต้องเปิด Arduino IDE)

มีไฟล์ config ให้แล้ว 2 ไฟล์ (แยกเพราะ `src_dir` ตั้งได้ระดับโปรเจกต์เท่านั้น)

```bash
pip install platformio
pio run -c pio-node.ini          # sensor node
pio run -c pio-gateway.ini       # gateway
pio run -c pio-gateway.ini -t upload
pio device monitor -c pio-gateway.ini
```

ไลบรารีถูกติดตั้งอัตโนมัติตาม `lib_deps` (ArduinoJson, ESP32Servo, DHT, BH1750,
esp32-camera จาก GitHub) — ไฟล์ `.ino`/`.h` ชุดเดียวกับที่เปิดใน Arduino IDE
ทั้งสอง env คอมไพล์ผ่าน (Espressif 32 platform 7.1.1 / Arduino core 2.0.17):
node Flash 58%, gateway Flash 32%

## ไลบรารีที่ต้องติดตั้ง

Library Manager: `DHT sensor library` (Adafruit) + `Adafruit Unified Sensor`,
`BH1750` (Christopher Laws), `ArduinoJson` (bennn 6.x), `ESP32Servo`,
`esp32-camera` (Espressif — ติดตั้งผ่าน GitHub/ZIP ถ้า Library Manager ไม่มี)

## วิธีตั้งค่าและอัปโหลด

1. **Gateway**: คัดลอก `gateway/secrets.h.example` → `gateway/secrets.h`
   แล้วใส่ SSID/รหัส Wi-Fi, IP ของเครื่องที่รัน cloud+AI และ `API_TOKEN`
   (`secrets.h` ถูก ignore ไม่ขึ้น Git)
2. เปิด `sensor_node/sensor_node.ino` เลือกบอร์ด ESP32 Dev Module
3. เปิด `gateway/gateway.ino` เลือกบอร์ด ESP32S3 Dev Module
   เปิด `PSRAM: OPI PSRAM` ถ้าใช้กล้อง
4. อัปโหลด gateway ก่อน แล้วดู Serial: จะพิมพ์ช่อง Wi-Fi ที่ใช้
5. ตั้ง `NODE_CHANNEL` ใน `sensor_node/config.h` ให้ตรงช่องนั้น
   (ESP-NOW กับ Wi-Fi ใช้วิทยุเดียวกัน จึงต้องอยู่ช่องเดียวกัน) แล้วอัปโหลด node

## คาลิเบรต MQ-135

`MQ135_R0_KOHM` ตั้งต้น 10 kΩ เป็นเพียงค่าตัวอย่าง ให้ทำตามนี้

1. เปิดบอร์ดในอากาศสะอาด อุ่น 3 นาที
2. อ่าน `Rs` จาก Serial หรือคำนวณจากแรงดัน AO
3. R0 = Rs ในอากาศสะอาด แล้วใส่ค่าใน `config.h`
4. ถ้าค่า ppm ยังเพี้ยน ให้เทียบกับเซนเซอร์อ้างอิงแล้วปรับ `MQ135_RL_KOHM` ตามโมดูลจริง

## สิ่งที่เฟิร์มแวร์ทำจริง (ไม่ใช่จำลอง)

- **Reliable link (E4)**: node ส่ง ESP-NOW แล้วรอ `AckPacket` ของ seq นั้น
  สูงสุด 5 ครั้ง; ไม่ได้ ack = เก็บที่หัวคิวแล้วส่งรอบหน้า; node รายงาน RTT
  ของ ack ล่าสุดในแพ็กเก็ตถัดไป (`rtt_ms`)
- **FreeRTOS (E1)**: node มี 3 task, gateway มี 4 task คุยกันด้วย queue
- **ISR (E2)**: ECHO ของ HC-SR04 วัดความกว้างพัลส์ใน ISR แล้วประมวลผลใน task
- **Real-time control**: พัดลมตัดสินบน gateway ด้วย hysteresis, timeout 10 s
  และตัดไฟเมื่อเปิดต่อเนื่องเกิน 180 s
- **AI closed loop (M4)**: gateway จับภาพ OV7670 → POST `/ai/aim` → ได้ `x_norm`
  → แปลงเป็นมุม servo (20°–160°) → สั่ง servo จริง
- **Store-and-forward (E4)**: ทุก payload ถูกเขียนลง LittleFS ก่อนส่งขึ้น cloud
  ถ้า Wi-Fi/cloud ล่มจะค้างในคิวและส่งเมื่อกลับมา (สูงสุด 200 งาน)
- **E-stop**: `POST /estop` ที่ gateway ปิดพัดลมทันทีและ servo กลับมุมปลอดภัย

## payload ที่ส่งขึ้น cloud

`POST /cloud/rows` (จาก gateway, ผ่าน spool)

```json
{"ts":1767000000.5,"node_id":"NA709","seq":12,"temp":27.4,"hum":58.2,
 "gas":310,"lux":120,"hop_ms":8.4,"note":"node -> gateway"}
```

`POST /cloud/rows` (แถวของ gateway เอง)

```json
{"ts":1767000002.1,"node_id":"CB302","seq":31,"dist_cm":48.0,"person":1,
 "fan":1,"servo":112,"estop":0,"hop_ms":0,"note":"ความชื้น 78% ถึงเกณฑ์เปิด"}
```

`POST /cloud/events` — `{"node_id","kind","text"}` โดย `kind` เป็น
`fan|ai|pick|estop|boot` และ cloud เป็นคนส่ง Discord ต่อ

`POST /api/pick` — `{"node_id":"CB302","label":"เสื้อยืดสีขาว"}` เมื่อมีคนเข้ามาใหม่
cloud จึงนับจำนวนครั้งและกันนับซ้ำด้วย cooldown

## Log ที่ควรเห็น

```
[node] ESP-NOW พร้อม (broadcast mode)
[NA709#12] temp=27.4 hum=58.2 gas=310 lux=120 ack rtt=8.4 ms fan=off
[net] WiFi connected 192.168.1.60 (channel 6) <- ตั้ง WEARWISE_CHANNEL ของ node เป็น 6
[rx] NA709#12 hum=58.2 gas=310 rtt=8.4 ms retry=0
[ai] AI เห็น เสื้อยืดสีขาว (93%) x=0.62 -> servo 107 องศา (96 ms)
```
