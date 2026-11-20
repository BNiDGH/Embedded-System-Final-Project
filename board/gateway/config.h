/*
 * Gateway CB302 configuration
 *
 * Wi-Fi/cloud secrets: คัดลอก secrets.h.example เป็น secrets.h แล้วเติมค่า
 * (secrets.h ถูก gitignore ไว้ ไม่ให้รหัสผ่านขึ้น Git — E5)
 */
#pragma once

#if __has_include("secrets.h")
#include "secrets.h"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID "CHANGE_ME"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "CHANGE_ME"
#endif
#ifndef CLOUD_URL
#define CLOUD_URL "http://192.168.1.50:8000"
#endif
#ifndef AI_URL
#define AI_URL "http://192.168.1.50:8001"
#endif
#ifndef API_TOKEN
#define API_TOKEN ""  // ต้องตรงกับ INGEST_TOKEN ใน cloud/.env (เว้นว่าง = ไม่ตรวจ)
#endif

#define GATEWAY_ID "CB302"

// ---------- ขา GPIO (ESP32-S3) ----------
#define TRIG_PIN 9
#define ECHO_PIN 10
#define FAN_RELAY_PIN 11
#define RELAY_ACTIVE_LEVEL HIGH   // โมดูลรีเลย์ส่วนมาก active HIGH; ถ้าใช้ active LOW ให้แก้เป็น LOW
#define SERVO_PIN 12

// ---------- actuator ----------
#define SERVO_MIN 20
#define SERVO_MAX 160
#define SERVO_SAFE 90

// ---------- ตรรกะพัดลม (อยู่บน gateway จึงตอบสนองได้ทันที) ----------
#define HUM_ON 75.0f
#define HUM_OFF 65.0f
#define GAS_ON 450.0f
#define GAS_OFF 350.0f
#define FAN_MAX_ON_MS (180UL * 1000UL)
#define NODE_TIMEOUT_MS (10UL * 1000UL)

// ---------- จังหวะงาน ----------
#define CONTROL_INTERVAL_MS 200
#define GATEWAY_ROW_MS 2000
#define AI_INTERVAL_MS 4000
#define PERSON_CM 80.0f
#define HTTP_TIMEOUT_MS 5000
#define SPOOL_MAX_JOBS 200

/*
 * ---------- กล้อง OV7670 ----------
 * WEARWISE_CAMERA 0 = ปิดกล้อง (ระบบยังทำงานได้ แต่ M4 closed loop จะไม่มี)
 *
 * OV7670 ไม่มี JPEG encoder จึงตั้ง pixel format เป็น RGB565 แล้วให้
 * frame2jpg() แปลงก่อนส่งให้ AI ฝั่ง server
 *
 * ขาต่อไปนี้เป็นค่าตั้งต้น ต้องแก้ให้ตรงกับสายจริงของแต่ละกลุ่ม
 * และหลีกเลี่ยง GPIO 33-37 บนบอร์ดที่มี PSRAM แบบ octal
 */
#define WEARWISE_CAMERA 1
#define CAM_PIN_PWDN -1
#define CAM_PIN_RESET -1
#define CAM_PIN_XCLK 15
#define CAM_PIN_SIOD 16
#define CAM_PIN_SIOC 17
#define CAM_PIN_VSYNC 18
#define CAM_PIN_HREF 19
#define CAM_PIN_PCLK 20
#define CAM_PIN_D0 4
#define CAM_PIN_D1 5
#define CAM_PIN_D2 6
#define CAM_PIN_D3 7
#define CAM_PIN_D4 13
#define CAM_PIN_D5 14
#define CAM_PIN_D6 21
#define CAM_PIN_D7 38
