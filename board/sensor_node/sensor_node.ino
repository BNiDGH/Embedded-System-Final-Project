/*
 * WearWise sensor node NA709 (ESP32)
 *
 * อ่าน DHT22 (อุณหภูมิ/ความชื้น), MQ-135 (ก๊าซ), BH1750 (แสง)
 * แล้วส่งผ่าน ESP-NOW ไปยัง gateway พร้อม ack/retry และคิวสำรองในหน่วยความจำ
 *
 * FreeRTOS: 3 task
 *   taskSample  คิวออกแบบ priority 1  อ่านเซนเซอร์ทุก SAMPLE_INTERVAL_MS
 *   taskTx      priority 2            ส่ง ESP-NOW + รอ ack + ส่งซ้ำ
 *   taskStats   priority 1            heartbeat ทาง Serial (ไม่บล็อกงานส่ง)
 *
 * ไลบรารี (Arduino IDE Library Manager)
 *   - DHT sensor library (Adafruit) + Adafruit Unified Sensor
 *   - BH1750 (Christopher Laws)
 *
 * ใช้ ESP32 Arduino core 2.x หรือ 3.x (callback ESP-NOW รองรับทั้งสองเวอร์ชัน)
 */

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <DHT.h>
#include <Wire.h>
#include <BH1750.h>

#include "config.h"
#include "../common/wearwise_protocol.h"

static DHT dht(DHT_PIN, DHT_TYPE);
static BH1750 lightMeter(0x23);

static QueueHandle_t txQueue = nullptr;

// ค่าที่ callback ฝั่งรับ ack เขียนไว้ (volatile เพราะอยู่นอก task)
static volatile uint32_t ackSeq = 0;
static volatile bool ackFan = false;
static volatile bool ackEstop = false;
static volatile uint32_t ackAtMs = 0;

static uint32_t seqCounter = 0;
static float lastRttMs = 0.0f;
static bool hasLastReading = false;
static float lastTemp = 0.0f;
static float lastHum = 0.0f;

static const uint8_t BROADCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// ---------------------------------------------------------------- ESP-NOW

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
static void onDataRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
#else
static void onDataRecv(const uint8_t *mac, const uint8_t *data, int len) {
#endif
  if (len < (int)sizeof(AckPacket)) return;
  AckPacket ack;
  memcpy(&ack, data, sizeof(ack));
  if (ack.magic != WEARWISE_MAGIC || ack.type != MSG_ACK) return;
  if (strncmp(ack.node_id, NODE_ID, sizeof(ack.node_id)) != 0) return;
  ackSeq = ack.ack_seq;
  ackFan = ack.fan != 0;
  ackEstop = ack.estop != 0;
  ackAtMs = millis();
}

static bool espnowBegin() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  // ตั้ง channel ให้ตรงกับ gateway ก่อนเริ่ม ESP-NOW
  esp_wifi_set_channel(NODE_CHANNEL, WIFI_SECOND_CHAN_NONE);

  if (esp_now_init() != ESP_OK) return false;
  esp_now_register_recv_cb(onDataRecv);

  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, BROADCAST, 6);
  peer.channel = NODE_CHANNEL;
  peer.encrypt = false;
  if (!esp_now_is_peer_exist(BROADCAST)) {
    if (esp_now_add_peer(&peer) != ESP_OK) return false;
  }
  return true;
}

// ------------------------------------------------------------- เซนเซอร์

static float readGasPpm() {
  if (millis() < MQ135_WARMUP_MS) return 0.0f;  // ยังอุ่นไม่ครบ ให้ค่า 0 แทนค่าผิด

  uint32_t sum = 0;
  for (int i = 0; i < 16; i++) {
    sum += analogRead(MQ135_PIN);
    delay(2);
  }
  float volts = (sum / 16.0f) * (MQ135_VCC / MQ135_ADC_MAX);
  if (volts < 0.01f) return 0.0f;

  // Rs จากวงจรแบ่งแรงดันของโมดูล MQ-135 แล้วเทียบกับ R0 ที่คาลิเบรตไว้
  float rs = ((MQ135_VCC - volts) / volts) * MQ135_RL_KOHM;
  float ratio = rs / MQ135_R0_KOHM;
  if (ratio <= 0.0f) return 0.0f;

  // เส้นโค้งมาตรฐานของ MQ-135 (ประมาณค่า CO2/NH3 โดยสรุปเป็น ppm รวม)
  float ppm = 116.6020682f * powf(ratio, -2.769034857f);
  return isnan(ppm) ? 0.0f : ppm;
}

static void fillPacket(SensorPacket &p) {
  memset(&p, 0, sizeof(p));
  p.magic = WEARWISE_MAGIC;
  p.type = MSG_SENSOR;
  strncpy(p.node_id, NODE_ID, sizeof(p.node_id) - 1);
  p.seq = ++seqCounter;
  p.uptime_ms = millis();
  p.rtt_ms = lastRttMs;
  p.retries = 0;

  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (!isnan(t) && !isnan(h)) {
    lastTemp = t;
    lastHum = h;
    hasLastReading = true;
  }
  // อ่านไม่สำเร็จใช้ค่าเดิม ไม่ส่ง NaN ขึ้น cloud
  p.temp = hasLastReading ? lastTemp : 0.0f;
  p.hum = hasLastReading ? lastHum : 0.0f;

  float lux = lightMeter.readLightLevel();
  p.lux = (isnan(lux) || lux < 0) ? 0.0f : lux;
  p.gas = readGasPpm();
}

