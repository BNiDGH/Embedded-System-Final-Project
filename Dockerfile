# Dockerfile เดียว ใช้ build ได้ทั้ง 3 service โดยเลือกโฟลเดอร์ผ่าน build arg
#   docker build --build-arg SERVICE=cloud -t wearwise-cloud .
# ปกติไม่ต้องเรียกเอง: docker-compose.yml ตั้ง SERVICE ให้แล้วต่อ service
ARG SERVICE=cloud
FROM python:3.12-slim

ARG SERVICE
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libglib2.0-0 + libgomp1 จำเป็นต่อ opencv-python-headless (ใช้ใน ai/)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements ก่อน COPY โค้ด เพื่อให้ layer cache ยังใช้ได้เมื่อแก้โค้ด
COPY ${SERVICE}/requirements.txt requirements.txt
RUN pip install -r requirements.txt

# แต่ละ service import โมดูลข้างกัน (import config) จึงต้องมีไฟล์อยู่ที่ /app ตรง ๆ
COPY ${SERVICE} /app

# คำสั่งรันกำหนดใน docker-compose.yml (working_dir = /app, uvicorn <module>:app)
