import serial, time

ser = serial.Serial()
ser.port = 'COM12'
ser.baudrate = 460800
ser.timeout = 0.5
ser.dtr = False
ser.rts = False
ser.open()
ser.reset_input_buffer()

t0 = time.time()
data = b''
while time.time() - t0 < 3:
    data += ser.read(4096)
ser.close()

print('bytes received:', len(data))
print('first 40 bytes:', data[:40].hex(' '))
print('count of A5 5A:', data.count(b'\xA5\x5A'))
print('count of AA 55 AA 55:', data.count(b'\xAA\x55\xAA\x55'))