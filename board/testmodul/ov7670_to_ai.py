"""ส่งภาพจาก OV7670 (ผ่าน ESP32-S3 ทาง USB serial) เข้า AI service /ai/aim

ใช้โปรโตคอลเดียวกับ camconlor_final.ino / camconlor_final.py
  แพ็กเก็ตต่อ 1 บรรทัดภาพ = A5 5A | y | payload (W*2 ไบต์ถ้าสี) | checksum 2 ไบต์ (little-endian)

ใช้:
  python ov7670_to_ai.py --port COM15
  python ov7670_to_ai.py --port COM15 --url http://127.0.0.1:8001 --interval 2
  python ov7670_to_ai.py --port COM15 --no-show          # ไม่เปิดหน้าต่าง
  python ov7670_to_ai.py --port COM15 --swap             # ถ้าสีเพี้ยน

ปุ่มในหน้าต่าง: ESC = ออก, s = บันทึกเฟรมปัจจุบันเป็น .jpg (เก็บไว้ทำชุดทดสอบความแม่น)

ข้อควรระวัง: พอร์ต COM เปิดได้ทีละโปรแกรม ต้องปิด camconlor_final.py ก่อนรันไฟล์นี้
"""
import argparse
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request

import cv2
import numpy as np
import serial

W, H = 320, 240
SERVO_MIN, SERVO_MAX = 20, 160  # ตรงกับ gateway


def decode_frame(raw, color, swap):
    """แปลงข้อมูลดิบ (RGB565 หรือ gray) เป็นภาพ BGR"""
    if not color:
        return cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    hi, lo = (raw[:, 1::2], raw[:, 0::2]) if swap else (raw[:, 0::2], raw[:, 1::2])
    px = (hi.astype(np.uint16) << 8) | lo
    r5 = (px >> 11) & 0x1F
    g6 = (px >> 5) & 0x3F
    b5 = px & 0x1F
    # ขยายบิตแบบเติมซ้ำ (ขาวต้องได้ 255 จริง) ช่วยให้ตรวจสีขาว/ดำใน garment.py แม่นขึ้น
    r = (r5 << 3) | (r5 >> 2)
    g = (g6 << 2) | (g6 >> 4)
    b = (b5 << 3) | (b5 >> 2)
    return np.dstack([b, g, r]).astype(np.uint8)


