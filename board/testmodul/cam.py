import serial, struct
import numpy as np
import cv2

ser = serial.Serial()
ser.port = 'COM12'
ser.baudrate = 460800      # ต้องตรงกับ Serial.begin(...) ใน ESP32
ser.timeout = 2
ser.dtr = False
ser.rts = False
ser.open()
ser.set_buffer_size(rx_size=4 * 1024 * 1024, tx_size=4096)
ser.reset_input_buffer()

MAGIC = b'\xAA\x55\xAA\x55'

def sync():
    buf = b''
    while True:
        b = ser.read(1)
        if not b:
            continue
        buf = (buf + b)[-4:]
        if buf == MAGIC:
            return
ok = bad = 0
while True:
    sync()

    hdr = ser.read(4)
    if len(hdr) != 4:
        continue
    w, h = struct.unpack('<HH', hdr)
    if not (0 < w <= 640 and 0 < h <= 480):
        continue

    data = ser.read(w * h)
    cs = ser.read(4)
    if len(data) != w * h or len(cs) != 4:
        continue

    expected = struct.unpack('<I', cs)[0]
    actual = int(np.frombuffer(data, dtype=np.uint8).sum(dtype=np.uint64)) & 0xFFFFFFFF
    
    if expected != actual:
        bad += 1
        print(f'BAD  (ok={ok} bad={bad})  expected={expected} actual={actual}')
        continue
    ok += 1
    print(f'OK   (ok={ok} bad={bad})')

    img = np.frombuffer(data, dtype=np.uint8).reshape(h, w)
    img = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_NEAREST)
    cv2.imshow('OV7670', img)
    if cv2.waitKey(1) == 27:   # กด ESC ออก
        break

ser.close()
cv2.destroyAllWindows()