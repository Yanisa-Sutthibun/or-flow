# -*- coding: utf-8 -*-
"""
demo_app.py — 🧪 จุดเข้าแอป DEMO (or-flow-demo)
════════════════════════════════════════════════
ทำไมต้องมีไฟล์นี้: Streamlit Cloud ไม่อนุญาตให้ deploy repo+branch+ไฟล์
เดิมซ้ำเป็นแอปที่สอง — ไฟล์นี้จึงเป็น "ประตูที่สอง" ที่ชี้เข้าโค้ดก้อนเดียวกัน
ทุกประการ (ไม่มีโค้ดสำเนา ไม่ต้องดูแลเพิ่ม)

พฤติกรรม demo/production ไม่ได้ตัดสินที่ไฟล์นี้ — ตัดสินที่ Secrets:
  instance_mode = "demo" + db_schema = "demo"  → ระบบสาธิต
(ดู DOC/ขั้นตอนสร้างระบบ_DEMO.txt และ DOC/secrets_DEMO_template.txt)
"""
import main_or_app

main_or_app.main()
