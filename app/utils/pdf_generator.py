# app/utils/pdf_generator.py
import os
import datetime
from typing import List, Dict, Any
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.platypus import BaseDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Frame, PageTemplate
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

THAI_FONT_NAME = "Sarabun"
THAI_FONT_BOLD_NAME = "Sarabun-bold"

# --- Font Registration ---
project_app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
font_dir = os.path.join(project_app_dir, "fonts")

font_files = {
    'regular': 'Sarabun-Regular.ttf',
    'bold': 'Sarabun-Bold.ttf',
    'italic': 'Sarabun-Italic.ttf',
    'bolditalic': 'Sarabun-BoldItalic.ttf'
}

try:
    if not os.path.exists(font_dir):
        raise FileNotFoundError(f"Font directory not found: {font_dir}")

    registered_fonts = {}
    for variant, filename in font_files.items():
        font_path = os.path.join(font_dir, filename)
        if not os.path.exists(font_path): continue
        font_name = f"{THAI_FONT_NAME}-{variant}" if variant != 'regular' else THAI_FONT_NAME
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        registered_fonts[variant] = font_name

    if 'regular' not in registered_fonts or 'bold' not in registered_fonts:
        raise FileNotFoundError("Sarabun-Regular.ttf and Sarabun-Bold.ttf are required.")

    THAI_FONT_BOLD_NAME = registered_fonts.get('bold')

    registerFontFamily(
        THAI_FONT_NAME,
        normal=registered_fonts.get('regular'),
        bold=registered_fonts.get('bold'),
        italic=registered_fonts.get('italic'),
        boldItalic=registered_fonts.get('bolditalic')
    )
    print(f"✅ Registered Sarabun font family successfully")

except Exception as e:
    print(f"❌ Error: Thai font registration failed: {e}")
    raise

# --- Helper Functions ---
def thai_datetime_str() -> str:
    """Creates a full Thai date and time string."""
    months = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
              'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
    d = datetime.datetime.now()
    return f"วันที่ {d.day} {months[d.month-1]} พ.ศ. {d.year+543} เวลา {d.hour:02d}:{d.minute:02d} น."

def get_custom_styles():
    """Gets the default stylesheet and modifies it with custom Thai font settings."""
    styles = getSampleStyleSheet()
    base_font_name = THAI_FONT_NAME
    bold_font_name = THAI_FONT_BOLD_NAME

    styles['Normal'].fontName = base_font_name
    styles['Normal'].fontSize = 11
    styles['Normal'].leading = 15
    styles['Title'].fontName = bold_font_name
    styles['Title'].fontSize = 22
    styles['Title'].alignment = TA_CENTER
    styles['Heading1'].fontName = bold_font_name
    styles['Heading1'].fontSize = 18
    styles['Heading1'].textColor = colors.HexColor("#1A237E")
    styles['Heading2'].fontName = bold_font_name
    styles['Heading2'].fontSize = 15
    styles['Heading2'].textColor = colors.HexColor("#283593")
    styles['Heading3'].fontName = bold_font_name
    styles['Heading3'].fontSize = 12
    styles['Heading3'].textColor = colors.HexColor("#3949AB")
    
    if 'Code' not in styles.byName:
        styles.add(ParagraphStyle(name='Code'))
    styles['Code'].fontName = 'Courier'
    styles['Code'].fontSize = 9
    styles['Code'].leading = 11
    styles['Code'].textColor = colors.HexColor("#37474F")
    styles['Code'].backColor = colors.HexColor("#ECEFF1")
    styles['Code'].leftIndent = 6
    styles['Code'].rightIndent = 6
    styles['Code'].firstLineIndent = 6
    styles['Code'].wordWrap = 'CJK'

    styles.add(ParagraphStyle(name='SubTitle', parent=styles['Normal'], fontSize=12, alignment=TA_CENTER, textColor=colors.darkgrey))
    styles.add(ParagraphStyle(name='URLStyle', parent=styles['Normal'], textColor=colors.blue, wordWrap='break'))
    styles.add(ParagraphStyle(name='SuccessStatus', parent=styles['Normal'], textColor=colors.HexColor("#2E7D32")))
    styles.add(ParagraphStyle(name='ErrorStatus', parent=styles['Normal'], textColor=colors.HexColor("#C62828")))
    
    return styles

