# -*- coding: utf-8 -*-
"""
update_stats_from_his.py : 📈 เติมสถิติย้อนหลังของระบบจริงจากไฟล์ HIS (ตารางผ่าตัด + intraop)
════════════════════════════════════════════════════════════════════════════
สร้าง 20 พ.ย. 2026 (มุกกี้สั่ง: เพิ่มสถิติของ production ให้เป็นปัจจุบัน)

เพิ่ม 1 แถวต่อ 1 เคสที่ผ่าตัดจริง (ยึดไฟล์ intraop เป็นหลัก ดึงหัตถการ วินิจฉัย อายุ จากตารางผ่าตัด)
โครงเดียวกับ main_or_db.import_history_6467 ที่ใช้เติมสถิติปี 64-67 แล้วแปลงชื่อเป็นรหัสด้วย
mask_unmasked_staff · ไม่ใช้ท่อปุ่ม ③ (process_panel) เพราะท่อนั้นจับคู่ด้วย วันที่+ห้อง+หัตถการ+แพทย์
หัตถการเดียวกันของแพทย์คนเดียวกันในห้องเดียวกันวันเดียวกันจะถูกยุบเหลือแถวเดียว (ไฟล์ปี 69 หาย 205 แถว)

กติกาความปลอดภัย
  1. ไม่ใส่ --apply = DRY-RUN อ่านอย่างเดียว ไม่เขียนฐานข้อมูลแม้แต่แถวเดียว
  2. วันที่ที่มีเคสในฐานข้อมูลอยู่แล้ว "ข้ามทั้งวัน" ไม่แตะของเดิม (กันเคสซ้ำ บทเรียน 19 ก.ค. 2026)
  3. วันสุดท้ายในไฟล์ = วันที่ export ข้อมูลยังไม่ครบวัน → ไม่นำเข้า (แก้ได้ด้วย --until)
  4. HN ชื่อผู้ป่วย และ procnote ไม่ขึ้นฐานข้อมูล · ชื่อแพทย์และพยาบาลถูกแปลงเป็นรหัส
     ท้ายขั้นตอนเสมอ แม้ขั้นกลางล้ม
  5. ETHICS LOCK : สคริปต์นี้เติมเฉพาะฐานสถิติ ไม่เทรนและไม่แตะแบบจำลอง

ใช้ (จากโฟลเดอร์ main_OR_app ต้องมี .streamlit\\secrets.toml ตัวจริง):
    python update_stats_from_his.py <ตารางผ่าตัด.csv> <intraop.csv>            # DRY-RUN
    python update_stats_from_his.py <ตารางผ่าตัด.csv> <intraop.csv> --apply    # เขียนจริง
    ตัวเลือก : --from YYYY-MM-DD   --until YYYY-MM-DD
"""
from __future__ import annotations

import collections
import os
import sys
from datetime import date, timedelta

os.chdir(os.path.dirname(os.path.abspath(__file__)))

_TH_MON = ['', 'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
           'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']


def _opt(name):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1].strip()
    return None


def _th(iso):
    return f"{int(iso[8:10])} {_TH_MON[int(iso[5:7])]} {int(iso[:4]) + 543}"


def _month_table(title, counter):
    print(title)
    if not counter:
        print("    (ไม่มีข้อมูล)")
        return
    for ym in sorted(counter):
        print(f"    {_TH_MON[int(ym[5:7])]:>5} {int(ym[:4]) + 543} : {counter[ym]:>5} เคส")


