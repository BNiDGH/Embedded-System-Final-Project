import serial, time
import numpy as np
import cv2

PORT = 'COM12'
BAUD = 921600          # ต้องตรงกับ Serial.begin(...) ใน ESP32
W, H = 320, 240
PKT = 3 + W + 2        # หัว 3 + ข้อมูล + checksum 2

ser = serial.Serial()
ser.port = PORT
ser.baudrate = BAUD
ser.timeout = 1
ser.dtr = False
ser.rts = False
ser.open()
ser.set_buffer_size(rx_size=4 * 1024 * 1024)
ser.reset_input_buffer()

img = np.zeros((H, W), np.uint8)
buf = bytearray()
good = bad = 0
last_show = last_stat = time.time()

while True:
    buf += ser.read(max(1, ser.in_waiting))

    while True:
        i = buf.find(b'\xA5\x5A')
        if i < 0:
            del buf[:-1]               # เก็บไบต์สุดท้ายไว้ เผื่อเป็น 0xA5
            break
        if len(buf) - i < PKT:
            del buf[:i]                # รอข้อมูลมาเพิ่ม
            break
        y = buf[i + 2]
        payload = bytes(buf[i + 3:i + 3 + W])
        cs = buf[i + 3 + W] | (buf[i + 4 + W] << 8)
        if y < H and (sum(payload) & 0xFFFF) == cs:
            img[y] = np.frombuffer(payload, np.uint8)
            good += 1
            del buf[:i + PKT]
        else:
            bad += 1
            del buf[:i + 1]            # ไม่ใช่แพ็กเก็ตจริง ขยับไป 1 ไบต์แล้วหาใหม่

    now = time.time()
    if now - last_show > 0.05:
        cv2.imshow('OV7670', cv2.resize(img, (W * 2, H * 2), interpolation=cv2.INTER_NEAREST))
        if cv2.waitKey(1) == 27:       # ESC ออก
            break
        last_show = now
    if now - last_stat > 2:
        print(f'lines good={good} bad={bad}')
        last_stat = now

ser.close()
cv2.destroyAllWindows()