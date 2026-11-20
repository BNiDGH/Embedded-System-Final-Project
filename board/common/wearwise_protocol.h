/*
 * WearWise: shared ESP-NOW protocol (sensor node <-> gateway)
 *
 * โครงสร้างนี้เป็นสัญญาระหว่างเฟิร์มแวร์สองบอร์ด ต้องเหมือนกันทั้งสองฝั่ง
 * ทุกแพ็กเก็ตขึ้นต้นด้วย magic + type เพื่อให้ฝั่งรับตรวจแพ็กเก็ตขยะได้
 */
#pragma once

#include <stdint.h>

#define WEARWISE_MAGIC 0x5757          // 'W''W'
#define WEARWISE_CHANNEL 1             // ต้องตั้ง Wi-Fi channel เดียวกันทั้งสองบอร์ด
#define WEARWISE_MAX_PAYLOAD 250       // ขีดจำกัดของ ESP-NOW

enum WearWiseMsg : uint8_t {
  MSG_SENSOR = 1,  // node -> gateway
  MSG_ACK = 2,     // gateway -> node (application-level ack)
  MSG_CMD = 3,     // gateway -> node (สำรองไว้สั่งงาน)
};

// node -> gateway
struct __attribute__((packed)) SensorPacket {
  uint16_t magic;
  uint8_t type;
  char node_id[12];
  uint32_t seq;
  uint32_t uptime_ms;
  float temp;    // °C      (DHT22)
  float hum;     // %RH     (DHT22)
  float gas;     // ppm     (MQ-135, ประมาณจาก Rs/R0)
  float lux;     // lx      (BH1750)
  float rtt_ms;  // RTT ของแพ็กเก็ตก่อนหน้า (node วัดเองจากตอนรอ ack)
  uint8_t retries;
};

// gateway -> node
struct __attribute__((packed)) AckPacket {
  uint16_t magic;
  uint8_t type;
  char node_id[12];
  uint32_t ack_seq;
  uint8_t fan;
  uint8_t estop;
};

// gateway -> node (คำสั่ง)
struct __attribute__((packed)) CmdPacket {
  uint16_t magic;
  uint8_t type;
  uint8_t estop;
};

static_assert(sizeof(SensorPacket) <= WEARWISE_MAX_PAYLOAD, "SensorPacket ใหญ่เกิน ESP-NOW");
static_assert(sizeof(AckPacket) <= WEARWISE_MAX_PAYLOAD, "AckPacket ใหญ่เกิน ESP-NOW");
