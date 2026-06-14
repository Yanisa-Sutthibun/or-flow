# -*- coding: utf-8 -*-
"""patch_board_names.py — ซ่อมชื่อผู้ป่วยบนบอร์ดวันนี้ ที่ถูก mask แบบเก่าจนชื่อหาย
(เคสมียศ เช่น 'ร.ต.อ. ม.' → 'ร.ต.อ. มานพ ส.') โดยดึงชื่อเต็มจากไฟล์ตารางผ่าตัด
ที่อัปโหลดเช้านี้ จับคู่เคสด้วย HN 4 ตัวท้าย — ไม่แตะสถานะ/เวลา/ค่าทำนายใดๆ

วิธีใช้:
    1. ปิดแอป Streamlit ก่อน (Ctrl+C)   ← สำคัญ กัน session เก่าเซฟทับ
    2. python patch_board_names.py "C:\\path\\to\\ตารางผ่าตัดวันนี้.csv"
    3. เปิดแอปใหม่ — บอร์ดจะแสดงชื่อรูปแบบใหม่

หมายเหตุ: mask logic ด้านล่างคัดลอกจาก main_or_db.py (เวอร์ชัน 11 มิ.ย. 2026)
ให้ standalone — ถ้าแก้ใน main_or_db ให้มาอัปเดตที่นี่ด้วย (ใช้ครั้งเดียวแล้วลบทิ้งได้)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SNAPSHOT = ROOT / 'data' / '_board_snapshot.json'

# ---- mask logic (ชุดเดียวกับ main_or_db.py ใหม่) ----
_PT_TITLES = (('นางสาว', 'น.ส.'), ('เด็กชาย', 'ด.ช.'), ('เด็กหญิง', 'ด.ญ.'),
              ('นาง', 'นาง'), ('นาย', 'นาย'), ('น.ส.', 'น.ส.'),
              ('ด.ช.', 'ด.ช.'), ('ด.ญ.', 'ด.ญ.'))
_RANK_STEMS = ('ร้อย', 'พัน', 'พล', 'สิบ', 'จ่าสิบ', 'เรือ', 'นาวา',
               'เรืออากาศ', 'นาวาอากาศ', 'จ่าอากาศ', 'พันจ่า', 'พันจ่าอากาศ',
               'ร้อยตำรวจ', 'พันตำรวจ', 'พลตำรวจ', 'สิบตำรวจ', 'จ่าสิบตำรวจ')
_PT_TITLE_WORDS = frozenset(
    {s + g for s in _RANK_STEMS for g in ('ตรี', 'โท', 'เอก')} | {
        'นาย', 'นาง', 'นางสาว', 'เด็กชาย', 'เด็กหญิง',
        'คุณ', 'คุณหญิง', 'ท่านผู้หญิง', 'หม่อม', 'หม่อมหลวง', 'หม่อมราชวงศ์',
        'พระ', 'พระครู', 'สามเณร', 'แม่ชี',
        'ดาบตำรวจ', 'จ่านายสิบ', 'พลทหาร', 'อาสาสมัครทหารพราน',
        'นายแพทย์', 'แพทย์หญิง', 'ทันตแพทย์', 'เภสัชกร', 'เภสัชกรหญิง',
        'ศาสตราจารย์', 'รองศาสตราจารย์', 'ผู้ช่วยศาสตราจารย์',
    })
_PT_TITLE_SHORT = {'นางสาว': 'น.ส.', 'เด็กชาย': 'ด.ช.', 'เด็กหญิง': 'ด.ญ.',
                   'นายแพทย์': 'นพ.', 'แพทย์หญิง': 'พญ.', 'ทันตแพทย์': 'ทพ.'}
_TH_TRAILING = 'ะัาำิีึืุู็่้๊๋์'


def _is_title_token(tok):
    return tok.endswith('.') or tok in _PT_TITLE_WORDS or tok.startswith('ว่าที่')


def mask_patient_name(name):
    if not name or not isinstance(name, str):
        return name or '-'
    parts = ' '.join(name.split()).split()
    title_parts = []
    while len(parts) >= 2 and len(title_parts) < 3 and _is_title_token(parts[0]):
        tok = parts.pop(0)
        title_parts.append(_PT_TITLE_SHORT.get(tok, tok))
    if not title_parts and parts:
        tok = parts[0]
        for full, short in _PT_TITLES:
            if (tok.startswith(full) and len(tok) > len(full)
                    and tok[len(full)] not in _TH_TRAILING):
                title_parts.append(short)
                parts[0] = tok[len(full):]
                break
    if not parts:
        return ' '.join(title_parts) or '-'
    core = f"{parts[0]} {parts[-1][:1]}." if len(parts) >= 2 else parts[0]
    return ' '.join(title_parts + [core]).strip()


def _hn4(hn):
    s = re.sub(r'\D', '', str(hn or ''))
    return s[-4:] if len(s) >= 4 else s


def load_schedule_names(path):
    """อ่านไฟล์ตารางผ่าตัด (CSV) → {hn 4 ตัวท้าย: ชื่อ mask รูปแบบใหม่}"""
    import pandas as pd
    last_err = None
    for enc in ('utf-8-sig', 'cp874', 'utf-8'):
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc)
            break
        except Exception as e:
            last_err = e
    else:
        sys.exit(f'อ่านไฟล์ไม่ได้: {last_err}')
    cols = {str(c).strip().lower(): c for c in df.columns}
    hn_col = next((cols[k] for k in cols if k == 'hn' or k.startswith('hn')), None)
    nm_col = next((cols[k] for k in ('dspname', 'name', 'ชื่อ', 'ชื่อ-สกุล',
                                     'ชื่อผู้ป่วย') if k in cols), None)
    if not hn_col or not nm_col:
        sys.exit(f'หาคอลัมน์ HN/ชื่อ ไม่เจอ — คอลัมน์ที่มี: {list(df.columns)}')
    mapping = {}
    for _, r in df.iterrows():
        k = _hn4(r.get(hn_col))
        nm = str(r.get(nm_col) or '').strip()
        if k and nm and nm.lower() != 'nan':
            mapping[k] = mask_patient_name(nm)
    return mapping


def main():
    if len(sys.argv) < 2:
        sys.exit('วิธีใช้: python patch_board_names.py <ไฟล์ตารางผ่าตัดวันนี้.csv>')
    mapping = load_schedule_names(sys.argv[1])
    print(f'อ่านชื่อจากไฟล์ตาราง: {len(mapping)} เคส')

    if not SNAPSHOT.exists():
        sys.exit('ไม่พบ data/_board_snapshot.json — เปิดบอร์ดอย่างน้อย 1 ครั้งก่อน')
    payload = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    fixed = 0
    for c in payload.get('cases', []):
        k = _hn4(c.get('hn'))
        new_name = mapping.get(k)
        if new_name and c.get('name') != new_name:
            print(f"  HN …{k}: '{c.get('name')}' → '{new_name}'")
            c['name'] = new_name
            fixed += 1
    if not fixed:
        print('ไม่มีเคสที่ต้องซ่อม (ชื่อตรงรูปแบบใหม่หมดแล้ว)')
        return
    payload['pii_kept'] = False
    out = json.dumps(payload, ensure_ascii=False, default=str)
    SNAPSHOT.write_text(out, encoding='utf-8')
    print(f'✅ ซ่อมไฟล์ local แล้ว {fixed} เคส')

    # อัปเดต DB กลาง (บอร์ดกลาง) ให้ตรงกัน — เครื่องอื่นเห็นชื่อใหม่ด้วย
    sec = (ROOT / '.streamlit' / 'secrets.toml').read_text(encoding='utf-8')
    url = re.search(r'^database_url\s*=\s*"([^"]*)"', sec, re.M)
    schema = re.search(r'^db_schema\s*=\s*"([^"]*)"', sec, re.M)
    mode = re.search(r'^db_mode\s*=\s*"([^"]*)"', sec, re.M)
    if not (mode and mode.group(1) == 'supabase' and url and url.group(1)):
        print('db_mode ไม่ใช่ supabase — จบแค่ไฟล์ local')
        return
    sch = schema.group(1) if schema else 'public'
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', sch):
        sys.exit(f'db_schema ไม่ปลอดภัย: {sch!r}')
    import psycopg2
    conn = psycopg2.connect(url.group(1), connect_timeout=15)
    try:
        cur = conn.cursor()
        cur.execute(f'SET search_path TO "{sch}", public')
        key = f"board_state_{payload.get('date')}"
        cur.execute(
            "UPDATE app_settings SET value = %s, updated_at = NOW() WHERE key = %s",
            (out, key))
        if cur.rowcount == 0:
            cur.execute("INSERT INTO app_settings (key, value) VALUES (%s, %s)",
                        (key, out))
        conn.commit()
        print(f'✅ อัปเดตบอร์ดกลางบน Supabase แล้ว ({key})')
    finally:
        conn.close()
    print('เสร็จ — เปิดแอปใหม่ได้เลย ชื่อจะขึ้นรูปแบบ ยศ + ชื่อเต็ม + นามสกุลย่อ')


if __name__ == '__main__':
    main()
