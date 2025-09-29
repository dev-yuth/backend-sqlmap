# 🚀 Flask Project Setup Guide

## 📦 เตรียม Virtual Environment

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 🔧 ติดตั้ง Dependencies

อัปเดตเครื่องมือพื้นฐาน:
```powershell
pip install --upgrade pip setuptools wheel
```

ติดตั้ง dependencies ที่จำเป็น:
```powershell
pip install Flask Flask-RESTful Flask-Cors Flask-SQLAlchemy PyMySQL Flask-Migrate Flask-JWT-Extended marshmallow
```

### 📑 รายละเอียดแพ็กเกจ
- **Flask** — เว็บ framework หลัก  
- **Flask-RESTful** — สำหรับสร้าง REST API (Resource-based)  
- **Flask-Cors** — รองรับ CORS (Cross-Origin Resource Sharing)  
- **Flask-SQLAlchemy** — ORM เชื่อมต่อ DB  
- **PyMySQL** — MySQL driver  
- **Flask-Migrate** — จัดการ database migrations (ใช้ Alembic)  
- **Flask-JWT-Extended** — ทำ JWT Authentication  
- **marshmallow** — (Optional) Schema & Data Validation  

บันทึก dependencies ลงไฟล์:
```powershell
pip freeze > requirements.txt
```

ติดตั้งจากไฟล์ (ถ้ามีการ clone โปรเจกต์มาใหม่):
```powershell
pip install -r requirements.txt
```

---

## ⚙️ ตั้งค่า Environment Variable

```powershell
$env:FLASK_APP="manage.py"
```

---

## 🗄️ Database Migration Commands

### 1. สร้างโฟลเดอร์ `migrations` (ครั้งแรกครั้งเดียว)
```powershell
python -m flask --app manage.py db init
```

### 2. สร้างไฟล์ Migration (autogenerate จาก models)
```powershell
python -m flask --app manage.py db migrate -m "create users table"
```

### 3. อัปเดตฐานข้อมูลตาม migration
```powershell
python -m flask --app manage.py db upgrade
```

---

## ✅ สรุปการใช้งาน

1. Clone โปรเจกต์  
2. สร้างและ activate `.venv`  
3. ติดตั้ง dependencies (`pip install -r requirements.txt`)  
4. ตั้งค่า `$env:FLASK_APP="manage.py"`  
5. ใช้ `flask db migrate` และ `flask db upgrade` เพื่อ sync database  
