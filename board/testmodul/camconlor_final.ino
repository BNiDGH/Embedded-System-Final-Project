#include "esp_camera.h"

#define STREAM_MODE 1   // 0 = ทดสอบ (ดูข้อความ), 1 = ส่งภาพให้ Python
#define COLOR       1   // 1 = สี RGB565, 0 = ขาวดำ

void setup() {
  Serial.begin(115200);
#if !STREAM_MODE
  delay(3000);
  Serial.printf("largest free block: %u bytes\n",
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
#endif

  // เปิด XCLK เอง (ไดรเวอร์เริ่มเองเร็วเกินไปจนหากล้องไม่เจอ)
  ledcSetup(0, 10000000, 1);
  ledcAttachPin(15, 0);
  ledcWrite(0, 1);
  delay(300);

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_1;
  config.ledc_timer   = LEDC_TIMER_1;
  config.pin_d0 = 11; config.pin_d1 = 9;  config.pin_d2 = 8;  config.pin_d3 = 10;
  config.pin_d4 = 12; config.pin_d5 = 18; config.pin_d6 = 17; config.pin_d7 = 16;
  config.pin_xclk  = -1;
  config.pin_pclk  = 13;
  config.pin_vsync = 6;
  config.pin_href  = 7;
  config.pin_sscb_sda = 4;
  config.pin_sscb_scl = 5;
  config.pin_pwdn  = -1;
  config.pin_reset = -1;
  config.xclk_freq_hz = 10000000;
#if COLOR
  config.pixel_format = PIXFORMAT_RGB565;
#else
  config.pixel_format = PIXFORMAT_GRAYSCALE;
#endif
  config.frame_size   = FRAMESIZE_QVGA;
  config.fb_count     = 1;
  config.fb_location  = CAMERA_FB_IN_DRAM;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
#if !STREAM_MODE
  Serial.printf("camera init: 0x%x\n", err);
#endif
}

void loop() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { delay(50); return; }

#if STREAM_MODE
  const int w = fb->width, h = fb->height;
  const int lineBytes = (int)(fb->len / h);        // 640 สำหรับสี, 320 สำหรับขาวดำ
  for (int y = 0; y < h; y++) {
    const uint8_t *line = fb->buf + (size_t)y * lineBytes;
    uint16_t sum = 0;
    for (int x = 0; x < lineBytes; x++) sum += line[x];
    const uint8_t head[3] = {0xA5, 0x5A, (uint8_t)y};
    Serial.write(head, 3);
    Serial.write(line, lineBytes);
    Serial.write((uint8_t*)&sum, 2);
  }
#else
  Serial.printf("frame OK: %dx%d, %u bytes\n", fb->width, fb->height, (unsigned)fb->len);
  delay(500);
#endif
  esp_camera_fb_return(fb);
}