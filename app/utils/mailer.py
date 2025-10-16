from flask_mail import Message
from app.extensions import mail
from flask import render_template
from flask import current_app # <-- 1. เพิ่มการ import current_app

def send_security_report_email(recipient, subject, report_data, pdf_attachment=None, pdf_filename=None):
    """
    ส่งอีเมลรายงานความปลอดภัยพร้อมไฟล์ PDF ที่แนบ
    """
    try:
        # 2. ดึงอีเมลผู้ส่งมาจากไฟล์คอนฟิก
        sender_email = current_app.config.get('MAIL_USERNAME')

        # 3. เพิ่มพารามิเตอร์ sender เข้าไปใน Message object
        msg = Message(subject,
                      sender=sender_email, # <-- เพิ่มบรรทัดนี้
                      recipients=[recipient])
        
        msg.html = render_template('email/security_report.html', report_data=report_data)

        if pdf_attachment and pdf_filename:
            msg.attach(pdf_filename, "application/pdf", pdf_attachment)
        
        mail.send(msg)
        return True, "Email sent successfully"
    except Exception as e:
        return False, str(e)



# from flask_mail import Message
# from app.extensions import mail
# # from flask import render_template # ปิดการใช้งาน template ชั่วคราว
# from flask import current_app

# def send_security_report_email(recipient, subject, report_data, pdf_attachment=None, pdf_filename=None):
#     """
#                        recipients=[recipient],
#                       body="This is a plain text email to test spam filters. No attachments or HTML." # <-- ใช้ body แทน html
#                     )
        
#         # --- ส่วนของ HTML และไฟล์แนบที่ปิดการใช้งานชั่วคราว ---
#         # msg.html = render_template('email/security_report.html', report_data=report_data)
#         #
#         # if pdf_attachment and pdf_filename:
#         #     msg.attach(pdf_filename, "application/pdf", pdf_attachment)
#         # ----------------------------------------------------
        
#         mail.send(msg)
#         return True, "Email sent successfully (Plain Text Test)"
#     except Exception as e:
#         return False, str(e)         ส่งอีเมลรายงานความปลอดภัย (โหมดทดสอบ: ส่งเป็นข้อความธรรมดา)
#     """
#     try:
#         sender_email = current_app.config.get('MAIL_USERNAME')

#         # สร้าง Message object โดยใช้ `body` ที่เป็นข้อความธรรมดา
#         # และเปลี่ยนหัวข้อเรื่องเพื่อทดสอบ
#         msg = Message(subject="[Test] Security Scan Plain Text", # <-- เปลี่ยนหัวข้อชั่วคราว
#                       sender=sender_email,
  