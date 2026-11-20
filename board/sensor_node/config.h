/*
 * Sensor node NA709: DHT22 + MQ-135 + BH1750 บน ESP32
 *
 * แก้ขาให้ตรงกับสายที่ต่อจริง ถ้าใช้บอร์ดอื่นให้ปรับ MQ135_ADC_MAX เป็น 4095 (ESP32)
 * หมายเหตุ: node ไม่ต้องต่อ Wi-Fi อินเทอร์เน็ต ใช้ ESP-NOW คุยกับ gateway เท่านั้น
 *           จึงไม่มีรหัส Wi-Fi เก็บอยู่ในเฟิร์มแวร์ของ node
 */
#pragma once

#define NODE_ID "NA709"

// ต้องตรงกับช่อง Wi-Fi ของ gateway (gateway ปริ๊นต์ค่าตอนบูต)
// ESP-NOW กับ Wi-Fi ใช้วิทยุตัวเดียวกัน จึงต้องอยู่ช่องเดียวกัน
#define NODE_CHANNEL 1

// ---------- ขาเซนเซอร์ ----------
#define DHT_PIN 4
#define DHT_TYPE DHT22
#define MQ135_PIN 34          // ต้องเป็น ADC1 (GPIO32-39) จึงจะอ่านได้ขณะ Wi-Fi เปิด
#define I2C_SDA 21
#define I2C_SCL 22
#define STATUS_LED 2

// ---------- MQ-135 ----------
// R0 ต้องคาลิเบรตในอากาศสะอาด (ปกติ 5-20 kOhm) ค่าเริ่มต้นเป็นค่าตัวอย่าง
#define MQ135_R0_KOHM 10.0f
#define MQ135_RL_KOHM 10.0f
#define MQ135_ADC_MAX 4095.0f
#define MQ135_VCC 3.3f
#define MQ135_WARMUP_MS (180UL * 1000UL)  // เซนเซอร์ต้องอุ่นก่อนอ่านค่าจริง

// ---------- จังหวะการทำงาน ----------
#define SAMPLE_INTERVAL_MS 2000
#define ACK_TIMEOUT_MS 150
#define TX_RETRY_MAX 5
#define TX_QUEUE_LEN 24

// 0 = ทำงานต่อเนื่อง (ค่าเริ่มต้น) / > 0 = ตื่นมาอ่าน-ส่ง-หลับ (โหมดประหยัดไฟ)
// ถ้าเปิดโหมดหลับ ต้องวัดกระแสจริงและรายงานในเล่มด้วย (E3)
#define DEEP_SLEEP_S 0
