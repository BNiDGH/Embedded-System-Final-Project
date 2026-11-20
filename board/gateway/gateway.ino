/*
 * Gateway CB302 (ESP32-S3): HC-SR04 + OV7670 + พัดลม + servo
 *
 * ทำ 4 อย่างตามโจทย์
 *   1. รับ ESP-NOW จาก node แล้วตอบ ack (task espnow_rx)
 *   2. ตัดสินใจพัดลมเองแบบ real-time ด้วย hysteresis + timeout + max on-time (task control)
 *   3. ส่งภาพให้ AI แล้วเอา x_norm มาหมุน servo แบบ closed loop (task ai)
 *   4. ส่งข้อมูลดิบ/เหตุการณ์ขึ้น cloud พร้อม spool ลง flash เมื่อเน็ตหลุด (task net)
 *
 * ไลบรารี (Arduino IDE Library Manager)
 *   - ArduinoJson (bblanchon) 6.x
 *   - ESP32Servo (Kevin Harrington)
 *   - esp32-camera (Espressif) ถ้าใช้ OV7670 และบอร์ดมี PSRAM
 *
 * ตั้งค่า Wi-Fi / ที่อยู่ cloud / token ใน secrets.h (ดู secrets.h.example)
 *
 * หมายเหตุช่องสัญญาณ: gateway ต่อ Wi-Fi เราเตอร์ ลำคลื่นจึงเป็นช่องของ AP
 * ตั้ง WEARWISE_CHANNEL ฝั่ง node ให้ตรงกับช่องนี้ (ดูค่าที่ gateway ปริ๊นต์ตอนบูต)
 */

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <ESP32Servo.h>
#include <LittleFS.h>
#include <ArduinoJson.h>
#include <time.h>

#include "config.h"
#include "../common/wearwise_protocol.h"

#if WEARWISE_CAMERA
#include "esp_camera.h"
#include "img_converters.h"
#include <mbedtls/base64.h>
#endif

// ESP-NOW callback เปลี่ยนรูปแบบระหว่าง Arduino core 2.x กับ 3.x:
//   2.x  onEspNowRecv(const uint8_t *mac, const uint8_t *data, int len)
//   3.x  onEspNowRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len)
// ใช้ typedef ตัวเดียวเพื่อไม่ให้ Arduino สร้าง prototype จาก #if ผิดฝั่ง
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
typedef esp_now_recv_info_t wearwise_recv_info_t;
#else
typedef uint8_t wearwise_recv_info_t;  // 2.x: พารามิเตอร์แรกคือ MAC address
#endif

// ------------------------------------------------------------- สถานะกลาง

struct NodeState {
  bool valid = false;
  uint32_t lastSeen = 0;
  uint32_t seq = 0;
  float temp = 0, hum = 0, gas = 0, lux = 0, hopMs = 0;
  uint8_t retries = 0;
};

static NodeState nodeState;
static portMUX_TYPE nodeMux = portMUX_INITIALIZER_UNLOCKED;

static volatile bool estopOn = false;
static bool fanOn = false;
static uint32_t fanSince = 0;
static char fanReason[96] = "-";
static int servoAngle = SERVO_SAFE;
static int servoWritten = -1;
static uint32_t gatewaySeq = 0;
static bool timeSynced = false;

// ค่าจาก HC-SR04 ถูกเขียนโดย task control ที่เดียว task อื่นอ่านอย่างเดียว
static volatile bool personPresent = false;
static volatile float lastDistCm = 0.0f;

static QueueHandle_t rxQueue = nullptr;
static TaskHandle_t netTaskHandle = nullptr;
static WebServer web(80);
static Servo servo;

#if WEARWISE_CAMERA
static bool cameraReady = false;
#endif

// ------------------------------------------------------------ spool flash

/*
 * ทุกอย่างที่ต้องขึ้น cloud จะถูกเขียนลง flash ก่อน (store-and-forward)
 * ถ้าเน็ตหลุด ข้อมูลยังอยู่และจะถูกส่งเมื่อกลับมา (E4)
 */
static SemaphoreHandle_t spoolMux = nullptr;
static uint32_t spoolCounter = 0;

