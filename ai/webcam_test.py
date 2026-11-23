"""ทดสอบ AI service ด้วย webcam ในเครื่อง (แทน OV7670 + gateway)

ใช้:
  python webcam_test.py                       # เปิดหน้าต่างดูภาพ กด q เพื่อออก
  python webcam_test.py --no-show             # ไม่เปิดหน้าต่าง พิมพ์ผลใน terminal อย่างเดียว
  python webcam_test.py --cam 1 --interval 0.5
  python webcam_test.py --url http://192.168.1.50:8001 --token xxxx

หมายเหตุ: requirements.txt ใช้ opencv-python-headless ซึ่งไม่มี cv2.imshow
ถ้าอยากเห็นหน้าต่าง ให้ลง opencv-python แทน (หรือใช้ --no-show)
"""
import argparse
import base64
import json
import time
import urllib.error
import urllib.request

import cv2

SERVO_MIN, SERVO_MAX = 20, 160  # ตรงกับ YOLO.md ข้อ 9


def call_ai(url, token, jpeg_bytes, node_id):
    body = json.dumps({
        "node_id": node_id,
        "t_sent": time.time(),
        "image_b64": base64.b64encode(jpeg_bytes).decode(),
    }).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Auth-Token"] = token
    req = urllib.request.Request(url.rstrip("/") + "/ai/aim", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--token", default="")
    ap.add_argument("--cam", type=int, default=0, help="index ของกล้อง")
    ap.add_argument("--interval", type=float, default=1.0, help="วินาทีระหว่างการยิงแต่ละครั้ง")
    ap.add_argument("--size", default="320x240", help="ขนาดภาพที่ส่ง (ค่าเริ่มต้นจำลอง QVGA ของ OV7670)")
    ap.add_argument("--node", default="CB302")
    ap.add_argument("--no-show", action="store_true")
    args = ap.parse_args()

    w, h = [int(v) for v in args.size.lower().split("x")]
    cap = cv2.VideoCapture(args.cam)
    if not cap.isOpened():
        raise SystemExit("เปิดกล้อง index %d ไม่ได้ (ลอง --cam 1)" % args.cam)

    show = not args.no_show
    last = None  # ผลล่าสุด ไว้วาดทับภาพ
    last_sent = 0.0
    print("เริ่มแล้ว กด q ที่หน้าต่าง (หรือ Ctrl+C) เพื่อออก")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("อ่านภาพจากกล้องไม่ได้")
                break

            now = time.time()
            if now - last_sent >= args.interval:
                last_sent = now
                small = cv2.resize(frame, (w, h))
                ok_enc, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
                try:
                    last = call_ai(args.url, args.token, buf.tobytes(), args.node)
                    if last.get("found"):
                        angle = SERVO_MIN + last["x_norm"] * (SERVO_MAX - SERVO_MIN)
                        print("found x_norm=%.3f servo=%.0f° %s (%s) conf=%.2f ai=%.0fms net=%sms [%s]" % (
                            last["x_norm"], angle, last["label"], last["category"],
                            last["confidence"], last["ai_ms"], last["net_ms"], last["detector"]))
                    else:
                        print("ไม่พบคน -> servo กลับมุมปลอดภัย 90°  (ai=%.0fms)" % last["ai_ms"])
                except urllib.error.HTTPError as e:
                    print("HTTP %d: %s" % (e.code, e.read().decode(errors="ignore")))
                    last = None
                except Exception as e:
                    print("เรียก AI ไม่สำเร็จ:", e)
                    last = None

            if show:
                view = frame.copy()
                vh, vw = view.shape[:2]
                if last and last.get("found"):
                    x = int(last["x_norm"] * vw)
                    cv2.line(view, (x, 0), (x, vh), (0, 255, 0), 2)
                    cv2.putText(view, "x_norm=%.2f conf=%.2f" % (last["x_norm"], last["confidence"]),
                                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    # label เป็นภาษาไทย cv2.putText วาดไม่ได้ จึงดูใน terminal แทน
                else:
                    cv2.putText(view, "no person", (10, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                try:
                    cv2.imshow("WearWise webcam test", view)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                except cv2.error:
                    print("opencv ไม่รองรับหน้าต่าง (headless) -> สลับเป็นโหมด --no-show")
                    show = False
            else:
                time.sleep(0.03)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()