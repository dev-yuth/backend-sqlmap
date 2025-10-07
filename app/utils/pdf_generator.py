# app/utils/pdf_generator.py
import os
import datetime
from typing import List, Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.lib.units import cm


THAI_FONT_NAME = "Sarabun"

# หา path ของโฟลเดอร์ app/fonts
project_app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
font_dir = os.path.join(project_app_dir, "fonts")

# กำหนดไฟล์ฟอนต์ทั้ง 4 แบบ
font_files = {
    'regular': 'Sarabun-Regular.ttf',
    'bold': 'Sarabun-Bold.ttf',
    'italic': 'Sarabun-Italic.ttf',
    'bolditalic': 'Sarabun-BoldItalic.ttf'
}

# ลงทะเบียนฟอนต์ครั้งเดียวตอน import module
try:
    if not os.path.exists(font_dir):
        raise FileNotFoundError(f"Font directory not found: {font_dir}")
    
    registered_fonts = {}
    for variant, filename in font_files.items():
        font_path = os.path.join(font_dir, filename)
        if not os.path.exists(font_path):
            continue
        
        font_name = f"{THAI_FONT_NAME}-{variant}" if variant != 'regular' else THAI_FONT_NAME
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        registered_fonts[variant] = font_name
    
    if 'regular' not in registered_fonts:
        raise FileNotFoundError("Sarabun-Regular.ttf is required but not found")
    
    registerFontFamily(
        THAI_FONT_NAME,
        normal=registered_fonts.get('regular', THAI_FONT_NAME),
        bold=registered_fonts.get('bold', registered_fonts['regular']),
        italic=registered_fonts.get('italic', registered_fonts['regular']),
        boldItalic=registered_fonts.get('bolditalic', registered_fonts['regular'])
    )
    
    print(f"✅ Registered Sarabun font family successfully")
    
except Exception as e:
    print(f"❌ Error: Thai font registration failed: {e}")
    raise


def thai_datetime_str() -> str:
    """สร้างสตริงวันที่ภาษาไทย"""
    months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
              'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
    d = datetime.datetime.now()
    return f"{d.day:02d} {months[d.month-1]} {d.year+543} เวลา {d.hour:02d}:{d.minute:02d} น."