static int spoolCountLocked() {
  File dir = LittleFS.open("/spool");
  if (!dir) return 0;
  int n = 0;
  File f = dir.openNextFile();
  while (f) {
    if (!f.isDirectory()) n++;
    f = dir.openNextFile();
  }
  return n;
}

// ชื่อไฟล์เรียงตามเลขลำดับ การอ่าน/ลบ "ไฟล์แรก" จึงเป็นของเก่าสุดที่ยังไม่ส่ง
static String spoolOldestLocked() {
  File dir = LittleFS.open("/spool");
  if (!dir) return "";
  File f = dir.openNextFile();
  while (f) {
    if (!f.isDirectory()) return String("/spool/") + f.name();
    f = dir.openNextFile();
  }
  return "";
}

static void pushCloud(const char *path, const String &json) {
  if (xSemaphoreTake(spoolMux, pdMS_TO_TICKS(200)) != pdTRUE) return;

  if (!LittleFS.exists("/spool")) LittleFS.mkdir("/spool");
  char name[48];
  snprintf(name, sizeof(name), "/spool/%010lu.job", (unsigned long)(++spoolCounter));
  File f = LittleFS.open(name, FILE_WRITE);
  if (f) {
    f.print(path);
    f.print('\n');
    f.print(json);
    f.close();
  }
  if (spoolCountLocked() > SPOOL_MAX_JOBS) {
    String victim = spoolOldestLocked();
    if (victim.length()) LittleFS.remove(victim);
  }
  xSemaphoreGive(spoolMux);

  if (netTaskHandle) xTaskNotifyGive(netTaskHandle);
}

// คืนชื่อไฟล์ของงานเก่าสุดพร้อม path/body (ยังไม่ลบ)
static bool spoolPeek(String &name, String &path, String &body) {
  if (xSemaphoreTake(spoolMux, pdMS_TO_TICKS(200)) != pdTRUE) return false;
  bool found = false;
  name = spoolOldestLocked();
  if (name.length()) {
    File f = LittleFS.open(name, "r");
    if (f) {
      path = f.readStringUntil('\n');
      body = f.readString();
      f.close();
      found = path.length() > 0;
    }
  }
  xSemaphoreGive(spoolMux);
  path.trim();
  return found;
}

static void spoolDelete(const String &name) {
  if (!name.length()) return;
  if (xSemaphoreTake(spoolMux, pdMS_TO_TICKS(200)) != pdTRUE) return;
  LittleFS.remove(name);
  xSemaphoreGive(spoolMux);
}

// ---------------------------------------------------------------- network

static bool postJson(const String &url, const String &body) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setConnectTimeout(3000);
  if (!http.begin(url)) return false;
  http.addHeader("Content-Type", "application/json");
  if (strlen(API_TOKEN) > 0) http.addHeader("X-Auth-Token", API_TOKEN);
  int code = http.POST(body);
  http.end();
  return code >= 200 && code < 300;
}

static double epochNow() {
  time_t t = time(nullptr);
  return (t > 1600000000) ? (double)t + (millis() % 1000) / 1000.0 : 0.0;
}

// template เพื่อรับ doc ขนาดใดก็ได้ (StaticJsonDocument<384> ที่ส่งเข้ามา
// จะไม่ถูกแปลงเป็น temporary แล้วผูกกับ reference ไม่ได้)
// รับ JsonDocument ฐาน จึงใช้ได้กับ StaticJsonDocument ทุกขนาด
// (เดิมประกาศเป็น StaticJsonDocument<512>& ทำให้ doc ขนาดอื่นผูกไม่ได้)
static String jsonOf(const JsonDocument &doc) {
  String out;
  serializeJson(doc, out);
  return out;
}

static void postEvent(const char *kind, const String &text) {
  StaticJsonDocument<384> d;
  d["node_id"] = GATEWAY_ID;
  d["kind"] = kind;
  d["text"] = text;
  double ts = epochNow();
  if (ts > 0) d["ts"] = ts;
  pushCloud("/cloud/events", jsonOf(d));
}