// ---------------------------------------------------------------- การส่ง

// ส่งหนึ่งแพ็กเก็ต รอ ack ของ seq นั้น ไม่เกิน ACK_TIMEOUT_MS ต่อครั้ง
static bool sendWithAck(SensorPacket p) {
  for (uint8_t attempt = 0; attempt < TX_RETRY_MAX; attempt++) {
    p.retries = attempt;
    uint32_t sentAt = millis();
    ackSeq = 0;

    if (esp_now_send(BROADCAST, (uint8_t *)&p, sizeof(p)) == ESP_OK) {
      while (millis() - sentAt < ACK_TIMEOUT_MS) {
        if (ackSeq == p.seq) {
          lastRttMs = (float)(millis() - sentAt);
          return true;
        }
        vTaskDelay(pdMS_TO_TICKS(4));
      }
    } else {
      vTaskDelay(pdMS_TO_TICKS(20));
    }
  }
  return false;
}

static void taskSample(void *) {
  for (;;) {
    SensorPacket p;
    fillPacket(p);

    if (xQueueSend(txQueue, &p, pdMS_TO_TICKS(200)) != pdTRUE) {
      SensorPacket dropped;
      xQueueReceive(txQueue, &dropped, 0);  // คิวเต็ม = ทิ้งของเก่าสุด กันหน่วยความจำบวม
      xQueueSend(txQueue, &p, 0);
      Serial.println("[node] คิวเต็ม: ทิ้งแพ็กเก็ตเก่าสุด");
    }
    vTaskDelay(pdMS_TO_TICKS(SAMPLE_INTERVAL_MS));
  }
}

static void taskTx(void *) {
  for (;;) {
    SensorPacket p;
    if (xQueuePeek(txQueue, &p, portMAX_DELAY) != pdTRUE) continue;

    if (sendWithAck(p)) {
      xQueueReceive(txQueue, &p, 0);  // ได้ ack แล้วเอาออกจากคิว
      Serial.printf("[%s#%lu] temp=%.1f hum=%.1f gas=%.0f lux=%.0f ack rtt=%.1f ms fan=%s\n",
                    NODE_ID, (unsigned long)p.seq, p.temp, p.hum, p.gas, p.lux,
                    lastRttMs, ackFan ? "ON" : "off");
    } else {
      // เก็บไว้ที่หัวคิวแล้วลองรอบหน้า (store-and-forward ฝั่ง node)
      Serial.printf("[%s#%lu] ไม่ได้ ack (ค้าง %d) จะส่งซ้ำ\n",
                    NODE_ID, (unsigned long)p.seq, uxQueueMessagesWaiting(txQueue));
      vTaskDelay(pdMS_TO_TICKS(500));
    }
  }
}

static void taskStats(void *) {
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(15000));
    Serial.printf("[node] heap=%u bytes, queued=%u, estop=%s\n",
                  (unsigned)ESP.getFreeHeap(),
                  (unsigned)uxQueueMessagesWaiting(txQueue),
                  ackEstop ? "YES" : "no");
  }
}

// ------------------------------------------------- โหมดหลับ (ถ้าเปิดใช้)

static void runOnceAndSleep() {
  SensorPacket p;
  fillPacket(p);
  bool ok = sendWithAck(p);
  Serial.printf("[node] one-shot %s, %.1f ms -> deep sleep %ds\n",
                ok ? "ACK" : "FAIL", lastRttMs, DEEP_SLEEP_S);
  Serial.flush();
  esp_sleep_enable_timer_wakeup((uint64_t)DEEP_SLEEP_S * 1000000ULL);
  esp_deep_sleep_start();
}

// ---------------------------------------------------------------- setup

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("\n[%s] WearWise sensor node (DHT22, MQ-135, BH1750)\n", NODE_ID);

  pinMode(STATUS_LED, OUTPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(MQ135_PIN, ADC_11db);

  Wire.begin(I2C_SDA, I2C_SCL);
  dht.begin();
  if (!lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
    Serial.println("[node] BH1750 ไม่ตอบสนอง ตรวจสาย I2C");
  }

  if (!espnowBegin()) {
    Serial.println("[node] เริ่ม ESP-NOW ไม่ได้ กำลังรีสตาร์ต");
    delay(3000);
    ESP.restart();
  }
  Serial.println("[node] ESP-NOW พร้อม (broadcast mode)");

  if (DEEP_SLEEP_S > 0) {
    runOnceAndSleep();
    return;
  }

  txQueue = xQueueCreate(TX_QUEUE_LEN, sizeof(SensorPacket));
  xTaskCreatePinnedToCore(taskSample, "sample", 4096, nullptr, 1, nullptr, 1);
  xTaskCreatePinnedToCore(taskTx, "espnow_tx", 4096, nullptr, 2, nullptr, 0);
  xTaskCreatePinnedToCore(taskStats, "stats", 2560, nullptr, 1, nullptr, 1);
  Serial.println("[node] tasks started");
}

void loop() {
  // งานทั้งหมดอยู่ใน FreeRTOS task; loop ใช้แค่กระพริบ LED ให้เห็นว่าบอร์ดยังทำงาน
  static uint32_t nextBlink = 0;
  if (millis() >= nextBlink) {
    digitalWrite(STATUS_LED, !digitalRead(STATUS_LED));
    nextBlink = millis() + (ackEstop ? 200 : 1000);
  }
  vTaskDelay(pdMS_TO_TICKS(50));
}