def generate_sqlmap_pdf_report(results: List[Dict[str, Any]], output_filename: str = None) -> str:
    """
    สร้างรายงาน PDF จากผลการสแกน SQLMap
    
    Args:
        results: รายการผลการสแกน (list of dict)
        output_filename: ชื่อไฟล์ที่ต้องการ (ถ้าไม่ระบุจะสร้างอัตโนมัติ)
    
    Returns:
        str: path แบบเต็มของไฟล์ PDF ที่สร้าง
    """
    # กำหนดโฟลเดอร์สำหรับเก็บ PDF
    output_dir = os.path.join(os.getcwd(), "app", "files")
    os.makedirs(output_dir, exist_ok=True)
    
    # สร้างชื่อไฟล์ถ้าไม่ได้ระบุ
    if not output_filename:
        timestamp = int(datetime.datetime.now().timestamp())
        output_filename = f"sqlmap_report_{timestamp}.pdf"
    
    pdf_path = os.path.join(output_dir, output_filename)

    # สร้าง PDF Document
    doc = SimpleDocTemplate(
        pdf_path, 
        pagesize=A4,
        rightMargin=2*cm, 
        leftMargin=2*cm,
        topMargin=2*cm, 
        bottomMargin=2*cm
    )

    # ตั้งค่า styles
    styles = getSampleStyleSheet()
    for key in styles.byName:
        try:
            styles[key].fontName = THAI_FONT_NAME
        except Exception:
            pass

    story = []

    # ===== Header =====
    story.append(Paragraph("รายงานผลการสแกน SQLMap", styles["Title"]))
    story.append(Paragraph(f"จัดทำเมื่อ: {thai_datetime_str()}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # ===== Summary =====
    total_items = len(results)

    # รวมชื่อฐานข้อมูลทั้งหมดจากทุก result แล้วตัดชื่อซ้ำออก
    all_db_names = set()
    for r in results:
        db_names = r.get("listDb", {}).get("names", [])
        all_db_names.update(db_names)
    total_db_names = len(all_db_names)

    # นับ payload ที่ไม่ซ้ำกันจาก findings ของทุก parameters ในทุกผลลัพธ์
    unique_payloads = set()
    for r in results:
        for p in r.get("parametersRaw", []):
            for f in p.get("findings", []):
                payload = f.get("payload")
                if payload:
                    unique_payloads.add(payload)
    total_params = len(unique_payloads)

    success_count = sum(1 for r in results if r.get("ok"))

    story.append(Paragraph("สรุปผลการสแกน", styles["Heading2"]))
    summary_data = [
        ["รายการที่สแกนทั้งหมด:", f"{total_items} รายการ"],
        ["สแกนสำเร็จ:", f"{success_count} รายการ"],
        ["ล้มเหลว:", f"{total_items - success_count} รายการ"],
        ["ฐานข้อมูลที่พบรวม:", f"{total_db_names} ฐาน "],
        ["พารามิเตอร์ (payload) ที่ไม่ซ้ำ:", f"{total_params} payloads"],
    ]
        
    summary_table = Table(summary_data, colWidths=[6*cm, 9*cm])
    summary_table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (0,-1), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,-1), THAI_FONT_NAME),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # ===== Details per URL =====
    for idx, r in enumerate(results, 1):
        story.append(Paragraph(f"รายการที่ {idx}", styles["Heading2"]))
        story.append(Paragraph(f"URL: {r.get('url', 'N/A')}", styles["Normal"]))
        story.append(Paragraph(
            f"สถานะ: {'✅ สำเร็จ' if r.get('ok') else '❌ ล้มเหลว'}", 
            styles["Normal"]
        ))
        
        # แสดง error ถ้ามี
        if not r.get('ok') and r.get('error'):
            story.append(Paragraph(f"ข้อผิดพลาด: {r.get('error')}", styles["Normal"]))
        
        story.append(Spacer(1, 6))

        # --- Databases ---
        list_db = r.get("listDb", {})
        db_names = list_db.get("names", [])
        db_count = list_db.get("count", 0)

        story.append(Paragraph(f"ฐานข้อมูลที่พบ ({db_count} ฐาน):", styles["Heading3"]))
        if db_names:
            db_data = [["ลำดับ", "ชื่อฐานข้อมูล"]] + \
                      [[str(i+1), name] for i, name in enumerate(db_names)]
            db_table = Table(db_data, colWidths=[2*cm, 13*cm])
            db_table.setStyle(TableStyle([
                ("GRID", (0,0), (-1,-1), 0.5, colors.black),
                ("BACKGROUND", (0,0), (-1,0), colors.grey),
                ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
                ("FONTNAME", (0,0), (-1,-1), THAI_FONT_NAME),
                ("FONTSIZE", (0,0), (-1,-1), 10),
                ("ALIGN", (0,0), (0,-1), "CENTER"),
            ]))
            story.append(db_table)
        else:
            story.append(Paragraph("ไม่พบฐานข้อมูล", styles["Normal"]))
        story.append(Spacer(1, 6))

        # --- Parameters ---
        params = r.get("parametersRaw", [])
        story.append(Paragraph(
            f"รายละเอียดพารามิเตอร์ที่มีช่องโหว่ ({len(params)} พารามิเตอร์):", 
            styles["Heading3"]
        ))
        
        if params:
            for p_idx, p in enumerate(params, 1):
                story.append(Paragraph(
                    f"พารามิเตอร์ที่ {p_idx}: {p.get('parameter', 'N/A')} "
                    f"(ตำแหน่ง: {p.get('location', 'N/A')})", 
                    styles["Normal"]
                ))
                
                findings = p.get("findings", [])
                if findings:
                    for f_idx, f in enumerate(findings, 1):
                        story.append(Paragraph(
                            f"  └─ ช่องโหว่ที่ {f_idx}:", 
                            styles["Normal"]
                        ))
                        story.append(Paragraph(
                            f"     • ประเภท: {f.get('type', 'N/A')}", 
                            styles["Normal"]
                        ))
                        story.append(Paragraph(
                            f"     • หัวข้อ: {f.get('title', 'N/A')}", 
                            styles["Normal"]
                        ))
                        
                        payload = f.get('payload', 'N/A')
                        if len(payload) > 100:
                            payload = payload[:100] + "..."
                        story.append(Paragraph(
                            f"     • Payload: {payload}", 
                            styles["Normal"]
                        ))
                        story.append(Spacer(1, 3))
                
                story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(
                "✅ ไม่พบพารามิเตอร์ที่มีช่องโหว่", 
                styles["Normal"]
            ))

        # ขึ้นหน้าใหม่สำหรับรายการถัดไป (ยกเว้นรายการสุดท้าย)
        if idx < len(results):
            story.append(PageBreak())

    # สร้าง PDF
    doc.build(story)
    print(f"✅ PDF Report generated: {pdf_path}")
    
    return pdf_path


def generate_simple_report(title: str, data: Dict[str, Any], output_filename: str = None) -> str:
    """
    สร้างรายงาน PDF แบบง่าย (สำหรับใช้งานทั่วไป)
    
    Args:
        title: หัวข้อรายงาน
        data: ข้อมูลที่ต้องการแสดง (dict)
        output_filename: ชื่อไฟล์
    
    Returns:
        str: path ของไฟล์ PDF
    """
    output_dir = os.path.join(os.getcwd(), "app", "files")
    os.makedirs(output_dir, exist_ok=True)
    
    if not output_filename:
        timestamp = int(datetime.datetime.now().timestamp())
        output_filename = f"report_{timestamp}.pdf"
    
    pdf_path = os.path.join(output_dir, output_filename)
    
    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    
    styles = getSampleStyleSheet()
    for key in styles.byName:
        try:
            styles[key].fontName = THAI_FONT_NAME
        except Exception:
            pass
    
    story = []
    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(f"จัดทำเมื่อ: {thai_datetime_str()}", styles["Normal"]))
    story.append(Spacer(1, 12))
    
    # แสดงข้อมูลเป็นตาราง
    table_data = [["หัวข้อ", "ข้อมูล"]]
    for key, value in data.items():
        table_data.append([str(key), str(value)])
    
    table = Table(table_data, colWidths=[6*cm, 9*cm])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,-1), THAI_FONT_NAME),
        ("FONTSIZE", (0,0), (-1,-1), 10),
    ]))
    story.append(table)
    
    doc.build(story)
    return pdf_path