static bool ensureWifi(uint32_t budgetMs = 12000) {
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < budgetMs) {
    vTaskDelay(pdMS_TO_TICKS(200));
  }
  if (WiFi.status() != WL_CONNECTED) return false;

  Serial.printf("[net] WiFi connected %s (channel %d) <- ตั้ง NODE_CHANNEL ของ node เป็น %d\n",
                WiFi.localIP().toString().c_str(), WiFi.channel(), WiFi.channel());
  if (!timeSynced) {
    configTime(0, 0, "pool.ntp.org", "time.google.com");
    struct tm tmNow;
    if (getLocalTime(&tmNow, 5000)) timeSynced = true;
  }
  return true;
}

// ------------------------------------------------------------------- fan

static void setFan(bool on, const char *reason) {
  strncpy(fanReason, reason, sizeof(fanReason) - 1);
  fanReason[sizeof(fanReason) - 1] = '\0';
  if (on == fanOn) return;

  fanOn = on;
  digitalWrite(FAN_RELAY_PIN, on ? RELAY_ACTIVE_LEVEL : !RELAY_ACTIVE_LEVEL);
  fanSince = on ? millis() : 0;

  char text[140];
  snprintf(text, sizeof(text), "พัดลม%s: %s", on ? "เปิด" : "ปิด", reason);
  postEvent("fan", text);
  Serial.printf("[fan] %s\n", text);
}

static bool liveNode(uint32_t now) {
  portENTER_CRITICAL(&nodeMux);
  bool ok = nodeState.valid && (now - nodeState.lastSeen < NODE_TIMEOUT_MS);
  portEXIT_CRITICAL(&nodeMux);
  return ok;
}

static void fanDecision(uint32_t now) {
  if (estopOn) {
    setFan(false, "หยุดฉุกเฉิน");
    servoAngle = SERVO_SAFE;
    return;
  }
  if (!liveNode(now)) {
    setFan(false, "ไม่ได้รับข้อมูลจาก node เกิน NODE_TIMEOUT_MS");
    return;
  }

  float hum, gas;
  portENTER_CRITICAL(&nodeMux);
  hum = nodeState.hum;
  gas = nodeState.gas;
  portEXIT_CRITICAL(&nodeMux);

  char reason[96];
  if (!fanOn && (hum >= HUM_ON || gas >= GAS_ON)) {
    snprintf(reason, sizeof(reason), "ความชื้น %.0f%% / ก๊าซ %.0f ถึงเกณฑ์เปิด", hum, gas);
    setFan(true, reason);
  } else if (fanOn && hum < HUM_OFF && gas < GAS_OFF) {
    snprintf(reason, sizeof(reason), "ความชื้น %.0f%% / ก๊าซ %.0f ต่ำกว่าเกณฑ์ปิด", hum, gas);
    setFan(false, reason);
  } else if (fanOn && fanSince && (now - fanSince > FAN_MAX_ON_MS)) {
    setFan(false, "ครบเวลา FAN_MAX_ON_MS กันพัดลมร้อนเกิน");
  }
}

// -------------------------------------------------------------- HC-SR04

static volatile uint32_t echoStartUs = 0;
static volatile uint32_t echoWidthUs = 0;
static portMUX_TYPE echoMux = portMUX_INITIALIZER_UNLOCKED;

void IRAM_ATTR echoISR() {
  uint32_t nowUs = micros();
  if (digitalRead(ECHO_PIN) == HIGH) {
    echoStartUs = nowUs;
  } else if (echoStartUs) {
    uint32_t width = nowUs - echoStartUs;
    portENTER_CRITICAL_ISR(&echoMux);
    echoWidthUs = width;
    portEXIT_CRITICAL_ISR(&echoMux);
    echoStartUs = 0;
  }
}

// ยิง trigger แล้วอ่านความกว้างพัลส์ที่ ISR เก็บไว้ (ไม่ busy-poll ใน ISR)
static bool readDistanceCm(float &cm) {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  uint32_t waitUntil = millis() + 60;
  while (millis() < waitUntil) {
    uint32_t width;
    portENTER_CRITICAL(&echoMux);
    width = echoWidthUs;
    if (width > 0) echoWidthUs = 0;
    portEXIT_CRITICAL(&echoMux);

    if (width > 0) {
      cm = width / 58.0f;
      return cm > 2.0f && cm < 450.0f;
    }
    vTaskDelay(pdMS_TO_TICKS(2));
  }
  return false;
}

