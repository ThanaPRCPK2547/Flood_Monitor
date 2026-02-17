# Automated Flood Monitoring Pipeline (CSV Version) 🌊

ระบบสำหรับประมวลผลข้อมูลน้ำท่วมจาก CSV และแสดงผลผ่าน Streamlit dashboard  
รองรับทั้ง pipeline แบบ aggregate รายจังหวัด และ dashboard แบบ event-level scatter

## Features
- CSV ingestion และ validation คอลัมน์หลัก (`date, province, rainfall_mm, water_level_m, temperature_c, humidity_percent, is_flood`)
- Pipeline คำนวณ `risk_score` รายจังหวัด และ export ไป PostGIS + GeoJSON
- Dashboard แสดง scatter map แบบหลายจุด (event-level) ไม่รวมเป็นจุดเดียว
- Sidebar filter: วันที่, จังหวัด, ชั่วโมง, และจำนวนจุดสูงสุดบนแผนที่
- Fallback data source อัตโนมัติ เมื่อ DB ใช้งานไม่ได้

## Architecture
- Ingestion: `src/flood_pipeline/csv_ingestion.py`
- Processing: `src/flood_pipeline/csv_processing.py`
- Storage: `src/flood_pipeline/storage.py`
- Orchestration: `src/flood_pipeline/pipeline.py`
- Dashboard: `dashboard/streamlit_app.py`

## Project Structure
```text
Automated-Flood-Monitoring-Pipeline/
├── config/settings.yaml
├── dashboard/streamlit_app.py
├── data/
│   ├── thailand_flood_sample.csv
│   └── output/
├── scripts/run_pipeline.py
├── sql/init_postgis.sql
├── src/flood_pipeline/
│   ├── config.py
│   ├── csv_ingestion.py
│   ├── csv_processing.py
│   ├── pipeline.py
│   └── storage.py
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
ตั้งค่าใน `.env` (ตัวอย่างอยู่ใน `.env.example`)

ค่าหลัก:
- `FLOOD_DATASET_PATH=/Users/thanakorn/Desktop/thailand_flood_mockup_1M.csv`
- `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/flood`
- `FLOOD_SCHEMA=public`
- `FLOOD_TABLE=flood_risk_events`

ค่าเสริม:
- `START_DATE=2020-01-01`
- `END_DATE=2020-01-31`
- `FLOOD_STRICT_DB=false` (ตั้ง `true` เพื่อบังคับให้ pipeline fail เมื่อเขียน DB ไม่ได้)
- `FLOOD_LOOKBACK_DAYS=90` (ใช้ตอนอ่านข้อมูลจาก DB บน dashboard)
- `FLOOD_LOCAL_GEOJSON_GLOB=data/output/flood_risk_*.geojson`
- `FLOOD_MIN_SAMPLES_PER_PROVINCE=300`

## 3) (Optional) Prepare PostGIS
ถ้าต้องการใช้ storage ใน PostgreSQL/PostGIS:

```bash
psql "$DATABASE_URL" -f sql/init_postgis.sql
```

## 4) Run Pipeline
```bash
python scripts/run_pipeline.py
```

ผลลัพธ์:
- Insert ข้อมูลไปตาราง `flood_risk_events` (ถ้า DB พร้อม)
- สร้างไฟล์ `data/output/flood_risk_*.geojson`

## 5) Run Dashboard
```bash
streamlit run dashboard/streamlit_app.py
```

## Dashboard Data Source Priority
ตัว dashboard จะพยายามโหลดข้อมูลตามลำดับ:
1. PostgreSQL/PostGIS (`DATABASE_URL`)
2. GeoJSON ล่าสุดใน `data/output/`
3. CSV ต้นทาง (`FLOOD_DATASET_PATH`) เพื่อแสดง event-level scatter

## Event-Level Scatter (Current Behavior)
- ใช้ข้อมูลรายแถวจาก CSV เพื่อแสดงหลายจุดบนแผนที่
- มีการกระจายจุดรอบ centroid จังหวัด (deterministic jitter) เพื่อไม่ให้ทับกัน
- Tooltip แสดง `risk score`, `rainfall`, `water level`, `status`, `time`
- ถ้าข้อมูลเยอะ สามารถจำกัดด้วย `Max points on map` ใน sidebar

## Notes
- dataset ปัจจุบันไม่มีพิกัดรายแถวจริง (`lat/lon`) จึงใช้ centroid + jitter เพื่อ visualization
- ค่า `risk_score` เป็น baseline heuristic ควรปรับ weight ตามบริบทจริง
