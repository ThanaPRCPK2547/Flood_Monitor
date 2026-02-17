# Deploy Web App on Render

เอกสารนี้สรุป 2 โหมด deploy:
- Quick Deploy (แนะนำ): รันจาก CSV โดยไม่ต้องมี Postgres
- Optional DB Mode: เพิ่ม Postgres/PostGIS ภายหลัง

## Quick Deploy (CSV-only, แนะนำ)

### 1) เตรียม repo
```bash
cd /Users/thanakorn/Desktop/Automated-Flood-Monitoring-Pipeline
git add .
git commit -m "Prepare Render deployment"
git push origin main
```

### 2) Deploy ด้วย Blueprint
1. ไปที่ https://render.com
2. เลือก `New +` -> `Blueprint`
3. เลือก GitHub repository นี้
4. Render จะอ่าน `render.yaml` และสร้าง web service ให้ทันที

### 3) ตรวจสอบการทำงาน
หลัง deploy สำเร็จ เปิด URL ของ service แล้วเช็คว่า:
- sidebar โหลดได้
- map แสดง event-level scatter ได้
- table แสดง ranking ได้

## Optional: Enable Postgres/PostGIS Mode

ถ้าต้องการใช้ข้อมูล aggregate จาก DB เพิ่มเติม:

### 1) สร้าง PostgreSQL service บน Render
- สร้าง Postgres instance แยกใน Render dashboard
- คัดลอก connection string

### 2) ใส่ env vars ใน web service
- `DATABASE_URL=<your render postgres url>`
- `FLOOD_SCHEMA=public`
- `FLOOD_TABLE=flood_risk_events`

### 3) เปิด shell แล้ว init DB
```bash
bash scripts/render_setup.sh
```

สคริปต์นี้จะ:
- create extension `postgis`
- create table จาก `sql/init_postgis.sql`
- run pipeline เติมข้อมูลเริ่มต้น

## Runtime Notes
- Dashboard มี fallback data source อัตโนมัติ: `DB -> GeoJSON -> CSV`
- ตอนนี้ deploy config ใน `render.yaml` ตั้งเป็น CSV-first เพื่อให้ขึ้นเว็บได้เร็วและเสถียร
- dataset ที่ใช้บน Render ถูกตั้งค่าโดย `FLOOD_DATASET_PATH=/opt/render/project/src/data/thailand_flood_sample.csv`

## Troubleshooting
- App ไม่ขึ้น:
  - ตรวจ Logs ของ Render service
  - ตรวจว่า `data/thailand_flood_sample.csv` อยู่ใน repo
  - ตรวจ build ว่าติดตั้ง dependency ครบจาก `requirements.txt`
- DB mode ใช้ไม่ได้:
  - เช็ค `DATABASE_URL` ถูกต้อง
  - เช็คว่า run `bash scripts/render_setup.sh` แล้ว