// ------------------------------------------------------------------ AI

#if WEARWISE_CAMERA
static bool cameraBegin() {
  camera_config_t cfg = {};
  // ไม่ใช้ LEDC channel 0 เพราะ ESP32Servo จองไว้ (ชนกันแล้ว servo จะไม่หมุน)
  cfg.ledc_channel = LEDC_CHANNEL_1;
  cfg.ledc_timer = LEDC_TIMER_1;
  cfg.pin_pwdn = CAM_PIN_PWDN;
  cfg.pin_reset = CAM_PIN_RESET;
  cfg.pin_xclk = CAM_PIN_XCLK;
  cfg.pin_sccb_sda = CAM_PIN_SIOD;
  cfg.pin_sccb_scl = CAM_PIN_SIOC;
  cfg.pin_d7 = CAM_PIN_D7;
  cfg.pin_d6 = CAM_PIN_D6;
  cfg.pin_d5 = CAM_PIN_D5;
  cfg.pin_d4 = CAM_PIN_D4;
  cfg.pin_d3 = CAM_PIN_D3;
  cfg.pin_d2 = CAM_PIN_D2;
  cfg.pin_d1 = CAM_PIN_D1;
  cfg.pin_d0 = CAM_PIN_D0;
  cfg.pin_vsync = CAM_PIN_VSYNC;
  cfg.pin_href = CAM_PIN_HREF;
  cfg.pin_pclk = CAM_PIN_PCLK;
  cfg.xclk_freq_hz = 20000000;
  cfg.pixel_format = PIXFORMAT_RGB565;  // OV7670 ไม่มี JPEG encoder ในตัว
  cfg.frame_size = FRAMESIZE_QVGA;
  cfg.jpeg_quality = 12;
  cfg.fb_count = 2;
  cfg.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&cfg);
  if (err != ESP_OK) {
    Serial.printf("[cam] init failed 0x%x (ตรวจสาย OV7670 / PSRAM)\n", err);
    return false;
  }
  return true;
}

// จับภาพแล้วแปลงเป็น JPEG base64 (OV7670 ให้ RGB565 เราจึง encode เอง)
static String captureBase64Jpeg() {
  if (!cameraReady) return "";
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) return "";

  uint8_t *jpg = nullptr;
  size_t jpgLen = 0;
  bool ownJpg = false;

  if (fb->format == PIXFORMAT_JPEG) {
    jpg = fb->buf;
    jpgLen = fb->len;
  } else if (!frame2jpg(fb, 80, &jpg, &jpgLen)) {
    esp_camera_fb_return(fb);
    return "";
  } else {
    ownJpg = true;
  }

  size_t b64Len = 0;
  mbedtls_base64_encode(nullptr, 0, &b64Len, jpg, jpgLen);

  // Arduino String ไม่มี resize(): จองบัฟเฟอร์เองแล้วสร้าง String จากผลลัพธ์
  // (mbedtls_base64_encode เติม '\0' ให้เมื่อ olen เผื่อไว้ 1 ไบต์)
  char *buf = (char *)malloc(b64Len + 1);
  String out;
  if (buf) {
    size_t written = 0;
    int rc = mbedtls_base64_encode((unsigned char *)buf, b64Len + 1,
                                   &written, jpg, jpgLen);
    if (rc == 0) out = String(buf);
    free(buf);
  }

  if (ownJpg) free(jpg);
  esp_camera_fb_return(fb);
  return out;
}
#endif

static void countPick(const String &label) {
  StaticJsonDocument<128> d;
  d["node_id"] = GATEWAY_ID;
  d["label"] = label;
  // ผ่าน spool เหมือนข้อมูลอื่น: cloud ล่มก็ไม่หาย
  pushCloud("/api/pick", jsonOf(d));
}

static uint32_t lastAiEventMs = 0;