def _read_intraop(path):
    """intraop เป็น .csv (ชุดปี 69 ใหม่) หรือ .xls/.xlsx (ชุดปี 68 และ 69 ชุดเก่า) → (header, rows, info)
    📄 21 พ.ย. 2026 (มุกกี้สั่งเติมสถิติปี 64-69): ไฟล์ .xls อ่านด้วย pandas วันที่ออกมาเป็น ISO อยู่แล้ว
    ชื่อคอลัมน์ซ้ำที่ pandas เติม .1 ถูกถอดกลับเป็นชื่อเดิม ให้หาตำแหน่งด้วย his_csv.col ได้เหมือน csv"""
    import his_csv as HC
    if str(path).lower().endswith('.csv'):
        return HC.read_table(path)
    import re as _re
    if str(path).lower().endswith('.xlsx'):
        import pandas as pd
        xl = pd.read_excel(path, engine='openpyxl', dtype=str).fillna('')
        header = [_re.sub(r'\.\d+$', '', str(c)).strip() for c in xl.columns]
        rows = [[str(v) for v in row] for row in xl.values.tolist()]
    else:
        # .xls : อ่านด้วย xlrd ตรง ๆ ไม่ผ่าน pandas (pandas บังคับ xlrd 2.0.1 ขึ้นไป
        # แต่เครื่องที่รันจริงมี xlrd 1.2.0 · เขียนแบบนี้ใช้ได้ทั้งสองรุ่น)
        import xlrd
        book = xlrd.open_workbook(path, logfile=open(os.devnull, 'w'))
        sh = book.sheet_by_index(0)

        def _cell(c):
            if c.ctype == xlrd.XL_CELL_DATE:
                return xlrd.xldate_as_datetime(c.value, book.datemode).strftime('%Y-%m-%d %H:%M:%S')
            if c.ctype == xlrd.XL_CELL_NUMBER:
                return str(int(c.value)) if float(c.value).is_integer() else str(c.value)
            if c.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                return ''
            return str(c.value)
        header = [str(v).strip() for v in sh.row_values(0)]
        rows = [[_cell(c) for c in sh.row(i)] for i in range(1, sh.nrows)]
    return header, rows, {'rejoined': 0, 'bad': 0, 'wrapped': False, 'blank': 0}


def _date_order(values):
    """'DMY' / 'MDY' จาก his_csv · ถ้าทั้งคอลัมน์เป็น ISO (ไฟล์ .xls) คืน 'ISO' (to_iso รับ ISO ได้เอง)"""
    import his_csv as HC
    import re as _re
    vals = [str(v or '') for v in values]
    if not any(_re.match(r'^\s*\d{1,2}/\d{1,2}/\d{4}', v) for v in vals):
        if any(_re.match(r'^\d{4}-\d{2}-\d{2}', v.strip()) for v in vals):
            return 'ISO'
    return HC.detect_date_order(vals)


def load_files(sched_path, intra_path):
    """อ่าน 2 ไฟล์ผ่าน his_csv → dict ของแถว + วันที่ ISO + รายงานคุณภาพไฟล์ (ไม่พิมพ์เนื้อหาแถว)"""
    import his_csv as HC
    sh, srows, sinfo = HC.read_table(sched_path)
    ih, irows, iinfo = _read_intraop(intra_path)
    s_op = HC.col(sh, 'opedate')
    i_op = HC.col(ih, 'opedate')
    if s_op < 0 or i_op < 0 or HC.col(ih, 'roomtimein') < 0 or HC.col(sh, 'icd9cm_name') < 0:
        sys.exit("⛔ ไฟล์ไม่ใช่รูปแบบที่คาดไว้ : เช็กว่าใส่ ตารางผ่าตัด ก่อน แล้วตามด้วย intraop")
    s_order = _date_order(r[s_op] for r in srows)
    i_order = _date_order(r[i_op] for r in irows)
    s_iso = [HC.to_iso(r[s_op], s_order) for r in srows]
    i_iso = [HC.to_iso(r[i_op], i_order) for r in irows]
    return dict(sh=sh, srows=srows, sinfo=sinfo, s_order=s_order, s_iso=s_iso,
                ih=ih, irows=irows, iinfo=iinfo, i_order=i_order, i_iso=i_iso)


def _hhmm(v):
    """'91800' → (9, 18) · อ่านไม่ออกคืน None"""
    t = str(v or '').strip().split('.')[0]
    if not t.isdigit():
        return None
    t = t.zfill(6)
    h, m = int(t[:2]), int(t[2:4])
    return (h, m) if (h <= 23 and m <= 59) else None


def _ts(iso, v):
    hm = _hhmm(v)
    return f"{iso} {hm[0]:02d}:{hm[1]:02d}:00" if (iso and hm) else None


def _clean(v):
    t = str(v or '').strip()
    return '' if t.upper() in ('NAN', 'NONE', '-') else t


