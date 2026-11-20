# -*- coding: utf-8 -*-
"""
his_csv.py : 📄 ตัวอ่านไฟล์ CSV ที่ export จาก HIS แบบทนทาน (ใช้ร่วมกันทุกจุดที่นำเข้าสถิติ)
════════════════════════════════════════════════════════════════════════════
สร้าง 20 พ.ย. 2026 (มุกกี้สั่ง: เช็กเรื่อง comma กับการเว้นบรรทัดของไฟล์ปี 69)

ปัญหาที่เจอจริงในไฟล์ชุด "อาคารBปี69" และวิธีที่ไฟล์นี้จัดการ
  1. comma ในช่องข้อความ (หัตถการ วินิจฉัย หมายเหตุ ชื่อพยาบาลหลายคน)
     → อ่านด้วย csv.reader ตรง ๆ ครั้งเดียว ห้าม join แล้ว parse ซ้ำ (เครื่องหมายคำพูดหาย คอลัมน์เลื่อน)
  2. ขึ้นบรรทัดใหม่กลางช่องโดยไม่มีเครื่องหมายคำพูดครอบ (ช่อง t_surgstf ของ intraop
     มีแพทย์หลายคน คนละบรรทัด) ทำให้ 1 เคสแตกเป็น 2-4 บรรทัด
     → ต่อกลับจนครบจำนวนคอลัมน์ของหัวตาราง ต่อไม่ลงให้นับเป็นแถวเสีย ไม่เดา
  3. รูปแบบวันที่ไม่คงที่ : ไฟล์ชุดเก่าเป็น วัน/เดือน/ปี แต่ชุดปี 69 เป็น เดือน/วัน/ปี
     → ตรวจจากข้อมูลทั้งคอลัมน์ (ตัวเลขที่เกิน 12 ต้องเป็นวัน) กำกวมให้หยุด ไม่เดา
  4. ไฟล์ชุดเก่าบางไฟล์ครอบเครื่องหมายคำพูดทั้งบรรทัด → แกะชั้นนอกออกก่อน

⛔ ไฟล์นี้ logic ล้วน ห้าม import streamlit และห้ามพิมพ์เนื้อหาแถว (มี HN และชื่อผู้ป่วย)
"""
from __future__ import annotations

import csv
import io
import re
from typing import Optional

_DATE_RE = re.compile(r'^\s*(\d{1,2})/(\d{1,2})/(\d{4})')


def read_text(src) -> str:
    """อ่านไฟล์ (path หรือ buffer ที่อัปโหลด) → ข้อความ · ลอง UTF-16 ก่อน (ค่าเริ่มของ HIS)"""
    if hasattr(src, 'read'):
        data = src.getvalue() if hasattr(src, 'getvalue') else src.read()
    else:
        with open(src, 'rb') as f:
            data = f.read()
    if isinstance(data, str):
        return data
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return data.decode('utf-16')
    for enc in ('utf-8-sig', 'utf-16', 'cp874'):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError("อ่านไฟล์ไม่ได้ : ไม่ใช่ UTF-16 / UTF-8 / cp874")