static void aimCamera(bool approach) {
#if WEARWISE_CAMERA
  if (!cameraReady) return;
  String frame = captureBase64Jpeg();
  if (frame.length() == 0) return;

  // ภาพ base64 ใหญ่หลายกิโลไบต์ จึงต้องใช้ document แบบจองจาก heap
  // (StaticJsonDocument ขนาดคงที่จะเก็บภาพไม่ลงและตัดฟิลด์ทิ้งเงียบ ๆ)
  DynamicJsonDocument d(frame.length() + 256);
  d["node_id"] = GATEWAY_ID;
  d["image_b64"] = frame;
  double ts = epochNow();
  if (ts > 0) d["t_sent"] = ts;
  d["approach"] = approach;

  String body;
  body.reserve(measureJson(d) + 1);
  serializeJson(d, body);

  StaticJsonDocument<512> r;
  {
    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT_MS);
    if (!http.begin(String(AI_URL) + "/ai/aim")) return;
    http.addHeader("Content-Type", "application/json");
    if (strlen(API_TOKEN) > 0) http.addHeader("X-Auth-Token", API_TOKEN);
    int code = http.POST(body);
    if (code < 200 || code >= 300) {
      http.end();
      postEvent("ai", "เรียก AI ไม่สำเร็จ HTTP " + String(code));
      return;
    }
    DeserializationError err = deserializeJson(r, http.getStream());
    http.end();
    if (err) return;
  }

  if (!r["found"].as<bool>()) {
    servoAngle = SERVO_SAFE;
    postEvent("ai", "AI ไม่พบเป้า กล้องกลับมุมปลอดภัย");
    return;
  }

  float x = r["x_norm"] | 0.5f;
  int angle = (int)roundf(SERVO_MIN + x * (SERVO_MAX - SERVO_MIN));
  if (angle < SERVO_MIN) angle = SERVO_MIN;
  if (angle > SERVO_MAX) angle = SERVO_MAX;
  servoAngle = angle;

  char text[200];
  snprintf(text, sizeof(text), "AI เห็น %s (%.0f%%) x=%.2f -> servo %d องศา (%.0f ms)",
           (const char *)(r["label"] | "ไม่ทราบ"), (r["confidence"] | 0.0f) * 100.0f, x, angle,
           r["ai_ms"] | 0.0f);
  // ไม่ยิง event ทุกเฟรม: ส่งตอนมีคนเข้ามาใหม่หรือทุก 30 วินาที
  if (approach || millis() - lastAiEventMs > 30000) {
    lastAiEventMs = millis();
    postEvent("ai", text);
  }
  Serial.printf("[ai] %s\n", text);

  if (approach) countPick(String((const char *)(r["label"] | "")));
#else
  (void)approach;
#endif
}

// --------------------------------------------------------------- tasks

static void taskEspNowRx(void *) {
  SensorPacket p;
  for (;;) {
    if (xQueueReceive(rxQueue, &p, portMAX_DELAY) != pdTRUE) continue;
    uint32_t now = millis();

    portENTER_CRITICAL(&nodeMux);
    nodeState.valid = true;
    nodeState.lastSeen = now;
    nodeState.seq = p.seq;
    nodeState.temp = p.temp;
    nodeState.hum = p.hum;
    nodeState.gas = p.gas;
    nodeState.lux = p.lux;
    nodeState.hopMs = p.rtt_ms;
    nodeState.retries = p.retries;
    portEXIT_CRITICAL(&nodeMux);

    AckPacket ack = {};
    ack.magic = WEARWISE_MAGIC;
    ack.type = MSG_ACK;
    strncpy(ack.node_id, p.node_id, sizeof(ack.node_id) - 1);
    ack.ack_seq = p.seq;
    ack.fan = fanOn ? 1 : 0;
    ack.estop = estopOn ? 1 : 0;
    const uint8_t bcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    esp_now_send(bcast, (uint8_t *)&ack, sizeof(ack));

    StaticJsonDocument<384> d;
    double ts = epochNow();
    if (ts > 0) d["ts"] = ts;
    d["node_id"] = p.node_id;
    d["seq"] = p.seq;
    d["temp"] = p.temp;
    d["hum"] = p.hum;
    d["gas"] = p.gas;
    d["lux"] = p.lux;
    d["hop_ms"] = p.rtt_ms;
    d["note"] = p.retries ? "node -> gateway (ส่งซ้ำ)" : "node -> gateway";
    pushCloud("/cloud/rows", jsonOf(d));

    Serial.printf("[rx] %s#%lu hum=%.1f gas=%.0f rtt=%.1f ms retry=%u\n",
                  p.node_id, (unsigned long)p.seq, p.hum, p.gas, p.rtt_ms, p.retries);
  }
}

