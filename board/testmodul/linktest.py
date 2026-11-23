import serial, time

ser = serial.Serial()
ser.port = 'COM12'
ser.baudrate = 460800        # ต้องตรงกับ Serial.begin(...) ใน ESP32
ser.timeout = 0.5
ser.dtr = False
ser.rts = False
ser.open()
ser.set_buffer_size(rx_size=4 * 1024 * 1024)
ser.reset_input_buffer()

buf = bytearray()
t0 = time.time()
while time.time() - t0 < 15:
    buf += ser.read(65536)
ser.close()

parts = bytes(buf).split(b'\xAA\x55\xAA\x55')
lens = [len(p) for p in parts[1:-1]]   # ตัดชิ้นแรกกับชิ้นสุดท้ายที่ไม่ครบ
print(len(lens), 'frames')
print(lens)
print('expected each =', 4 + 76800 + 4)   # w,h + ภาพ + checksum