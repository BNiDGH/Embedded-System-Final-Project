import serial, time
import numpy as np
import cv2

PORT = 'COM15'            # เปลี่ยนเป็นพอร์ตของ ESP32-S3
W, H = 320, 240
COLOR = True             # ต้องตรงกับ #define COLOR ใน ESP32
SWAP = False             # ถ้าสีเพี้ยน ลองเปลี่ยนเป็น True
LINE = W * 2 if COLOR else W
PKT = 3 + LINE + 2

ser = serial.Serial()
ser.port = PORT
ser.baudrate = 115200    # พอร์ต USB ไม่สนค่านี้
ser.timeout = 0.1
ser.dtr = False
ser.rts = False
ser.open()
try:
    ser.set_buffer_size(rx_size=4 * 1024 * 1024)
except Exception:
    pass
ser.reset_input_buffer()

raw = np.zeros((H, LINE), np.uint8)
buf = bytearray()
good = bad = 0
last_show = last_stat = time.time()

while True:
    buf += ser.read(max(1, ser.in_waiting))

    while True:
        i = buf.find(b'\xA5\x5A')
        if i < 0:
            del buf[:-1]
            break
        if len(buf) - i < PKT:
            del buf[:i]
            break
        y = buf[i + 2]
        payload = bytes(buf[i + 3:i + 3 + LINE])
        cs = buf[i + 3 + LINE] | (buf[i + 4 + LINE] << 8)
        if y < H and (sum(payload) & 0xFFFF) == cs:
            raw[y] = np.frombuffer(payload, np.uint8)
            good += 1
            del buf[:i + PKT]
        else:
            bad += 1
            del buf[:i + 1]

    now = time.time()
    if now - last_show > 0.05:
        if COLOR:
            hi, lo = (raw[:, 1::2], raw[:, 0::2]) if SWAP else (raw[:, 0::2], raw[:, 1::2])
            px = (hi.astype(np.uint16) << 8) | lo
            r = ((px >> 11) & 0x1F) << 3
            g = ((px >> 5) & 0x3F) << 2
            b = (px & 0x1F) << 3
            img = np.dstack([b, g, r]).astype(np.uint8)
        else:
            img = raw
        cv2.imshow('OV7670', cv2.resize(img, (W * 2, H * 2), interpolation=cv2.INTER_NEAREST))
        if cv2.waitKey(1) == 27:     # ESC ออก
            break
        last_show = now
    if now - last_stat > 2:
        print(f'lines good={good} bad={bad}')
        last_stat = now

ser.close()
cv2.destroyAllWindows()