// เป็นเจ้าของ HC-SR04 แต่ผู้เดียว: อ่านระยะ ตัดสินพัดลม และเขียนแถวของ gateway
static void taskControl(void *) {
  uint32_t lastRow = 0;

  for (;;) {
    uint32_t now = millis();
    float cm = 0;
    bool haveEcho = readDistanceCm(cm);
    personPresent = haveEcho && cm < PERSON_CM;
    if (haveEcho) lastDistCm = cm;

    fanDecision(now);

    if (servoAngle != servoWritten) {
      servo.write(servoAngle);
      servoWritten = servoAngle;
    }

    if (now - lastRow >= GATEWAY_ROW_MS) {
      gatewaySeq++;
      lastRow = now;
      StaticJsonDocument<384> d;
      double ts = epochNow();
      if (ts > 0) d["ts"] = ts;
      d["node_id"] = GATEWAY_ID;
      d["seq"] = gatewaySeq;
      if (haveEcho) d["dist_cm"] = roundf(cm * 10) / 10.0f;
      d["person"] = personPresent ? 1 : 0;
      d["fan"] = fanOn ? 1 : 0;
      d["servo"] = servoAngle;
      d["estop"] = estopOn ? 1 : 0;
      d["hop_ms"] = 0;
      d["note"] = fanReason;
      pushCloud("/cloud/rows", jsonOf(d));
    }

    vTaskDelay(pdMS_TO_TICKS(CONTROL_INTERVAL_MS));
  }
}

// เรียก AI ตอนมีคนเข้ามา (rising edge) แล้วทวนเป็นระยะระหว่างที่ยังมีคนอยู่
static void taskAi(void *) {
  uint32_t lastAi = 0;
  bool prevPerson = false;

  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(200));
    bool person = personPresent;
    bool approach = person && !prevPerson;
    prevPerson = person;

    if (estopOn || !person) continue;
    if (!approach && millis() - lastAi < AI_INTERVAL_MS) continue;

    lastAi = millis();
    aimCamera(approach);
  }
}

static void taskNet(void *) {
  uint32_t lastWifiTry = 0;
  for (;;) {
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000));

    if (WiFi.status() != WL_CONNECTED) {
      if (millis() - lastWifiTry > 10000) {
        lastWifiTry = millis();
        ensureWifi();
      }
      continue;
    }

    String name, path, body;
    while (spoolPeek(name, path, body)) {
      if (!postJson(String(CLOUD_URL) + path, body)) break;  // ยังไม่ขึ้น เก็บไว้ก่อน
      spoolDelete(name);
    }
  }
}

// ------------------------------------------------------------- HTTP local

static void handleEstop() {
  StaticJsonDocument<64> d;
  if (deserializeJson(d, web.arg("plain")) != DeserializationError::Ok) {
    web.send(400, "application/json", "{\"ok\":false,\"error\":\"bad json\"}");
    return;
  }
  estopOn = d["on"] | true;
  if (estopOn) {
    setFan(false, "หยุดฉุกเฉิน");
    servoAngle = SERVO_SAFE;
  }
  postEvent("estop", estopOn ? "กดหยุดฉุกเฉิน: ปิดพัดลมและกล้องกลับมุมปลอดภัย"
                             : "ปลดล็อกหยุดฉุกเฉิน ระบบกลับมาทำงาน");

  StaticJsonDocument<128> out;
  out["ok"] = true;
  out["estop"] = estopOn;
  out["fan"] = fanOn;
  out["servo"] = servoAngle;
  String s;
  serializeJson(out, s);
  web.send(200, "application/json", s);
}

