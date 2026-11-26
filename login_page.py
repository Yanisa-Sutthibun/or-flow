"""🔐 หน้าเข้าสู่ระบบ แบบ B (แผงซ้าย + ฟอร์มขวา) : มุกกี้เลือก 20 พ.ย. 2026 ลงโค้ด 21 พ.ย. 2026

แผงซ้าย = จำนวนผู้ป่วยวันนี้ 4 ช่วง (อ่านจาก snapshot บอร์ดกลาง cache 5 นาที นับอย่างเดียว ไม่มีชื่อ/HN)
+ พยาบาล pixel เดินถือเครื่องดื่ม + กล่อง "รู้หรือไม่" วน 18 ข้อ ข้อละ 8 วินาที (CSS ล้วน ไม่มี JS)
⛔ HTML ทั้งก้อนต้องอยู่บรรทัดเดียว (st.markdown ตัด <style> ถ้ามีบรรทัดว่าง)
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

_BKK = ZoneInfo('Asia/Bangkok')

# ☕ 26 พ.ย. 2026 (มุกกี้ส่งรูปต้นแบบมา): แก้วแบบมีฝา ถือในมือ · จังหวะ 1 ถือข้างตัว จังหวะ 2 ยกขึ้นระดับอก
# 🎨 25 พ.ย. 2026 (มุกกี้สั่ง): พยาบาล pixel รุ่นใหม่ ตัวเดียวกับในวิดีโอสาธิต เดิน 2 จังหวะ (nf0/nf1) ถือแก้วกาแฟมีไอร้อน
_SPRITE = '<svg width="64" height="92" viewBox="0 0 32 46" shape-rendering="crispEdges" aria-hidden="true" style="display:block;margin:8px auto 0"><ellipse cx="12" cy="45.2" rx="9" ry="1.2" fill="#000" fill-opacity=".28"></ellipse><g class="nf0"><path fill="#1a1f30" d="M9 1h7v1h-7zM6 2h3v1h-3zM16 2h3v1h-3zM5 3h1v1h-1zM19 3h1v1h-1zM4 4h1v1h-1zM20 4h1v1h-1zM3 5h1v1h-1zM21 5h1v1h-1zM2 6h1v1h-1zM22 6h1v1h-1zM1 7h1v1h-1zM23 7h1v1h-1zM1 8h1v1h-1zM23 8h1v1h-1zM0 9h1v1h-1zM24 9h1v1h-1zM0 10h1v1h-1zM24 10h1v1h-1zM0 11h1v1h-1zM24 11h1v1h-1zM0 12h1v1h-1zM24 12h1v1h-1zM1 13h23v1h-23zM1 14h1v1h-1zM23 14h1v1h-1zM1 15h1v1h-1zM7 15h2v1h-2zM15 15h2v1h-2zM23 15h1v1h-1zM1 16h1v1h-1zM7 16h2v1h-2zM15 16h2v1h-2zM23 16h1v1h-1zM5 17h15v1h-15zM5 18h1v1h-1zM19 18h1v1h-1zM5 19h1v1h-1zM19 19h1v1h-1zM3 20h1v1h-1zM5 20h1v1h-1zM19 20h1v1h-1zM21 20h1v1h-1zM4 21h2v1h-2zM19 21h2v1h-2zM5 22h1v1h-1zM19 22h1v1h-1zM5 23h15v1h-15zM5 24h1v1h-1zM9 24h7v1h-7zM19 24h1v1h-1zM2 25h4v1h-4zM19 25h4v1h-4zM2 26h1v1h-1zM5 26h1v1h-1zM19 26h1v1h-1zM22 26h1v1h-1zM2 27h1v1h-1zM5 27h1v1h-1zM19 27h1v1h-1zM22 27h1v1h-1zM2 28h1v1h-1zM5 28h1v1h-1zM19 28h6v1h-6zM2 29h1v1h-1zM5 29h1v1h-1zM19 29h2v1h-2zM24 29h1v1h-1zM2 30h1v1h-1zM5 30h1v1h-1zM19 30h2v1h-2zM23 30h3v1h-3zM2 31h1v1h-1zM5 31h1v1h-1zM19 31h2v1h-2zM23 31h1v1h-1zM25 31h1v1h-1zM2 32h1v1h-1zM5 32h1v1h-1zM19 32h2v1h-2zM23 32h1v1h-1zM25 32h1v1h-1zM2 33h4v1h-4zM19 33h2v1h-2zM24 33h1v1h-1zM2 34h1v1h-1zM5 34h1v1h-1zM19 34h6v1h-6zM2 35h4v1h-4zM19 35h1v1h-1zM5 36h15v1h-15zM7 37h1v1h-1zM11 37h1v1h-1zM13 37h1v1h-1zM17 37h1v1h-1zM7 38h1v1h-1zM11 38h1v1h-1zM13 38h1v1h-1zM17 38h1v1h-1zM7 39h1v1h-1zM11 39h1v1h-1zM13 39h1v1h-1zM17 39h1v1h-1zM7 40h1v1h-1zM11 40h1v1h-1zM13 40h6v1h-6zM7 41h1v1h-1zM11 41h1v1h-1zM13 41h1v1h-1zM18 41h1v1h-1zM7 42h12v1h-12zM7 43h1v1h-1zM12 43h1v1h-1zM7 44h6v1h-6z"></path><path fill="#1f6f55" d="M9 2h7v1h-7zM6 3h2v1h-2zM13 3h6v1h-6zM5 4h1v1h-1zM8 4h5v1h-5zM14 4h6v1h-6zM4 5h1v1h-1zM6 5h15v1h-15zM3 6h1v1h-1zM5 6h1v1h-1zM7 6h15v1h-15zM2 7h21v1h-21zM2 8h21v1h-21zM1 9h23v1h-23zM1 10h23v1h-23zM7 24h2v1h-2zM7 25h4v1h-4zM14 25h1v1h-1zM7 26h5v1h-5zM13 26h2v1h-2zM20 26h2v1h-2zM7 27h7v1h-7zM7 28h6v1h-6zM7 29h6v1h-6zM14 29h1v1h-1zM7 30h6v1h-6zM14 30h1v1h-1zM7 31h6v1h-6zM21 31h2v1h-2zM7 32h8v1h-8zM21 32h2v1h-2zM7 33h8v1h-8zM7 34h8v1h-8zM6 35h9v1h-9z"></path><path fill="#2d8c6c" d="M8 3h5v1h-5zM6 4h2v1h-2zM13 4h1v1h-1zM5 5h1v1h-1zM4 6h1v1h-1zM6 24h1v1h-1zM6 25h1v1h-1zM6 26h1v1h-1zM6 27h1v1h-1zM6 28h1v1h-1zM6 29h1v1h-1zM6 30h1v1h-1zM6 31h1v1h-1zM6 32h1v1h-1zM6 33h1v1h-1zM6 34h1v1h-1z"></path><path fill="#ffffff" d="M6 6h1v1h-1z"></path><path fill="#185844" d="M1 11h23v1h-23zM1 12h23v1h-23zM16 24h3v1h-3zM15 25h4v1h-4zM3 26h2v1h-2zM15 26h4v1h-4zM3 27h2v1h-2zM15 27h4v1h-4zM20 27h2v1h-2zM3 28h2v1h-2zM13 28h6v1h-6zM3 29h2v1h-2zM13 29h1v1h-1zM15 29h4v1h-4zM3 30h2v1h-2zM13 30h1v1h-1zM15 30h4v1h-4zM3 31h2v1h-2zM13 31h6v1h-6zM3 32h2v1h-2zM15 32h4v1h-4zM15 33h4v1h-4zM15 34h4v1h-4zM15 35h4v1h-4zM8 37h3v1h-3zM14 37h3v1h-3zM8 38h3v1h-3zM14 38h3v1h-3zM8 39h3v1h-3zM14 39h3v1h-3zM8 40h3v1h-3zM8 41h3v1h-3z"></path><path fill="#5c3a28" d="M2 14h3v1h-3zM20 14h3v1h-3zM2 15h3v1h-3zM20 15h3v1h-3zM2 16h3v1h-3zM20 16h3v1h-3zM2 17h3v1h-3zM20 17h3v1h-3zM2 18h3v1h-3zM20 18h3v1h-3zM2 19h3v1h-3zM20 19h3v1h-3z"></path><path fill="#f7d4b2" d="M5 14h13v1h-13zM5 15h2v1h-2zM9 15h6v1h-6zM17 15h1v1h-1zM5 16h2v1h-2zM9 16h6v1h-6zM17 16h1v1h-1zM4 20h1v1h-1zM20 20h1v1h-1zM11 25h3v1h-3zM12 26h1v1h-1zM24 31h1v1h-1zM24 32h1v1h-1zM3 34h2v1h-2z"></path><path fill="#e4b892" d="M18 14h2v1h-2zM18 15h2v1h-2zM18 16h2v1h-2z"></path><path fill="#96d6c2" d="M6 18h13v1h-13zM6 19h13v1h-13zM6 21h13v1h-13zM6 22h13v1h-13z"></path><path fill="#78beaa" d="M6 20h13v1h-13z"></path><path fill="#ffffff" fill-opacity="0.78" d="M25 23h1v1h-1zM24 24h1v1h-1zM26 25h1v1h-1z"></path><path fill="#fafaf6" d="M14 27h1v1h-1zM21 33h3v1h-3zM14 41h4v1h-4zM8 43h4v1h-4z"></path><path fill="#965c34" d="M21 30h2v1h-2z"></path><path fill="#acabaa" d="M21 29h3v1h-3z"></path></g><g class="nf1"><path fill="#1a1f30" d="M9 0h7v1h-7zM6 1h3v1h-3zM16 1h3v1h-3zM5 2h1v1h-1zM19 2h1v1h-1zM4 3h1v1h-1zM20 3h1v1h-1zM3 4h1v1h-1zM21 4h1v1h-1zM2 5h1v1h-1zM22 5h1v1h-1zM1 6h1v1h-1zM23 6h1v1h-1zM1 7h1v1h-1zM23 7h1v1h-1zM0 8h1v1h-1zM24 8h1v1h-1zM0 9h1v1h-1zM24 9h1v1h-1zM0 10h1v1h-1zM24 10h1v1h-1zM0 11h1v1h-1zM24 11h1v1h-1zM1 12h23v1h-23zM1 13h1v1h-1zM23 13h1v1h-1zM1 14h1v1h-1zM7 14h2v1h-2zM15 14h2v1h-2zM23 14h1v1h-1zM1 15h1v1h-1zM7 15h2v1h-2zM15 15h2v1h-2zM23 15h1v1h-1zM5 16h15v1h-15zM5 17h1v1h-1zM19 17h1v1h-1zM5 18h1v1h-1zM19 18h1v1h-1zM3 19h1v1h-1zM5 19h1v1h-1zM19 19h1v1h-1zM21 19h1v1h-1zM4 20h2v1h-2zM19 20h2v1h-2zM5 21h1v1h-1zM19 21h1v1h-1zM5 22h15v1h-15zM5 23h1v1h-1zM9 23h7v1h-7zM19 23h1v1h-1zM2 24h4v1h-4zM16 24h5v1h-5zM2 25h1v1h-1zM5 25h1v1h-1zM16 25h1v1h-1zM21 25h1v1h-1zM2 26h1v1h-1zM5 26h1v1h-1zM16 26h1v1h-1zM20 26h3v1h-3zM2 27h1v1h-1zM5 27h1v1h-1zM16 27h1v1h-1zM19 27h1v1h-1zM22 27h1v1h-1zM2 28h1v1h-1zM5 28h1v1h-1zM16 28h1v1h-1zM19 28h1v1h-1zM22 28h1v1h-1zM2 29h1v1h-1zM5 29h1v1h-1zM16 29h1v1h-1zM19 29h2v1h-2zM22 29h1v1h-1zM2 30h1v1h-1zM5 30h1v1h-1zM16 30h5v1h-5zM22 30h1v1h-1zM2 31h1v1h-1zM5 31h1v1h-1zM19 31h3v1h-3zM2 32h4v1h-4zM19 32h1v1h-1zM2 33h1v1h-1zM5 33h1v1h-1zM19 33h1v1h-1zM2 34h4v1h-4zM19 34h1v1h-1zM5 35h15v1h-15zM7 36h1v1h-1zM11 36h1v1h-1zM13 36h1v1h-1zM17 36h1v1h-1zM7 37h1v1h-1zM11 37h1v1h-1zM13 37h1v1h-1zM17 37h1v1h-1zM7 38h1v1h-1zM11 38h1v1h-1zM13 38h1v1h-1zM17 38h1v1h-1zM7 39h1v1h-1zM11 39h1v1h-1zM13 39h1v1h-1zM17 39h1v1h-1zM7 40h7v1h-7zM17 40h1v1h-1zM7 41h1v1h-1zM12 41h2v1h-2zM17 41h1v1h-1zM7 42h12v1h-12zM13 43h1v1h-1zM18 43h1v1h-1zM13 44h6v1h-6z"></path><path fill="#1f6f55" d="M9 1h7v1h-7zM6 2h2v1h-2zM13 2h6v1h-6zM5 3h1v1h-1zM8 3h5v1h-5zM14 3h6v1h-6zM4 4h1v1h-1zM6 4h15v1h-15zM3 5h1v1h-1zM5 5h1v1h-1zM7 5h15v1h-15zM2 6h21v1h-21zM2 7h21v1h-21zM1 8h23v1h-23zM1 9h23v1h-23zM7 23h2v1h-2zM7 24h4v1h-4zM14 24h1v1h-1zM7 25h5v1h-5zM13 25h2v1h-2zM7 26h7v1h-7zM7 27h6v1h-6zM17 27h2v1h-2zM7 28h6v1h-6zM14 28h1v1h-1zM17 28h2v1h-2zM7 29h6v1h-6zM14 29h1v1h-1zM7 30h6v1h-6zM7 31h8v1h-8zM7 32h8v1h-8zM7 33h8v1h-8zM6 34h9v1h-9z"></path><path fill="#2d8c6c" d="M8 2h5v1h-5zM6 3h2v1h-2zM13 3h1v1h-1zM5 4h1v1h-1zM4 5h1v1h-1zM6 23h1v1h-1zM6 24h1v1h-1zM6 25h1v1h-1zM6 26h1v1h-1zM6 27h1v1h-1zM6 28h1v1h-1zM6 29h1v1h-1zM6 30h1v1h-1zM6 31h1v1h-1zM6 32h1v1h-1zM6 33h1v1h-1z"></path><path fill="#ffffff" d="M6 5h1v1h-1z"></path><path fill="#185844" d="M1 10h23v1h-23zM1 11h23v1h-23zM16 23h3v1h-3zM15 24h1v1h-1zM3 25h2v1h-2zM15 25h1v1h-1zM3 26h2v1h-2zM15 26h1v1h-1zM3 27h2v1h-2zM13 27h3v1h-3zM3 28h2v1h-2zM13 28h1v1h-1zM15 28h1v1h-1zM3 29h2v1h-2zM13 29h1v1h-1zM15 29h1v1h-1zM21 29h1v1h-1zM3 30h2v1h-2zM13 30h3v1h-3zM21 30h1v1h-1zM3 31h2v1h-2zM15 31h4v1h-4zM15 32h4v1h-4zM15 33h4v1h-4zM15 34h4v1h-4zM8 36h3v1h-3zM14 36h3v1h-3zM8 37h3v1h-3zM14 37h3v1h-3zM8 38h3v1h-3zM14 38h3v1h-3zM8 39h3v1h-3zM14 39h3v1h-3zM14 40h3v1h-3zM14 41h3v1h-3z"></path><path fill="#5c3a28" d="M2 13h3v1h-3zM20 13h3v1h-3zM2 14h3v1h-3zM20 14h3v1h-3zM2 15h3v1h-3zM20 15h3v1h-3zM2 16h3v1h-3zM20 16h3v1h-3zM2 17h3v1h-3zM20 17h3v1h-3zM2 18h3v1h-3zM20 18h3v1h-3z"></path><path fill="#f7d4b2" d="M5 13h13v1h-13zM5 14h2v1h-2zM9 14h6v1h-6zM17 14h1v1h-1zM5 15h2v1h-2zM9 15h6v1h-6zM17 15h1v1h-1zM4 19h1v1h-1zM20 19h1v1h-1zM11 24h3v1h-3zM12 25h1v1h-1zM20 27h2v1h-2zM20 28h2v1h-2zM3 33h2v1h-2z"></path><path fill="#e4b892" d="M18 13h2v1h-2zM18 14h2v1h-2zM18 15h2v1h-2z"></path><path fill="#96d6c2" d="M6 17h13v1h-13zM6 18h13v1h-13zM6 20h13v1h-13zM6 21h13v1h-13z"></path><path fill="#78beaa" d="M6 19h13v1h-13z"></path><path fill="#ffffff" fill-opacity="0.78" d="M24 21h1v1h-1zM23 22h1v1h-1zM25 23h1v1h-1z"></path><path fill="#fafaf6" d="M14 26h1v1h-1zM17 26h3v1h-3zM17 29h2v1h-2zM8 41h4v1h-4zM14 43h4v1h-4z"></path><path fill="#965c34" d="M17 25h4v1h-4z"></path></g></svg>'

_TIPS = ['<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>OR Flow ใช้ AI ทำนายเวลาการใช้ห้องผ่าตัด ตั้งแต่ผู้ป่วยเข้าห้อง (wheel-in) จนออกจากห้อง (wheel-out)', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>Turnover time คือ ช่วงเวลาตั้งแต่ผู้ป่วยเคสก่อนออกจากห้อง จนผู้ป่วยเคสถัดไปเข้าห้องเดียวกัน (นับเฉพาะช่วง 1 ถึง 90 นาที)', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>Utilization คือ ร้อยละการใช้ห้องผ่าตัดในเวลาราชการ คำนวณจาก เวลาที่ผู้ป่วยอยู่ในห้องช่วง 08:00 ถึง 16:00 ÷ (จำนวนห้องที่ใช้ × 480 นาที) × 100', '<span style="font-weight: 700; color: #1658B8">วิธีใช้ 1/5 : </span>ตอนเช้า อัปโหลดตารางผ่าตัดจาก HIS ที่ปุ่ม ⋯ มุมขวาบน', '<span style="font-weight: 700; color: #1658B8">วิธีใช้ 2/5 : </span>ผู้ป่วยมาถึงห้องรับ-ส่ง กด รับเข้า', '<span style="font-weight: 700; color: #1658B8">วิธีใช้ 3/5 : </span>ผู้ป่วยเข้าห้องผ่าตัด กด เข้าห้อง', '<span style="font-weight: 700; color: #1658B8">วิธีใช้ 4/5 : </span>ผ่าตัดเสร็จ ผู้ป่วยออกจากห้องผ่าตัด กด เสร็จ', '<span style="font-weight: 700; color: #1658B8">วิธีใช้ 5/5 : </span>ผู้ป่วยกลับตึกหรือกลับบ้าน กด จำหน่าย', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>หน้าจออัปเดตเองทุก 30 วินาที ไม่ต้องกด F5 ปรับรอบได้ที่ ตั้งค่า : การแสดงผล', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>อยากเห็นข้อมูลล่าสุดทันที กดปุ่ม 🔄 รีเฟรช มุมขวาบนได้เลย', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>กดพลาดไม่ต้องตกใจ กด ✏️ ท้ายแถว แล้วเลือก ย้อนกลับ ถอยกลับได้หนึ่งขั้น', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>ห้องที่ยังมีเคสผ่าตัดอยู่ จะกดเข้าห้องเคสถัดไปไม่ได้ จนกว่าเคสก่อนหน้าจะออกจากห้อง', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>เวลาที่ AI ทำนายเป็นค่าประมาณ พยาบาลกด ✏️ ปรับเองได้เสมอ', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>ระบบเก็บทั้งเวลาที่ AI ทำนายและเวลาที่พยาบาลปรับ ไว้เทียบกันในงานวิจัย', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>"จาก N เคส" ใต้ค่าทำนาย ยิ่งเลขมาก ยิ่งน่าเชื่อถือ', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>ช่วงเวลาที่ทำนายยิ่งกว้าง แปลว่าเคสนั้นเวลาแกว่งได้มาก ควรเผื่อเวลาไว้', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>แถบคิวถัดไปบอกเวลาที่ควรไปตามผู้ป่วยมารอ ผู้ป่วยจะได้ไม่ต้องรอหน้าห้องเกิน 1 ชั่วโมง', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>ถ้าในห้องกดกระดิ่ง 🔔 แถบจะเป็นสีเขียวพร้อมเสียงติ๊ง ไปตามผู้ป่วยได้ทันที']

_CSS = '.orl-panel{background:#10263D;color:#FFFFFF;border-radius:20px;padding:36px 36px 28px;display:flex;flex-direction:column;gap:20px;margin-top:24px}.orl-brand{display:flex;align-items:center;gap:12px;font-size:22px;font-weight:700}.orl-logo{width:44px;height:44px;border-radius:12px;background:rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center}.orl-h1{font-size:34px;font-weight:700;line-height:1.35;margin-top:8px}.orl-sub{font-size:17px;line-height:1.7;color:#C9D6E3}.orl-box{display:flex;flex-direction:column;gap:16px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:20px 20px 0;overflow:hidden}.orl-boxh{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;font-size:15px}.orl-boxh span{font-size:13px;color:#A9BBCC}.orl-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.orl-cell{display:flex;flex-direction:column;gap:4px;background:rgba(255,255,255,.06);border-radius:12px;padding:12px}.orl-cl{display:flex;align-items:center;gap:6px;font-size:13px;color:#DCE7F2}.orl-cl span{width:8px;height:8px;border-radius:4px;display:inline-block}.orl-num{font-size:32px;font-weight:700;line-height:1.2}.orl-stage{position:relative;height:210px;margin:0 -20px;border-top:1px dashed rgba(255,255,255,.14);background:rgba(255,255,255,.03)}.orl-bubble{position:absolute;left:20px;right:20px;top:14px;background:#FFFFFF;border:2px solid #0B1A29;border-radius:4px;padding:10px 14px;box-shadow:4px 4px 0 rgba(0,0,0,.25)}.orl-tips{display:grid;font-size:14px;line-height:1.55;color:#12212E}.orl-tail{position:absolute;left:26px;bottom:-7px;width:10px;height:10px;background:#FFFFFF;border-right:2px solid #0B1A29;border-bottom:2px solid #0B1A29;transform:rotate(45deg)}.orl-floor{position:absolute;left:0;right:0;bottom:14px;height:2px;background:rgba(255,255,255,.16)}.orl-foot{font-size:13px;line-height:1.6;color:#A9BBCC}.orl-fh{margin:8px 0 6px}.orl-fh1{font-size:28px;font-weight:700;color:#12212E}.orl-fh2{font-size:15px;color:#5B6B7B;margin-top:4px}@media (max-width:640px){.orl-h1{font-size:26px}.orl-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.orl-panel{padding:24px}}.walker{position:absolute;left:0;bottom:14px;width:100px;height:100px;animation:orfMove 14s linear infinite alternate}.flip{width:100px;height:100px;animation:orfFlip 28s steps(1,end) infinite}.fa{opacity:1;animation:orfFa .6s steps(1,end) infinite}.fb{opacity:0;animation:orfFb .6s steps(1,end) infinite}.fc{opacity:0;animation:orfFc .6s steps(1,end) infinite}.bob{animation:orfBob .3s steps(1,end) infinite}.nf0{animation:orfF0 .6s steps(1,end) infinite}.nf1{animation:orfF1 .6s steps(1,end) infinite}@keyframes orfF0{0%{opacity:1}50%{opacity:0}}@keyframes orfF1{0%{opacity:0}50%{opacity:1}}@keyframes orfMove{from{left:0}to{left:calc(100% - 100px)}}@keyframes orfFlip{0%{transform:scaleX(1)}50%{transform:scaleX(-1)}100%{transform:scaleX(-1)}}@keyframes orfFa{0%{opacity:1}25%{opacity:0}50%{opacity:1}75%{opacity:0}100%{opacity:0}}@keyframes orfFb{0%{opacity:0}25%{opacity:1}50%{opacity:0}100%{opacity:0}}@keyframes orfFc{0%{opacity:0}75%{opacity:1}100%{opacity:1}}@keyframes orfBob{0%{transform:translateY(0)}50%{transform:translateY(-1px)}100%{transform:translateY(-1px)}}.d1{opacity:1;animation:orfD1 56s steps(1,end) infinite}.d2,.d3,.d4{opacity:0}.d2{animation:orfD2 56s steps(1,end) infinite}.d3{animation:orfD3 56s steps(1,end) infinite}.d4{animation:orfD4 56s steps(1,end) infinite}.steam{animation:orfSteam 1.2s steps(1,end) infinite}@keyframes orfD1{0%{opacity:1}25%{opacity:0}100%{opacity:0}}@keyframes orfD2{0%{opacity:0}25%{opacity:1}50%{opacity:0}100%{opacity:0}}@keyframes orfD3{0%{opacity:0}50%{opacity:1}75%{opacity:0}100%{opacity:0}}@keyframes orfD4{0%{opacity:0}75%{opacity:1}100%{opacity:1}}@keyframes orfSteam{0%{transform:translateY(0);opacity:.9}50%{transform:translateY(-1px);opacity:.5}100%{opacity:.5}}.tip{grid-area:1/1;opacity:0;animation:orfTip 144s steps(1,end) infinite}@keyframes orfTip{0%{opacity:1}5.556%{opacity:0}100%{opacity:0}}@media (prefers-reduced-motion: reduce){.tip{animation:none}.tip0{opacity:1}.walker,.flip,.fa,.fb,.fc,.bob,.d1,.d2,.d3,.d4,.steam{animation:none}}'

# 🟠 สถานะบนบอร์ด → ช่องบนหน้าเข้าสู่ระบบ
_GROUPS = (
    ('ก่อนผ่าตัด', '#F2A33A', ('holding_pre',)),
    ('กำลังผ่าตัด', '#4C9BFF', ('in_or',)),
    ('พักฟื้น', '#2BB5A3', ('recovery', 'holding_post')),
    ('จำหน่ายแล้ว', '#9AA9B8', ('discharged',)),
)


@st.cache_data(ttl=300, show_spinner=False)
def _today_counts(today: str):
    """นับเคสวันนี้ตามช่วง : คืน (list จำนวน, 'HH:MM') · อ่านไม่ได้ = None (หน้าเข้าสู่ระบบยังขึ้นได้)"""
    try:
        from main_or_db import load_board_state
        s = load_board_state(today)
        p = json.loads(s) if s else {}
        cases = p.get('cases', []) if p.get('date') == today else []
        n = [sum(1 for c in cases if c.get('status') in keys) for _, _, keys in _GROUPS]
        return n, datetime.now(_BKK).strftime('%H:%M')
    except Exception:
        return None


def render_left_panel() -> None:
    today = datetime.now(_BKK).date().isoformat()
    got = _today_counts(today)
    n, upd = got if got else ([None] * 4, None)
    cells = ''.join(
        '<div class="orl-cell"><div class="orl-cl"><span style="background:%s"></span>%s</div>'
        '<div class="orl-num">%s</div></div>' % (col, lab, '-' if v is None else v)
        for (lab, col, _), v in zip(_GROUPS, n))
    tips = ''.join(
        '<div class="tip tip%d" style="animation-delay:%ds">%s</div>' % (i, i * 8, t)
        for i, t in enumerate(_TIPS))
    upd_txt = ('อัปเดต %s : ทุก 5 นาที' % upd) if upd else 'ยังอ่านข้อมูลวันนี้ไม่ได้'
    html = (
        '<style>' + _CSS + '</style>'
        '<div class="orl-panel">'
        '<div class="orl-brand"><div class="orl-logo"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="12" cy="12" r="8.5"></circle><path d="M12 7.5V12l3 2"></path></svg></div>OR Flow</div>'
        '<div class="orl-h1">เห็นทุกห้องผ่าตัด<br>ในจอเดียว</div>'
        '<div class="orl-sub">ติดตามสถานะผู้ป่วยตั้งแต่รับเข้าจนจำหน่าย</div>'
        '<section class="orl-box" aria-label="จำนวนผู้ป่วยวันนี้แยกตามช่วง">'
        '<div class="orl-boxh"><b>วันนี้ในห้องผ่าตัด</b><span>' + upd_txt + '</span></div>'
        '<div class="orl-grid">' + cells + '</div>'
        '<div class="orl-stage"><div class="orl-bubble"><div class="orl-tips">' + tips + '</div><div class="orl-tail"></div></div>'
        '<div class="orl-floor"></div>'
        '<div class="walker" aria-hidden="true"><div class="flip">' + _SPRITE + '</div></div></div>'
        '</section>'
        '<div class="orl-foot">ส่วนหนึ่งของวิทยานิพนธ์ หลักสูตรพยาบาลศาสตรมหาบัณฑิต สาขาการบริหารการพยาบาล</div>'
        '</div>')
    st.markdown(html, unsafe_allow_html=True)


_TH_DAY = ('จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์')
_TH_MON = ('มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม',
           'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม')
_SUN = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0B7A6C" stroke-width="1.8" '
        'stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2.5v2M12 19.5v2'
        'M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"></path></svg>')
_MOON = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0B7A6C" stroke-width="1.8" '
         'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
         '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"></path></svg>')
# 🟢 ฟอร์มขวาแบบ C (มุกกี้เลือก 22 พ.ย. 2026) : แต่งช่อง/ปุ่ม/การ์ดของ st.form ด้วย CSS · ใช้เฉพาะหน้านี้
_FORM_CSS = (
    '[data-testid="stForm"]{background:#FFFFFF;border:1px solid #DCE5E2;border-radius:20px;padding:28px 28px 22px}'
    '[data-testid="stForm"] [data-testid="stWidgetLabel"] p{font-size:15px;font-weight:500;color:#12212E}'
    '[data-testid="stForm"] [data-baseweb="input"]{height:52px;border:1.5px solid #C6D3CF;border-radius:12px;background:#FFFFFF}'
    '[data-testid="stForm"] [data-baseweb="input"]:focus-within{border-color:#0B7A6C;box-shadow:0 0 0 4px rgba(11,122,108,.18)}'
    '[data-testid="stForm"] [data-baseweb="input"] input{font-size:17px;background:#FFFFFF;padding-left:14px}'
    '[data-testid="stForm"] [data-baseweb="input"] input::placeholder{color:#6B7A88}'
    '[data-testid="stFormSubmitButton"] button{height:52px;border:none;border-radius:12px;background:#0B7A6C;color:#FFFFFF}'
    '[data-testid="stFormSubmitButton"] button:hover{background:#09685C;color:#FFFFFF}'
    '[data-testid="stFormSubmitButton"] button p{font-size:17px;font-weight:600}'
    '.orl-g{display:flex;flex-direction:column;gap:8px;margin:0 0 20px}'
    '.orl-gd{display:flex;align-items:center;gap:10px;font-size:15px;color:#3E4C59}'
    '.orl-gi{width:40px;height:40px;border-radius:20px;background:rgba(11,122,108,.12);display:flex;align-items:center;justify-content:center}'
    '.orl-gt{font-size:40px;font-weight:700;line-height:1.3;color:#12212E}'
    '.orl-gs{font-size:17px;color:#3E4C59}'
)


def _greeting(now: datetime):
    """ทักทายตามเวร : ห้องผ่าตัดมีแค่เวรเช้ากับเวร On Call (มุกกี้แจ้ง 22 พ.ย. 2026)"""
    h = now.hour
    if 6 <= h < 12:
        return _SUN, 'สวัสดีเวรเช้า', 'ขอให้วันนี้ผ่าตัดราบรื่นทุกห้อง'
    if 12 <= h < 16:
        return _SUN, 'สวัสดีเวรเช้า', 'อีกนิดเดียว เคสบ่ายก็จะเสร็จแล้ว'
    if 16 <= h < 19:
        return _SUN, 'สวัสดีเวร On Call', 'ขอบคุณที่อยู่ดูแลผู้ป่วยต่อนะ'
    return _MOON, 'สวัสดีเวร On Call', 'เวร On Call นี้ขอให้เรียบร้อยและปลอดภัย'


def render_form_head() -> None:
    now = datetime.now(_BKK)
    icon, title, sub = _greeting(now)
    date_txt = 'วัน%s ที่ %d %s %d' % (_TH_DAY[now.weekday()], now.day, _TH_MON[now.month - 1], now.year + 543)
    date_txt = date_txt.replace(' ที่ ', 'ที่ ')
    st.markdown(
        '<style>' + _FORM_CSS + '</style>'
        '<div class="orl-g"><div class="orl-gd"><div class="orl-gi">' + icon + '</div>' + date_txt + '</div>'
        '<div class="orl-gt">' + title + '</div><div class="orl-gs">' + sub + '</div></div>',
        unsafe_allow_html=True)
