# ต่อ OV7670 กับ ESP32-S3 (N16R8)

สรุปการต่อสายและการตั้งค่าที่ทดสอบผ่านแล้ว (ได้เฟรมสี 320×240 = 153,600 ไบต์)

## 1. ตารางต่อสาย

| ขา OV7670 | ขา ESP32-S3 |
|---|---|
| 3.3V | 3V3 |
| GND | GND |
| SIOD (SDA) | GPIO 4 |
| SIOC (SCL) | GPIO 5 |
| XCLK | GPIO 15 |
| PCLK | GPIO 13 |
| VSYNC | GPIO 6 |
| HREF | GPIO 7 |
| D0 | GPIO 11 |
| D1 | GPIO 9 |
| D2 | GPIO 8 |
| D3 | GPIO 10 |
| D4 | GPIO 12 |
| D5 | GPIO 18 |
| D6 | GPIO 17 |
| D7 | GPIO 16 |
| RESET | 3.3V |
| PWDN | GND |

## 2. ข้อควรจำเรื่องฮาร์ดแวร์

- ใช้ไฟ **3.3V เท่านั้น** ห้ามต่อ 5V
- ใช้สายสั้นที่สุดเท่าที่ทำได้ โดยเฉพาะ PCLK, HREF, VSYNC, XCLK
- ขาที่ไม่ควรใช้บน S3 รุ่น N16R8: GPIO 26-32 (flash), 33-37 (PSRAM แบบ octal), 19-20 (USB) และ 0/3/45/46 (strapping) ตารางด้านบนเลี่ยงขากลุ่มนี้แล้ว

## 3. ตั้งค่า Arduino IDE

| รายการ | ค่า |
|---|---|
| Board package | esp32 by Espressif เวอร์ชัน **2.0.17** |
| Board | ESP32S3 Dev Module |
| PSRAM | **Disabled** |
| Flash Size | 16MB (128Mb) |
| USB CDC On Boot | Enabled |
| Core Debug Level | Error ตอนทดสอบ, **None** ตอนส่งภาพเข้าคอม |

หมายเหตุ:

- ใช้ core 2.0.17 เพราะ core รุ่นใหม่ (3.x/4.x) อ่านรีจิสเตอร์ OV7670 ไม่ได้ (`SCCB_Read failed` แล้วขึ้น `0x106`)
- ปิด PSRAM เพราะภาพสี QVGA ใช้ RAM ภายในพอ (ก้อนใหญ่สุดที่เหลือ ~327 KB) และตอนเปิด OPI PSRAM บอร์ดค้างแล้วรีเซ็ตวน (ยังไม่ได้หาสาเหตุ)
- เสียบสายที่ช่อง **USB (native)** ตอนใช้งาน เพราะ USB CDC On Boot ทำให้ข้อความและภาพออกที่ช่องนี้

## 4. ประเด็นสำคัญในโค้ด

เปิด XCLK เองก่อนเรียกไดรเวอร์ แล้วตั้ง `pin_xclk = -1` ไม่งั้นไดรเวอร์หากล้องไม่เจอ (`0x105`):

```cpp
ledcSetup(0, 10000000, 1);   // XCLK 10 MHz
ledcAttachPin(15, 0);        // GPIO 15
ledcWrite(0, 1);
delay(300);                  // รอให้กล้องพร้อม

config.ledc_channel = LEDC_CHANNEL_1;
config.ledc_timer   = LEDC_TIMER_1;
config.pin_xclk     = -1;    // ไดรเวอร์ไม่สร้าง XCLK เอง
config.pin_sscb_sda = 4;
config.pin_sscb_scl = 5;
config.pixel_format = PIXFORMAT_RGB565;
config.frame_size   = FRAMESIZE_QVGA;   // 320x240
config.fb_location  = CAMERA_FB_IN_DRAM;
```

## 5. อัปโหลดไม่ติด (ESP32-S3)

- ตั้ง Upload Speed เป็น 115200
- กด **BOOT** ค้าง → กด **RESET** → ปล่อย **BOOT** → กด Upload (เลข COM อาจเปลี่ยน ให้เลือกตามที่ขึ้นใหม่)
- ถอดสายกล้องออกชั่วคราวตอนอัปโหลด
- ใช้สาย USB ที่ส่งข้อมูลได้ เสียบพอร์ตหลังเครื่องคอมโดยตรง

## 6. อาการที่เคยเจอและรหัส error

| อาการ / รหัส | ความหมายที่พบ |
|---|---|
| `0x105` (ไม่พบกล้อง) | ไดรเวอร์เริ่ม XCLK ไม่ทัน แก้ด้วยการเปิด XCLK เองตามข้อ 4 |
| `0x106` (not supported) | บน core 3.x/4.x อ่าน PID ของ OV7670 ไม่ได้ ใช้ core 2.0.17 |
| `FB-SIZE: ... != ...` | เกิดบน ESP32 รุ่นเดิมที่ไม่มี PSRAM (ไม่เจอบน S3 ในการทดสอบนี้) |
| บอร์ดบูตวน `rst:0x8 (TG1WDT_SYS_RST)` | เกิดตอนเปิด OPI PSRAM แล้วเรียกกล้อง ให้ปิด PSRAM |
| ภาพฉีกเป็นแถบ | เกิดจากไบต์หล่นบนลิงก์ serial ของ ESP32 รุ่นเดิม แก้ด้วยการส่งทีละบรรทัดพร้อม checksum |