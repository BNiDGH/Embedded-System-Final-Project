"""แจ้งเตือนผ่าน Discord webhook

ถ้าไม่ได้ตั้ง DISCORD_WEBHOOK_URL จะคืน "mock" (ไม่ยิงเน็ต) เพื่อให้เดโมไม่พัง
"""
import config


def send(text):
    url = config.env("DISCORD_WEBHOOK_URL")
    if not url:
        return "mock"
    try:
        import requests
        r = requests.post(url, json={"content": text}, timeout=5)
        return "sent" if r.status_code < 300 else "failed"
    except Exception:
        return "failed"