static void handleStatus() {
  StaticJsonDocument<256> d;
  d["ok"] = true;
  d["node_valid"] = nodeState.valid;
  d["estop"] = estopOn;
  d["fan"] = fanOn;
  d["fan_reason"] = fanReason;
  d["servo"] = servoAngle;
  d["queued_jobs"] = spoolCountLocked();
  d["wifi_rssi"] = WiFi.RSSI();
  d["wifi_channel"] = WiFi.channel();
  String s;
  serializeJson(d, s);
  web.send(200, "application/json", s);
}

// ---------------------------------------------------------------- setup

// แยกตัวจัดการออกจาก callback เพื่อให้ signature ที่ขึ้นกับเวอร์ชัน core
// อยู่ที่เดียว (ดู typedef wearwise_recv_info_t ด้านบน)
static void handleSensorPacket(const uint8_t *data, int len) {
  if (len != (int)sizeof(SensorPacket)) return;
  SensorPacket p;
  memcpy(&p, data, sizeof(p));
  if (p.magic != WEARWISE_MAGIC || p.type != MSG_SENSOR) return;
  BaseType_t woken = pdFALSE;
  xQueueSendFromISR(rxQueue, &p, &woken);
  if (woken) portYIELD_FROM_ISR();
}

static void onEspNowRecv(const wearwise_recv_info_t *arg, const uint8_t *data, int len) {
  (void)arg;  // ที่อยู่ผู้ส่งไม่จำเป็น: ใช้ node_id ในแพ็กเก็ตแทน
  handleSensorPacket(data, len);
}

static bool espnowInit() {
  // ไม่ตั้ง channel ที่นี่: gateway ใช้ channel ของ Wi-Fi ที่ต่ออยู่ (ดู log ตอนบูต)
  WiFi.mode(WIFI_STA);
  if (esp_now_init() != ESP_OK) return false;
  esp_now_register_recv_cb(onEspNowRecv);

  esp_now_peer_info_t peer = {};
  const uint8_t bcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
  memcpy(peer.peer_addr, bcast, 6);
  peer.channel = WiFi.channel();
  peer.encrypt = false;
  esp_now_add_peer(&peer);
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("\n[%s] WearWise gateway (HC-SR04, OV7670, fan, servo)\n", GATEWAY_ID);

  spoolMux = xSemaphoreCreateMutex();
  rxQueue = xQueueCreate(16, sizeof(SensorPacket));
  if (!LittleFS.begin(true)) Serial.println("[spool] LittleFS mount failed");
  if (!LittleFS.exists("/spool")) LittleFS.mkdir("/spool");

  pinMode(FAN_RELAY_PIN, OUTPUT);
  digitalWrite(FAN_RELAY_PIN, !RELAY_ACTIVE_LEVEL);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
  attachInterrupt(digitalPinToInterrupt(ECHO_PIN), echoISR, CHANGE);

  servo.setPeriodHertz(50);
  servo.attach(SERVO_PIN, 500, 2400);
  servo.write(SERVO_SAFE);
  servoWritten = SERVO_SAFE;

  ensureWifi();
  if (!espnowInit()) Serial.println("[espnow] init failed");
  else Serial.println("[espnow] ready");

#if WEARWISE_CAMERA
  cameraReady = cameraBegin();
#endif

  web.on("/estop", HTTP_POST, handleEstop);
  web.on("/status", HTTP_GET, handleStatus);
  web.begin();

  xTaskCreatePinnedToCore(taskEspNowRx, "espnow_rx", 4096, nullptr, 4, nullptr, 0);
  xTaskCreatePinnedToCore(taskControl, "control", 4096, nullptr, 3, nullptr, 1);
  xTaskCreatePinnedToCore(taskAi, "ai", 12288, nullptr, 2, nullptr, 1);
  xTaskCreatePinnedToCore(taskNet, "net", 8192, nullptr, 1, &netTaskHandle, 0);

  postEvent("boot", "gateway เริ่มทำงาน");
  Serial.println("[boot] tasks started");
}

void loop() {
  web.handleClient();
  delay(2);
}