class AiWorker(threading.Thread):
    """เรียก AI ใน thread แยก เพื่อไม่ให้การอ่าน serial สะดุด"""

    def __init__(self, url, token, node):
        super().__init__(daemon=True)
        self.url, self.token, self.node = url.rstrip("/") + "/ai/aim", token, node
        self.job = None
        self.result = None
        self.busy = False
        self.event = threading.Event()

    def submit(self, bgr):
        ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return
        self.job = buf.tobytes()
        self.busy = True
        self.event.set()

    def run(self):
        while True:
            self.event.wait()
            self.event.clear()
            jpeg = self.job
            body = json.dumps({
                "node_id": self.node,
                "t_sent": time.time(),
                "image_b64": base64.b64encode(jpeg).decode(),
            }).encode()
            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["X-Auth-Token"] = self.token
            try:
                req = urllib.request.Request(self.url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res = json.loads(resp.read().decode())
                self.result = res
                if res.get("found"):
                    angle = SERVO_MIN + res["x_norm"] * (SERVO_MAX - SERVO_MIN)
                    print("found x_norm=%.3f servo=%.0f° %s (%s) conf=%.2f ai=%.0fms net=%sms [%s]" % (
                        res["x_norm"], angle, res["label"], res["category"],
                        res["confidence"], res["ai_ms"], res["net_ms"], res["detector"]))
                else:
                    print("ไม่พบคน -> servo กลับมุมปลอดภัย 90°  (ai=%.0fms)" % res["ai_ms"])
            except urllib.error.HTTPError as e:
                self.result = None
                print("HTTP %d: %s" % (e.code, e.read().decode(errors="ignore")))
            except Exception as e:
                self.result = None
                print("เรียก AI ไม่สำเร็จ:", e)
            self.busy = False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM15", help="พอร์ตของ ESP32-S3")
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--token", default="")
    ap.add_argument("--node", default="CB302")
    ap.add_argument("--interval", type=float, default=2.0, help="วินาทีระหว่างการส่งแต่ละครั้ง")
    ap.add_argument("--gray", action="store_true", help="ใช้เมื่อ #define COLOR 0 ใน ESP32")
    ap.add_argument("--swap", action="store_true", help="สลับ byte ถ้าสีเพี้ยน")
    ap.add_argument("--no-show", action="store_true")
    ap.add_argument("--save-dir", default="captures")
    args = ap.parse_args()

    color = not args.gray
    line_len = W * 2 if color else W
    pkt = 3 + line_len + 2

    ser = serial.Serial()
    ser.port = args.port
    ser.baudrate = 115200
    ser.timeout = 0.1
    ser.dtr = False
    ser.rts = False
    ser.open()
    try:
        ser.set_buffer_size(rx_size=4 * 1024 * 1024)
    except Exception:
        pass
    ser.reset_input_buffer()

    worker = AiWorker(args.url, args.token, args.node)
    worker.start()

    raw = np.zeros((H, line_len), np.uint8)
    seen = np.zeros(H, bool)
    buf = bytearray()
    good = bad = 0
    complete = None          # เฟรมสมบูรณ์ล่าสุด (BGR)
    last_send = 0.0
    last_show = last_stat = time.time()
    show = not args.no_show
    print("เริ่มแล้ว (ESC ออก, s บันทึกภาพ)")

    try:
        while True:
            buf += ser.read(max(1, ser.in_waiting))

            while True:
                i = buf.find(b"\xA5\x5A")
                if i < 0:
                    del buf[:-1]
                    break
                if len(buf) - i < pkt:
                    del buf[:i]
                    break
                y = buf[i + 2]
                payload = bytes(buf[i + 3:i + 3 + line_len])
                cs = buf[i + 3 + line_len] | (buf[i + 4 + line_len] << 8)
                if y < H and (sum(payload) & 0xFFFF) == cs:
                    if y == 0:
                        seen[:] = False          # เริ่มเฟรมใหม่
                    raw[y] = np.frombuffer(payload, np.uint8)
                    seen[y] = True
                    good += 1
                    if y == H - 1 and seen.sum() >= H * 0.97:
                        # บรรทัดสุดท้ายมาถึงและครบเกือบทั้งเฟรม -> ถ่าย snapshot ที่ไม่ฉีก
                        complete = decode_frame(raw, color, args.swap)
                    del buf[:i + pkt]
                else:
                    bad += 1
                    del buf[:i + 1]

            now = time.time()

            # ส่งเข้า AI เมื่อถึงรอบและ worker ว่าง
            if complete is not None and not worker.busy and now - last_send >= args.interval:
                last_send = now
                worker.submit(complete)

            if show and now - last_show > 0.05:
                view = decode_frame(raw, color, args.swap)
                view = cv2.resize(view, (W * 2, H * 2), interpolation=cv2.INTER_NEAREST)
                res = worker.result
                if res and res.get("found"):
                    x = int(res["x_norm"] * W * 2)
                    cv2.line(view, (x, 0), (x, H * 2), (0, 255, 0), 2)
                    cv2.putText(view, "x_norm=%.2f conf=%.2f" % (res["x_norm"], res["confidence"]),
                                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                elif res:
                    cv2.putText(view, "no person", (10, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                try:
                    cv2.imshow("OV7670 -> AI", view)
                    k = cv2.waitKey(1) & 0xFF
                    if k == 27:
                        break
                    if k == ord("s") and complete is not None:
                        os.makedirs(args.save_dir, exist_ok=True)
                        path = os.path.join(args.save_dir, "cap_%d.jpg" % int(time.time()))
                        cv2.imwrite(path, complete)
                        print("บันทึก", path)
                except cv2.error:
                    print("opencv ไม่รองรับหน้าต่าง (headless) -> สลับเป็นโหมด --no-show")
                    show = False
                last_show = now

            if now - last_stat > 5:
                print("lines good=%d bad=%d" % (good, bad))
                last_stat = now
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        if show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()