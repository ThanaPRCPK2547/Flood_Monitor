# Automated Flood Monitoring Pipeline (CSV Version) 🌊

โปรเจกต์นี้ปรับให้ใช้ dataset จริงของคุณ: `/Users/thanakorn/Desktop/thailand_flood_mockup_1M.csv`
เพื่อสร้างระบบวิเคราะห์ความเสี่ยงน้ำท่วมรายจังหวัดแบบอัตโนมัติ

## Architecture
- Ingestion: โหลดข้อมูลจาก CSV (`date, province, rainfall_mm, water_level_m, ...`)
- Processing: aggregate รายจังหวัด + คำนวณ `risk_score` จาก rainfall/water level/flood rate/humidity
- Storage: บันทึกผลลัพธ์เชิงพื้นที่ (Point) ลง PostgreSQL + PostGIS
- Visualization: แสดง Heatmap และอันดับจังหวัดเสี่ยงผ่าน Streamlit

## Project Structure
```text
/Users/thanakorn/Desktop/Automated-Flood-Monitoring-Pipeline/
├── config/settings.yaml
├── src/flood_pipeline/
│   ├── config.py
│   ├── csv_ingestion.py
│   ├── csv_processing.py
│   ├── pipeline.py
│   └── storage.py
├── dashboard/streamlit_app.py
├── scripts/run_pipeline.py
├── sql/init_postgis.sql
└── requirements.txt
```

## 1) Setup
```bash
cd /Users/thanakorn/Desktop/Automated-Flood-Monitoring-Pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2) Configure
ค่าเริ่มต้นตั้งให้ใช้ไฟล์นี้แล้ว:
- `FLOOD_DATASET_PATH=/Users/thanakorn/Desktop/thailand_flood_mockup_1M.csv`

ถ้าต้องการกำหนดช่วงวันเอง ให้ใส่ใน `.env`
- `START_DATE=2020-01-01`
- `END_DATE=2020-01-31`

ถ้าไม่กำหนดช่วงวัน ระบบจะพยายามใช้ 7 วันล่าสุด และถ้าไม่เจอข้อมูลจะ fallback ไป 7 วันล่าสุดใน dataset อัตโนมัติ

## 3) Prepare PostGIS
```bash
psql "http://localhost/phpmyadmin/index.php?route=/database/structure&db=flood" -f sql/init_postgis.sql
```

## 4) Run Pipeline
```bash
python scripts/run_pipeline.py
```

ผลลัพธ์ที่ได้:
- ตาราง `public.flood_risk_events` ใน PostGIS
- GeoJSON ใน `data/output/flood_risk_*.geojson`

## 5) Run Dashboard
```bash
streamlit run dashboard/streamlit_app.py
```

## Notes
- Dataset นี้เป็น mockup ไม่มีพิกัดรายจุด จึง map จังหวัดเป็น centroid เพื่อทำแผนที่
- สูตร `risk_score` เป็น baseline สำหรับ monitoring และควรปรับน้ำหนักให้ตรงบริบทหน้างาน