def read_table(src):
    """คืน (header, rows, info) · rows ทุกแถวยาวเท่า header เสมอ
    info = {'rejoined': จำนวนเคสที่ต่อบรรทัดกลับ, 'bad': จำนวนแถวที่ต่อไม่ลง (ถูกทิ้ง),
            'wrapped': ไฟล์ครอบคำพูดทั้งบรรทัดหรือไม่, 'blank': บรรทัดว่าง}"""
    raw = list(csv.reader(io.StringIO(read_text(src), newline='')))
    raw = [r for r in raw if r]                       # csv.reader คืน [] เมื่อบรรทัดว่างสนิท
    if not raw:
        return [], [], {'rejoined': 0, 'bad': 0, 'wrapped': False, 'blank': 0}
    wrapped = len(raw[0]) == 1 and ',' in raw[0][0]
    if wrapped:
        # ชุดเก่า : ทั้งบรรทัดเป็นช่องเดียว ข้างในคือ CSV ที่ครอบคำพูดถูกต้อง
        raw = [next(csv.reader([r[0]])) if len(r) == 1 else r for r in raw]
    header = [h.strip() for h in raw[0]]
    n = len(header)
    rows, rejoined, bad, blank = [], 0, 0, 0
    buf = None
    for r in raw[1:]:
        if buf is None:
            if len(r) == n:
                rows.append(r)
            elif len(r) == 1 and not r[0].strip():
                blank += 1
            elif len(r) < n:
                buf = list(r)                         # เริ่มเคสที่แตกบรรทัด
            else:
                bad += 1                              # ยาวเกินหัวตาราง = คอลัมน์เลื่อน ไม่เดา
            continue
        # กำลังต่อ : ช่องสุดท้ายของท่อนก่อน + ช่องแรกของท่อนนี้ คือช่องเดียวกันที่ถูกตัด
        merged = buf[:-1] + [buf[-1].rstrip() + '\n' + r[0].lstrip()] + list(r[1:])
        if len(merged) == n:
            rows.append(merged)
            rejoined += 1
            buf = None
        elif len(merged) < n:
            buf = merged
        else:
            bad += 1                                  # ต่อแล้วเกิน = ท่อนก่อนเสียจริง
            buf = None
            if len(r) == n:
                rows.append(r)
    if buf is not None:
        bad += 1
    return header, rows, {'rejoined': rejoined, 'bad': bad,
                          'wrapped': wrapped, 'blank': blank}


def col(header, name, nth=0) -> int:
    """ตำแหน่งคอลัมน์ตามชื่อ · หัวตาราง HIS มีชื่อซ้ำ (name, an, dspname, arrivdate)
    nth=0 คือตัวแรก · ไม่พบคืน -1"""
    hits = [i for i, h in enumerate(header) if h.lower() == name.lower()]
    return hits[nth] if len(hits) > nth else -1


def detect_date_order(values) -> str:
    """'DMY' (วัน/เดือน/ปี) หรือ 'MDY' (เดือน/วัน/ปี) จากข้อมูลทั้งคอลัมน์
    กำกวม (ไม่มีค่าไหนเกิน 12 ทั้งสองตำแหน่ง) หรือขัดกันเอง → ValueError"""
    a_max = b_max = 0
    for v in values:
        m = _DATE_RE.match(str(v or ''))
        if m:
            a_max = max(a_max, int(m.group(1)))
            b_max = max(b_max, int(m.group(2)))
    if a_max > 12 and b_max > 12:
        raise ValueError("รูปแบบวันที่ในไฟล์ขัดกันเอง (มีทั้ง วัน/เดือน และ เดือน/วัน)")
    if a_max > 12:
        return 'DMY'
    if b_max > 12:
        return 'MDY'
    raise ValueError("ดูไม่ออกว่าวันที่ในไฟล์เป็น วัน/เดือน/ปี หรือ เดือน/วัน/ปี "
                     "(ไม่มีวันที่เกินวันที่ 12) : ไฟล์ต้องมีข้อมูลหลายวัน")


def to_iso(v, order: str) -> Optional[str]:
    """'11/20/2026 00:00:00' + 'MDY' → '2026-11-20' · ปี พ.ศ. แปลงเป็น ค.ศ. · อ่านไม่ออกคืน None"""
    m = _DATE_RE.match(str(v or ''))
    if not m:
        s = str(v or '').strip()
        return s[:10] if re.match(r'^\d{4}-\d{2}-\d{2}', s) else None
    a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    d, mo = (a, b) if order == 'DMY' else (b, a)
    if y > 2400:
        y -= 543
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def to_dmy(v, order: str) -> str:
    """แปลงเป็น 'วัน/เดือน/ปี' ที่โค้ดเดิมของระบบคาดหวัง (classify_case ใช้ dayfirst)"""
    iso = to_iso(v, order)
    if not iso:
        return ''
    return f"{int(iso[8:10])}/{int(iso[5:7])}/{iso[:4]}"


def write_table(path, header, rows) -> None:
    """เขียนกลับเป็น CSV UTF-16 ครอบเครื่องหมายคำพูดถูกต้อง (ช่องที่มี comma หรือขึ้นบรรทัดใหม่ไม่แตกอีก)"""
    with open(path, 'w', encoding='utf-16', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator='\r\n')
        w.writerow(header)
        w.writerows(rows)
