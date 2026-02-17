# Deploy บน Render (สำหรับโชว์ผลงาน CV)

## เตรียมข้อมูล
เนื่องจาก CSV ขนาด 1M rows ใหญ่เกินไป แนะนำสร้าง sample ขนาดเล็กสำหรับ demo:

```bash
# สร้าง sample 10,000 rows
head -n 10001 /Users/thanakorn/Desktop/thailand_flood_mockup_1M.csv > data/thailand_flood_sample.csv
```

## ขั้นตอน Deploy

### 1. Push โปรเจกต์ขึ้น GitHub
```bash
cd /Users/thanakorn/Desktop/Automated-Flood-Monitoring-Pipeline
git init
git add .
git commit -m "Initial commit - Flood Monitoring Pipeline"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/flood-monitoring.git
git push -u origin main
```

### 2. Deploy บน Render
1. ไปที่ https://render.com (สมัครฟรี)
2. คลิก **New +** → **Blueprint**
3. เชื่อมต่อ GitHub repository
4. Render จะอ่าน `render.yaml` และสร้าง:
   - PostgreSQL database (ฟรี)
   - Web Service สำหรับ Streamlit dashboard (ฟรี)

### 3. Setup Database (ครั้งเดียว)
หลัง deploy เสร็จ:
1. ไปที่ dashboard → เลือก **flood-monitoring-dashboard**
2. คลิก **Shell** tab
3. รันคำสั่ง:
```bash
bash scripts/render_setup.sh
```

### 4. เข้าใช้งาน
- Dashboard URL: `https://flood-monitoring-dashboard.onrender.com`
- Database: เชื่อมต่ออัตโนมัติผ่าน environment variable

## ข้อจำกัด Free Plan
- Web service จะ sleep หลังไม่มีคนใช้ 15 นาที (ใช้เวลา ~30 วินาทีในการ wake up)
- Database: 1GB storage, 97 ชั่วโมง/เดือน
- เหมาะสำหรับ demo/portfolio

## Tips สำหรับ CV
- เพิ่ม screenshot ของ dashboard ใน README
- อธิบาย architecture และ tech stack
- ใส่ live demo link
- เขียน case study สั้นๆ ว่าแก้ปัญหาอะไร

## Troubleshooting
หาก dashboard ไม่แสดงข้อมูล:
1. ตรวจสอบ logs: Dashboard → Logs tab
2. ตรวจสอบว่ารัน `render_setup.sh` แล้ว
3. ตรวจสอบว่า CSV file อยู่ใน repo