# --- Custom Document Template with Header/Footer ---
class ReportDocTemplate(BaseDocTemplate):
    """Custom document template with header, footer, and a two-pass page count."""
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        self.page_count = 0
        self.allowSplitting = 1
        template = PageTemplate(id='main_template', onPage=self._header_footer, frames=[
            Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='main_frame')
        ])
        self.addPageTemplates([template])
        
    def _header_footer(self, canvas, doc):
        """Draws the header and footer on each page."""
        canvas.saveState()
        canvas.setFont(THAI_FONT_NAME, 9)
        
        # Header
        canvas.drawString(self.leftMargin, A4[1] - 1.5*cm, "รายงานผลการทดสอบความปลอดภัย (SQLMap Scan)")
        canvas.setStrokeColorRGB(0.8, 0.8, 0.8)
        canvas.line(self.leftMargin, A4[1] - 1.7*cm, A4[0] - self.rightMargin, A4[1] - 1.7*cm)

        # Footer
        canvas.drawString(self.leftMargin, 1.5*cm, "Generated by Security Assessment Platform")
        page_num_text = f"หน้า {doc.page} / {self.page_count}"
        canvas.drawCentredString(A4[0]/2, 1.5*cm, page_num_text)
        canvas.drawRightString(A4[0] - self.rightMargin, 1.5*cm, f"พิมพ์เมื่อ: {datetime.datetime.now():%d/%m/%Y %H:%M}")
        canvas.line(self.leftMargin, 2.0*cm, A4[0] - self.rightMargin, 2.0*cm)
        
        canvas.restoreState()

    def afterFlowable(self, flowable):
        """Register page number after each flowable is processed."""
        if hasattr(self, 'page'):
            self.page_count = self.page