def insert_cases(F, tset):
    """เพิ่มเคสของวันเป้าหมายลงตาราง cases · คืน (เพิ่ม, ซ้ำ, ไม่มีแถวตารางผ่าตัด, เวลาครองห้องใช้ไม่ได้)
    โครงเดียวกับ main_or_db.import_history_6467 : กันซ้ำด้วย (วันที่, ห้อง, หัตถการ, เวลาเข้าห้อง)
    ซึ่งตรงกับ unique index ของตาราง · HN ใช้จับคู่ 2 ไฟล์ในหน่วยความจำเท่านั้น ไม่ลงฐานข้อมูล"""
    import his_csv as HC
    from datetime import datetime as _dt
    from main_or_db import get_conn, classify_case, _predict_for_case
    sh, ih = F['sh'], F['ih']
    S = {k: HC.col(sh, k) for k in ('hn', 'reqdate', 'division', 'orroom', 'estmtime', 'an',
                                    'optype_var', 'opetime', 'age', 'icd9cm_name',
                                    'icd10_name', 'surgstfnm', 'procnote')}
    I = {k: HC.col(ih, k) for k in ('roomdatein', 'roomtimein', 'roomdateout', 'roomtimeout',
                                    'hn', 'an', 'division', 'orroom', 'icd9cmnm', 'dctnm',
                                    'nursurgnm', 'nurcircunm', 'arrivdate', 'arrivtime')}

    def g(row, ix):
        return row[ix].strip() if ix >= 0 else ''

    # ตารางผ่าตัดของวันเป้าหมาย จัดกลุ่มตาม (hn, วัน) · คนเดียวผ่า 2 ครั้งในวันเดียวมีได้
    sched = collections.defaultdict(list)
    for r, d in zip(F['srows'], F['s_iso']):
        if d in tset:
            sched[(g(r, S['hn']), d)].append(r)

    model_label = 'v?'
    try:
        import json
        with open(os.path.join('models', 'model_registry.json'), encoding='utf-8') as f:
            model_label = f"v{json.load(f).get('active_version', 1)}"
    except Exception:
        pass

    conn = get_conn()
    # คอลัมน์ที่ฐาน SQLite รุ่นเก่ายังไม่มี (Supabase มีครบแล้ว) : เติมแบบเดียวกับ import_history_6467
    from main_or_db import _table_columns
    _cols = _table_columns(conn)
    for _c, _t in (('age', 'REAL'), ('ai_model_ver', 'TEXT')):
        if _c not in _cols:
            conn.execute(f"ALTER TABLE cases ADD COLUMN {_c} {_t}")
    n_ins = n_dup = n_nosched = n_baddur = n_notime = 0
    # เรียงตามวัน แล้ว commit ทีละวัน : วันหนึ่งเข้าครบทั้งวันหรือไม่เข้าเลย
    # (กติกาข้ามวันที่มีข้อมูลแล้ว จะพังถ้าปล่อยให้วันไหนเข้าครึ่งเดียว) ล้มกลางทางรันซ้ำได้
    todo = sorted(((r, d) for r, d in zip(F['irows'], F['i_iso']) if d in tset),
                  key=lambda x: x[1])
    _day = None
    try:
        for k, (r, op_date) in enumerate(todo, 1):
            if op_date != _day:
                if _day is not None:
                    conn.commit()
                _day = op_date
            room_s = g(r, I['orroom'])
            room = int(room_s) if room_s.isdigit() else None
            # จับคู่แถวตารางผ่าตัด : ห้องตรงกันก่อน ไม่งั้นแถวแรกที่เหลือ
            cand = sched.get((g(r, I['hn']), op_date)) or []
            s = next((x for x in cand if g(x, S['orroom']) == room_s), cand[0] if cand else None)
            if s is not None:
                cand.remove(s)
            else:
                n_nosched += 1
            # 🔁 23 พ.ย. 2026 (มุกกี้เลือกทางเลือก 1): หัตถการในสถิติใช้ชื่อที่ลงรหัสหลังผ่าตัดใน intraop
            #    (icd9cmnm) ก่อน ถ้าไม่มีจึงใช้ชื่อจากตารางผ่าตัด · เดิมใช้ชื่อจากตารางก่อนเสมอ
            #    = นับ "ที่วางแผน" ไม่ใช่ "ที่ทำจริง" · HIS ลง icd9cmnm ราว 30% ของเคส ที่เหลือยังเป็นชื่อตามแผน
            #    สถิตินี้ใช้ดูเร็ว ๆ : หัตถการจริงทุกเคสต้องนับจากสมุดสถิติ
            #    proc_plan = ชื่อตามแผน ยังใช้กับการทำนายย้อนหลังและการจัดเคสนอกเวลา
            #    (AI ต้องเห็นเท่าที่รู้ก่อนผ่า และคำว่า "นอกเวลา" อยู่ในชื่อจากตาราง)
            proc_plan = (_clean(g(s, S['icd9cm_name'])) if s is not None else '') \
                or _clean(g(r, I['icd9cmnm'])) or 'UNKNOWN'
            proc = _clean(g(r, I['icd9cmnm'])) or proc_plan
            diag = _clean(g(s, S['icd10_name'])) if s is not None else ''
            sched_surg = _clean(g(s, S['surgstfnm'])) if s is not None else ''
            surg = _clean(g(r, I['dctnm'])) or sched_surg
            div = g(r, I['division']) or (g(s, S['division']) if s is not None else '')
            est = g(s, S['estmtime']) if s is not None else ''
            optype = (g(s, S['optype_var']).lower() if s is not None else '') or 'elective'
            an_v = g(r, I['an']) or (g(s, S['an']) if s is not None else '')
            note = g(s, S['procnote']) if s is not None else ''
            try:
                age_v = float(g(s, S['age'])) if s is not None else None
                if age_v is not None and not (0 < age_v < 120):
                    age_v = None
            except ValueError:
                age_v = None

            in_iso = HC.to_iso(g(r, I['roomdatein']), F['i_order']) or op_date
            out_iso = HC.to_iso(g(r, I['roomdateout']), F['i_order']) or op_date
            in_ts = _ts(in_iso, g(r, I['roomtimein']))
            out_ts = _ts(out_iso, g(r, I['roomtimeout']))
            arr_ts = _ts(HC.to_iso(g(r, I['arrivdate']), F['i_order']) or op_date,
                         g(r, I['arrivtime']))
            if not in_ts or not out_ts:
                # ไม่มีเวลาเข้าหรือออกห้อง = HIS ไม่ได้บันทึกว่าผ่าตัดจริง (เลื่อน ยกเลิก หรือบันทึกไม่ครบ)
                # ไม่นับเป็นเคสผ่าตัดเสร็จ (เกณฑ์เดียวกับ finetune_pipeline._parse_intraop ที่ตัดแถวไม่มีเวลา)
                n_notime += 1
                if s is not None:
                    cand.insert(0, s)                  # คืนแถวตารางผ่าตัดให้เคสอื่นของคนเดียวกันในวันนั้น
                else:
                    n_nosched -= 1
                continue
            dur = wait = None
            try:
                if in_ts and out_ts:
                    dur = int((_dt.fromisoformat(out_ts) - _dt.fromisoformat(in_ts))
                              .total_seconds() // 60)
                    if dur < 0 and in_iso == out_iso:
                        dur += 1440                    # ข้ามเที่ยงคืนแต่ HIS ลงวันออกเป็นวันเดิม
                    if not (5 <= dur <= 1440):         # เกณฑ์เดียวกับ finetune_pipeline._parse_intraop
                        dur = None
                if arr_ts and in_ts:
                    wait = int((_dt.fromisoformat(in_ts) - _dt.fromisoformat(arr_ts))
                               .total_seconds() // 60)
                    if not (0 <= wait <= 720):
                        wait = None
            except ValueError:
                pass
            if dur is None:
                n_baddur += 1

            if conn.execute(
                    "SELECT case_id FROM cases WHERE op_date=? AND COALESCE(room_no,-1)=? "
                    "AND procedure_name=? AND COALESCE(in_or_at,'')=?",
                    (op_date, room if room is not None else -1, proc, in_ts or '')).fetchone():
                n_dup += 1
                continue
            cls = classify_case({
                'an': an_v, 'estimated_time': est, 'procnote': note,
                'requested_date': (HC.to_dmy(g(s, S['reqdate']), F['s_order'])
                                   if s is not None else ''),
                'op_date': op_date, 'procedure_name': proc_plan, 'diagnosis': diag,
                'op_type': optype, 'in_or_at': in_ts})
            ai_min = _predict_for_case(proc_plan, surg or 'UNKNOWN', div or '75', optype, op_date,
                                       age=age_v, orroom=room, diagnosis=diag)
            # 🔒 procnote ใช้จัดประเภทเคสข้างบนเท่านั้น ไม่เก็บลงฐานข้อมูลบนคลาวด์
            conn.execute("""
                INSERT INTO cases (op_date, is_ipd, diagnosis,
                    procedure_name, surgeon_name, scheduled_surgeon,
                    division_code, case_category, patient_type, op_type,
                    estimated_time, status, arrived_at, in_or_at, op_end_at,
                    discharged_at, actual_duration_min, wait_min, scrub_nurse, circ_nurse,
                    room_no, age, ai_predicted_min, ai_model_ver)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (op_date, 1 if _clean(an_v) else 0, diag or None, proc,
                  surg or None, sched_surg or surg or None, div or None,
                  cls.get('case_category'), cls.get('patient_type'), optype,
                  est or None, 'discharged', arr_ts, in_ts, out_ts, out_ts, dur, wait,
                  _clean(g(r, I['nursurgnm'])) or None, _clean(g(r, I['nurcircunm'])) or None,
                  room, age_v, ai_min, model_label))
            n_ins += 1
            if k % 100 == 0 or k == len(todo):
                print(f"    {k}/{len(todo)} เคส", flush=True)
        conn.commit()
    except Exception:
        try:
            conn.rollback()                            # ทิ้งวันที่เข้าไม่ครบ
        except Exception:
            pass
        print(f"    ⛔ หยุดที่วันที่ {_day} : วันนี้ไม่ถูกบันทึก วันก่อนหน้าบันทึกครบแล้ว รันซ้ำได้")
        raise
    finally:
        conn.close()
    return n_ins, n_dup, n_nosched, n_baddur, n_notime


def overview(title="ฐานข้อมูลทั้งหมด แยกปี (ทั้งหมด / ผ่าตัดเสร็จ)"):
    """📊 จำนวนแถวในตาราง cases แยกปี (อ่านอย่างเดียว) · คืน dict {ปี ค.ศ.: (ทั้งหมด, ผ่าตัดเสร็จ)}"""
    from main_or_db import get_conn
    conn = get_conn()
    try:
        rows = [tuple(r) for r in conn.execute(
            "SELECT substr(op_date,1,4), COUNT(*), "
            "SUM(CASE WHEN status='discharged' THEN 1 ELSE 0 END), MIN(op_date), MAX(op_date) "
            "FROM cases GROUP BY substr(op_date,1,4)").fetchall()]
    finally:
        conn.close()
    print(title)
    if not rows:
        print("    (ตาราง cases ว่าง)")
    out = {}
    for y, n, nd, d0, d1 in sorted(rows, key=lambda r: str(r[0])):
        try:
            print(f"    พ.ศ. {int(y) + 543} : {n:>6} / {nd or 0:>6}   ({_th(str(d0))} ถึง {_th(str(d1))})")
        except (TypeError, ValueError):
            print(f"    ปีอ่านไม่ออก ({y!r}) : {n} แถว")
        out[str(y)] = (int(n), int(nd or 0))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    for _o in ('--from', '--until'):
        _v = _opt(_o)
        if _v in args:
            args.remove(_v)
    if len(args) != 2:
        sys.exit("ใช้ : python update_stats_from_his.py <ตารางผ่าตัด.csv> <intraop.csv> [--apply]")
    sched_path, intra_path = args
    apply = '--apply' in sys.argv
    for p in (sched_path, intra_path):
        if not os.path.exists(p):
            sys.exit(f"⛔ ไม่พบไฟล์ : {p}")

    import his_csv as HC
    F = load_files(sched_path, intra_path)
    _ord = {'DMY': 'วัน/เดือน/ปี', 'MDY': 'เดือน/วัน/ปี', 'ISO': 'ปี-เดือน-วัน'}

    from db_connection import IS_POSTGRES, DB_SCHEMA
    print("=" * 66)
    print(f" update_stats_from_his · {'APPLY (เขียนจริง)' if apply else 'DRY-RUN (อ่านอย่างเดียว)'}"
          f" · DB: {'Supabase schema ' + DB_SCHEMA if IS_POSTGRES else 'SQLite local'}")
    print("=" * 66)
    print("① ตรวจไฟล์")
    print(f"    ตารางผ่าตัด : {len(F['srows'])} แถว · วันที่แบบ {_ord[F['s_order']]} · "
          f"ต่อแถวที่แตก {F['sinfo']['rejoined']} · แถวเสีย {F['sinfo']['bad']} · "
          f"ไม่มีวันผ่าตัด {sum(1 for d in F['s_iso'] if not d)}")
    print(f"    intraop     : {len(F['irows'])} เคส · วันที่แบบ {_ord[F['i_order']]} · "
          f"ต่อแถวที่แตก {F['iinfo']['rejoined']} · แถวเสีย {F['iinfo']['bad']}")
    if F['sinfo']['bad'] or F['iinfo']['bad']:
        sys.exit("⛔ มีแถวที่ต่อกลับไม่ลง : หยุดก่อน ไม่นำเข้าไฟล์ที่คอลัมน์อาจเลื่อน")
    i_dates = [d for d in F['i_iso'] if d]
    if not i_dates:
        sys.exit("⛔ ไฟล์ intraop ไม่มีวันผ่าตัดที่อ่านได้")
    f_min, f_max = min(i_dates), max(i_dates)
    print(f"    intraop ครอบ {_th(f_min)} ถึง {_th(f_max)}")

    # ── ช่วงที่จะนำเข้า ──
    d_from = _opt('--from') or f_min
    # วันสุดท้ายในไฟล์ถือว่ายังไม่ครบวัน เฉพาะเมื่อไฟล์จบใกล้วันนี้ (ไฟล์ export สด)
    # ไฟล์ย้อนหลังทั้งปี (เช่นปี 68 จบ 31 ธ.ค.) นำเข้าครบถึงวันสุดท้าย
    _fresh = (date.today() - date.fromisoformat(f_max)).days <= 3
    _last_full = (date.fromisoformat(f_max) - timedelta(days=1)).isoformat() if _fresh else f_max
    d_until = _opt('--until') or _last_full
    if _fresh and not _opt('--until'):
        print(f"    วันสุดท้ายในไฟล์ ({_th(f_max)}) ถือว่ายังไม่ครบวัน : นำเข้าถึง {_th(d_until)}")

    # ── ฐานข้อมูลมีอะไรอยู่แล้ว ──
    from main_or_db import get_conn
    conn = get_conn()
    try:
        db_rows = conn.execute(
            "SELECT op_date, COUNT(*) FROM cases WHERE op_date >= ? AND op_date <= ? "
            "GROUP BY op_date", (f_min, f_max)).fetchall()
        db_last = conn.execute(
            "SELECT MAX(op_date) FROM cases WHERE status = 'discharged'").fetchone()[0]
    finally:
        conn.close()
    db_days = {str(r[0]): int(r[1]) for r in db_rows}
    db_month = collections.Counter()
    for d, n in db_days.items():
        db_month[d[:7]] += n
    print("② ฐานข้อมูลตอนนี้")
    print(f"    เคสผ่าตัดเสร็จล่าสุดในฐานข้อมูล : {_th(db_last) if db_last else 'ไม่มี'}")
    _month_table("    จำนวนแถวในฐานข้อมูล ช่วงเดียวกับไฟล์", db_month)

    in_range = [d for d in sorted(set(i_dates)) if d_from <= d <= d_until]
    target = [d for d in in_range if d not in db_days]
    skipped = [d for d in in_range if d in db_days]
    tset = set(target)
    n_intra = sum(1 for d in F['i_iso'] if d in tset)
    n_sched = sum(1 for d in F['s_iso'] if d in tset)
    new_month = collections.Counter(d[:7] for d in F['i_iso'] if d in tset)   # นับแถว intraop ทั้งหมดของวันเป้าหมาย
    print("③ แผนนำเข้า")
    print(f"    ช่วง {_th(d_from)} ถึง {_th(d_until)} : {len(in_range)} วันที่มีเคสในไฟล์")
    print(f"    ข้าม {len(skipped)} วันที่ฐานข้อมูลมีแล้ว"
          + (f" ({_th(skipped[0])} ถึง {_th(skipped[-1])})" if skipped else ""))
    _ti, _to = HC.col(F['ih'], 'roomtimein'), HC.col(F['ih'], 'roomtimeout')
    n_notime = sum(1 for r, d in zip(F['irows'], F['i_iso'])
                   if d in tset and not (_hhmm(r[_ti]) and _hhmm(r[_to])))
    print(f"    นำเข้า {len(target)} วัน : ตารางผ่าตัด {n_sched} แถว · แถว intraop {n_intra} "
          f"(ไม่มีเวลาเข้าออกห้อง ไม่นำเข้า {n_notime}) · จะเพิ่มราว {n_intra - n_notime} เคส")
    _month_table("    แถว intraop ของวันที่จะนำเข้า แยกเดือน", new_month)
    # วันที่ในฐานข้อมูลมีบางส่วน (เช่นวันที่ใช้ระบบสด) : บอกให้เห็น ไม่แก้ให้
    _i_day = collections.Counter(d for d in F['i_iso'] if d)
    _thin = [d for d in skipped if db_days[d] < 0.5 * _i_day[d]]
    if _thin:
        print(f"    ⚠️ มี {len(_thin)} วันที่ฐานข้อมูลมีแถวน้อยกว่าครึ่งของไฟล์ (ถูกข้ามตามกติกา) "
              f"เช่น {', '.join(_th(d) for d in _thin[:5])}")

    if not apply:
        print("-" * 66)
        print(" นี่คือ DRY-RUN : ยังไม่ได้เขียนอะไร · ถ้าตัวเลขถูกต้อง รันซ้ำโดยเติม --apply")
        print("=" * 66)
        return
    if not target:
        print(" ไม่มีวันใหม่ให้นำเข้า")
        return

    # ── เขียนจริง : 1 เคสที่ผ่าตัดจริง (intraop) = 1 แถว แบบเดียวกับ import_history_6467 ──
    print("④ นำเข้าเคสที่ผ่าตัดจริง + ทำนายเวลา")
    from main_or_db import mask_unmasked_staff
    try:
        n_ins, n_dup, n_nosched, n_baddur, n_notime = insert_cases(F, tset)
        print(f"    เพิ่ม {n_ins} เคส · ซ้ำกับที่มีอยู่ {n_dup} · "
              f"ไม่มีแถวในตารางผ่าตัด {n_nosched} · เวลาครองห้องใช้ไม่ได้ (เว้นว่าง) {n_baddur} · "
              f"ไม่มีเวลาเข้าออกห้อง (ไม่นำเข้า) {n_notime}")
    finally:
        # 🎭 ต้องรันเสมอ แม้ขั้นบนล้มกลางทาง : กันชื่อจริงค้างบนคลาวด์
        print("⑤ แปลงชื่อแพทย์และพยาบาลเป็นรหัส")
        try:
            print(f"    {mask_unmasked_staff()} ชื่อ")
        except Exception as ex:
            print(f"    ⚠️ แปลงชื่อไม่สำเร็จ ({type(ex).__name__}: {ex}) : "
                  f"ต้องรันซ้ำก่อนปิดงาน ห้ามปล่อยค้าง")

    conn = get_conn()
    try:
        after = conn.execute(
            "SELECT substr(op_date,1,7), COUNT(*), "
            "SUM(CASE WHEN status='discharged' THEN 1 ELSE 0 END) FROM cases "
            "WHERE op_date >= ? AND op_date <= ? GROUP BY substr(op_date,1,7)",
            (f_min, f_max)).fetchall()
    finally:
        conn.close()
    print("⑥ ฐานข้อมูลหลังนำเข้า (ทั้งหมด / ผ่าตัดเสร็จ)")
    for ym, n, nd in sorted(tuple(r) for r in after):
        print(f"    {_TH_MON[int(ym[5:7])]:>5} {int(ym[:4]) + 543} : {n:>5} / {nd or 0:>5}")
    print(" เสร็จ : เปิดหน้า สถิติย้อนหลัง แล้วกด 🔄 รีเฟรช เพื่อล้างผลที่จำไว้ 15 นาที")
    print("=" * 66)


if __name__ == '__main__':
    main()