# --- Main PDF Generation Logic ---
def generate_sqlmap_pdf_report(results: List[Dict[str, Any]], output_dir: str, output_filename: str) -> str:
    """Creates a professionally styled PDF report from SQLMap scan results."""
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, output_filename)

    styles = get_custom_styles()
    story = []

    # ===== Title Page =====
    story.append(Spacer(1, 4*cm))
    story.append(Paragraph("รายงานผลการสแกนช่องโหว่ SQL Injection", styles["Title"]))
    story.append(Paragraph("ด้วยเครื่องมือ SQLMap", styles["SubTitle"]))
    story.append(Spacer(1, 8*cm))
    story.append(Paragraph(f"จัดทำเมื่อ {thai_datetime_str()}", styles["Normal"]))
    story.append(PageBreak())

    # ===== Executive Summary =====
    story.append(Paragraph("บทสรุปช่องโหว่ SQL Injection", styles["Heading1"]))
    total_items = len(results)
    all_db_names = {name for r in results for name in r.get("listDb", {}).get("names", [])}
    unique_payloads = {f.get("payload") for r in results for p in r.get("parametersRaw", []) for f in p.get("findings", []) if f.get("payload")}
    success_count = sum(1 for r in results if r.get("ok"))
    summary_data = [
        [Paragraph(f"<b>{label}</b>", styles['Normal']), Paragraph(str(value), styles['Normal'])] for label, value in [
            ("รายการที่สแกนทั้งหมด", f"{total_items} รายการ"),
            ("สแกนสำเร็จ", f"{success_count} รายการ"),
            ("ล้มเหลว", f"{total_items - success_count} รายการ"),
            ("ฐานข้อมูลที่พบ (ไม่ซ้ำกัน)", f"{len(all_db_names)} ฐานข้อมูล"),
            ("Payload ที่พบ (ไม่ซ้ำกัน)", f"{len(unique_payloads)} รูปแบบ"),
        ]
    ]
    summary_table = Table(summary_data, colWidths=[6.5*cm, 9.5*cm], hAlign='LEFT')
    summary_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#E3F2FD")),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(summary_table)
    story.append(PageBreak())

    # ===== Detailed Scan Results =====
    story.append(Paragraph("รายละเอียดผลการสแกน", styles["Heading1"]))
    for idx, r in enumerate(results, 1):
        story.append(Paragraph(f"รายการที่ {idx}: ผลการสแกน URL", styles["Heading2"]))
        story.append(Paragraph("<b>URL เป้าหมาย:</b>", styles['Normal']))
        story.append(Paragraph(r.get('url', 'N/A'), styles["URLStyle"]))
        status_text = "<b>สถานะ:</b> " + (f"<font color='#2E7D32'>✅ สำเร็จ</font>" if r.get('ok') else f"<font color='#C62828'>❌ ล้มเหลว</font>")
        story.append(Paragraph(status_text, styles["Normal"]))
        if not r.get('ok') and r.get('error'): story.append(Paragraph(f"<b>ข้อผิดพลาด:</b> {r.get('error')}", styles["ErrorStatus"]))
        story.append(Spacer(1, 10))

        db_names = r.get("listDb", {}).get("names", [])
        story.append(Paragraph(f"ฐานข้อมูลที่พบ ({len(db_names)} ฐานข้อมูล)", styles["Heading3"]))
        if db_names: story.append(Table([[Paragraph(f"<b>{i+1}. {name}</b>", styles['Normal'])] for i, name in enumerate(db_names)], colWidths=[15*cm], hAlign='LEFT', style=[('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey), ('LEFTPADDING', (0,0), (-1,-1), 8)]))
        else: story.append(Paragraph("ไม่พบฐานข้อมูล", styles["Normal"]))
        story.append(Spacer(1, 12))

        params = r.get("parametersRaw", [])
        story.append(Paragraph(f"พารามิเตอร์ที่พบช่องโหว่ ({len(params)} พารามิเตอร์)", styles["Heading3"]))
        if params:
            for p_idx, p in enumerate(params, 1):
                story.append(Paragraph(f"<b>{p_idx}. พารามิเตอร์: {p.get('parameter', 'N/A')}</b> (ตำแหน่ง: {p.get('location', 'N/A')})", styles['Normal']))
                
                findings = p.get("findings", [])
                if findings:
                    # ** FIX: Use a Table for better layout **
                    findings_data = []
                    for f in findings:
                        type_p = Paragraph(f"<b>ประเภท:</b> {f.get('type', 'N/A')}<br/><b>หัวข้อ:</b> {f.get('title', 'N/A')}", styles['Normal'])
                        payload_p = Paragraph(f.get('payload', 'N/A'), styles['Code'])
                        
                        # สร้างตารางย่อยสำหรับแต่ละ finding
                        inner_table = Table([
                            [Paragraph("<b>รายละเอียดช่องโหว่</b>", styles['Normal']), type_p],
                            [Paragraph("<b>Payload ที่ใช้ทดสอบ</b>", styles['Normal']), payload_p]
                        ], colWidths=[4.5*cm, 10*cm])
                        
                        inner_table.setStyle(TableStyle([
                            ('VALIGN', (0,0), (-1,-1), 'TOP'),
                            ('LEFTPADDING', (0,0), (-1,-1), 6),
                            ('TOPPADDING', (0,0), (-1,-1), 4),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                            ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
                            ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#f5f5f5")),
                        ]))
                        findings_data.append([inner_table])

                    # เพิ่ม findings ทั้งหมดในตารางหลักอันเดียว
                    findings_table = Table(findings_data, colWidths=[15*cm], style=[('LEFTPADDING', (0,0), (-1,-1), 12)])
                    story.append(findings_table)
                    story.append(Spacer(1, 8))

        else: story.append(Paragraph("✅ ไม่พบพารามิเตอร์ที่มีช่องโหว่", styles["SuccessStatus"]))
        if idx < len(results): story.append(PageBreak())
    
    # --- Build the PDF Document using the two-pass method ---
    doc = ReportDocTemplate(
        pdf_path, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2.5*cm,
        title="รายงานผลการสแกน SQLMap", author="Security Assessment Platform"
    )
    
    # First pass to count pages, second pass to build the final PDF
    doc.multiBuild(story)
    
    print(f"✅ PDF Report generated: {pdf_path}")
    return pdf_path

# --- Simple Report Generator ---
def generate_simple_report(title: str, data: Dict[str, Any], output_filename: str = None) -> str:
    output_dir = os.path.join(os.getcwd(), "app", "static", "reports", "general")
    os.makedirs(output_dir, exist_ok=True)
    
    if not output_filename:
        timestamp = int(datetime.datetime.now().timestamp())
        output_filename = f"report_{timestamp}.pdf"
    
    pdf_path = os.path.join(output_dir, output_filename)
    styles = get_custom_styles()
    
    story = []
    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(f"จัดทำเมื่อ: {thai_datetime_str()}", styles["Normal"]))
    story.append(Spacer(1, 12))
    
    table_data = [[Paragraph(f"<b>{key}</b>", styles['Normal']), Paragraph(str(value), styles['Normal'])] for key, value in data.items()]
    table_data.insert(0, [Paragraph("<b>หัวข้อ</b>", styles['Normal']), Paragraph("<b>ข้อมูล</b>", styles['Normal'])])
    
    table = Table(table_data, colWidths=[6*cm, 9*cm])
    table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
    story.append(table)
    
    doc = ReportDocTemplate(pdf_path, pagesize=A4, topMargin=2.5*cm, bottomMargin=2.5*cm)
    doc.multiBuild(story)
    
    return pdf_path