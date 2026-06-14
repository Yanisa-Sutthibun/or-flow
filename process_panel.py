"""
process_panel.py — ปุ่ม "③ ประมวลผลทั้งหมด" (อัปไฟล์ครั้งเดียว → dashboard + สอนโมเดล)
=====================================================================================
ออกแบบให้ง่ายสุด:
   ① ลากไฟล์ schedule (.csv)   ② ลากไฟล์ intraop (.xls)   ③ กดปุ่มเดียว
ระบบจะทำให้ครบ:
   • นำเข้า schedule → dashboard (สร้างเคส + AI ทำนาย)
   • อัปเดตเวลาจริงจาก intraop → dashboard
   • สอนโมเดล (fine-tune) + ใช้ตัวใหม่อัตโนมัติถ้าแม่นขึ้น

แก้ปัญหาเดิม: ไฟล์ schedule ของ HIS เป็นแบบ "quote ครอบทั้งบรรทัด (UTF-16)"
ตัวอ่าน CSV ปกติอ่านไม่ออก → ใช้ parser 2 ชั้นเดียวกับ fine-tune

วางในหน้าบริหาร:
    from process_panel import render_process_panel
    render_process_panel()
"""
from __future__ import annotations

import csv
import io


def build_schedule_db_df(schedule_src):
    """parse schedule (quote ซ้อน, UTF-16) → DataFrame ที่ import_schedule ใช้ได้
    (คอลัมน์ตรงกับ alias ของ import_schedule + opedate เป็น ISO date)"""
    import pandas as pd
    import finetune_pipeline as FP

    text = FP._read_utf16_text(schedule_src)
    rows = []
    for outer in csv.reader(io.StringIO(text)):
        inner = outer[0] if len(outer) == 1 else ",".join(outer)
        rows.append(next(csv.reader([inner])))

    recs = []
    for r in rows[1:]:
        if len(r) < 29:
            continue
        recs.append({
            "hn": r[0].strip(),
            "reqdate": r[1].strip(),
            "reqtime": r[2].strip(),
            "division": r[3].strip(),
            "orroom": r[5].strip(),
            "an": r[7].strip(),
            "estmtime": r[9].strip(),
            "dspname": r[14].strip(),       # ชื่อผู้ป่วย
            "optype_var": r[16].strip(),
            "opedate": FP._norm_date(r[19]) or "",   # ISO date — import_schedule group ได้แน่
            "opetime": r[20].strip(),
            "age": r[22].strip(),
            "icd9cm_name": r[24].strip(),
            "icd10_name": r[25].strip(),
            "surgstfnm": r[28].strip(),
            "procnote": r[29].strip() if len(r) > 29 else "",
        })
    df = pd.DataFrame(recs)
    if len(df):
        df = df[df["opedate"] != ""]
        # กันเคสซ้ำ key เดียวกัน (op_date+hn+หัตถการ) — ตรงกับ UNIQUE ของตาราง cases
        df = df.drop_duplicates(subset=["hn", "opedate", "icd9cm_name"], keep="first")
    return df.reset_index(drop=True)


def _complete_cases_from_files(schedule_src, intraop_src) -> int:
    """ทำเครื่องหมายเคสที่ "จบแล้ว" ใน DB → status='discharged' + เวลา/duration จริง
    จับคู่ด้วย key เดียวกับตอน import_schedule (วันที่ + ห้อง + หัตถการ + หมอที่ set)
    (🔒 DB ไม่เก็บ an/hn — join sched↔intra ใช้ hn ในหน่วยความจำ, จับคู่ DB ใช้ชุดที่ไม่ระบุตัวบุคคล)
    ทำให้สถิติย้อนหลังเห็นทันที (สถิตินับเฉพาะเคสที่ status เสร็จแล้ว)
    คืนจำนวนเคสที่อัปเดต"""
    import pandas as pd
    import finetune_pipeline as FP
    from main_or_db import get_conn

    sdf = build_schedule_db_df(schedule_src)[
        ["hn", "surgstfnm", "opedate", "orroom", "icd9cm_name"]].copy()
    sdf["orroom"] = pd.to_numeric(sdf["orroom"], errors="coerce")

    idf = FP._parse_intraop(intraop_src).rename(columns={"opedate_norm": "opedate"})
    idf["orroom"] = pd.to_numeric(idf["orroom"], errors="coerce")

    m = sdf.merge(idf, on=["hn", "opedate", "orroom"], how="inner")

    def _ts(date_s, minutes):
        if pd.isna(minutes):
            return None
        mm = int(minutes)
        return f"{date_s} {mm // 60:02d}:{mm % 60:02d}:00"

    # cloud อาจ mask scheduled_surgeon เป็น SURG_xxx แล้ว → เตรียมแปลงชื่อจริง→รหัส
    try:
        from staff_unmask import _reverse_and_max
        _surg2code, _ = _reverse_and_max("SURG")
    except Exception:
        _surg2code = {}

    conn = get_conn()
    n = 0
    for _, r in m.iterrows():
        in_ts = _ts(r["opedate"], r.get("roomtimein_min"))
        out_ts = _ts(r["opedate"], r.get("roomtimeout_min"))
        dur = int(r["duration_minutes"]) if pd.notna(r.get("duration_minutes")) else None
        try:
            room = int(r["orroom"]) if pd.notna(r.get("orroom")) else -1
        except (TypeError, ValueError):
            room = -1
        surg = str(r.get("surgstfnm") or "").strip()
        surg_code = _surg2code.get(surg, surg)   # ใช้รหัสถ้า cloud mask หมอแล้ว
        _sc = r.get("scrub_nurse"); scrub = str(_sc).strip() if pd.notna(_sc) else None
        _ci = r.get("circ_nurse"); circ = str(_ci).strip() if pd.notna(_ci) else None
        if scrub and scrub.upper() in ("NAN", "NONE", ""):
            scrub = None
        if circ and circ.upper() in ("NAN", "NONE", ""):
            circ = None
        # 🔒 จับคู่ด้วย (วันที่, ห้อง, หัตถการ, หมอ) — รองรับทั้งชื่อจริงและรหัส masked
        cur = conn.execute(
            "UPDATE cases SET status='discharged', "
            "actual_duration_min=COALESCE(?, actual_duration_min), "
            "in_or_at=COALESCE(?, in_or_at), op_end_at=COALESCE(?, op_end_at), "
            "discharged_at=COALESCE(?, discharged_at), "
            "scrub_nurse=COALESCE(?, scrub_nurse), circ_nurse=COALESCE(?, circ_nurse) "
            "WHERE op_date=? AND COALESCE(room_no,-1)=? AND procedure_name=? "
            "AND COALESCE(scheduled_surgeon,'') IN (?, ?)",
            (dur, in_ts, out_ts, out_ts, scrub, circ,
             r["opedate"], room, r["icd9cm_name"], surg, surg_code),
        )
        n += cur.rowcount
    conn.commit()
    conn.close()
    return n


def render_process_panel():
    import streamlit as st
    import finetune_pipeline as FP

    if "proc_report" not in st.session_state:
        st.session_state["proc_report"] = None

    st.caption(
        "ลากไฟล์ **schedule + intraop** ของช่วงใหม่เข้ามา แล้วกด **③ ประมวลผล** ปุ่มเดียว — "
        "ระบบจะอัปเดต **dashboard** (เคส + เวลาจริง + สถิติ) ให้ครบ\n\n"
        "🧠 ตัวทำนายบนบอร์ดคือ **honest_v1** (เทรนด้วยข้อมูล พ.ศ. 2564–2567 "
        "ตามขอบเขต ethics approval — ตรึงไว้ให้ตรงกับเล่มวิจัย)"
    )
    st.info(
        "🔒 **การสอนโมเดล (fine-tune) ถูกปิดใช้งาน** — ข้อมูลปี 2568–2569 อยู่นอกขอบเขต "
        "ที่คณะกรรมการจริยธรรมอนุมัติ (เทรนได้เฉพาะ พ.ศ. 2564–2567) · โมเดลที่เคย fine-tune "
        "ถูกย้ายไปกักกันแล้ว · จะเปิดได้เมื่อยื่น amendment ผ่าน "
        "(ดู docs/ETHICS_LOCK_2026-06-10.md)"
    )

    c1, c2 = st.columns(2)
    sched = c1.file_uploader("① ไฟล์ schedule (.csv)", type=["csv"], key="proc_sched")
    intra = c2.file_uploader("② ไฟล์ intraop (.xls/.xlsx)", type=["xls", "xlsx"], key="proc_intra")

    if st.button("③ ▶️ ประมวลผลทั้งหมด (อัปเดต dashboard + สถิติ)", type="primary",
                 width="stretch", key="proc_run",
                 disabled=(sched is None or intra is None)):
        report = {}

        # 1) schedule → dashboard (DB) — มีแถบ progress ให้เห็นว่าไม่ค้าง
        try:
            from main_or_db import import_schedule
            df_sched = build_schedule_db_df(sched)
            days = list(df_sched.groupby("opedate"))
            total = 0
            prog = st.progress(0.0, text="① นำเข้า schedule → dashboard...")
            for i, (op_date, grp) in enumerate(days):
                total += import_schedule(grp.copy(), op_date)
                prog.progress((i + 1) / max(len(days), 1),
                              text=f"① นำเข้า schedule → dashboard... {i + 1}/{len(days)} วัน")
            prog.empty()
            report["schedule"] = f"✅ นำเข้า {total} เคส จาก {len(days)} วัน"
        except Exception as e:
            import traceback
            report["schedule"] = f"❌ {e}"
            report["_sched_tb"] = traceback.format_exc()

        # 2) intraop → เวลาจริง (DB)
        with st.spinner("② อัปเดตเวลาจริงจาก intraop..."):
            import tempfile, os
            tmp = None
            try:
                suffix = "." + intra.name.split(".")[-1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                    f.write(intra.getvalue())
                    tmp = f.name
                from import_historical import reimport_timestamps
                res = reimport_timestamps(tmp)
                report["intraop"] = (f"✅ อัปเดตเวลา {res.get('updated', 0)} เคส"
                                     + (f" · ไม่เจอใน DB {res.get('not_found', 0)} เคส"
                                        if res.get('not_found') else ""))
            except Exception as e:
                report["intraop"] = f"❌ {e}"
            finally:
                if tmp:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass

        # 2b) mark เคสที่จบแล้ว = discharged + เวลา/duration จริง → สถิติเห็นทันที
        with st.spinner("ทำเครื่องหมายเคสที่เสร็จแล้ว → สถิติ..."):
            try:
                for _f in (sched, intra):
                    try:
                        _f.seek(0)
                    except Exception:
                        pass
                n_done = _complete_cases_from_files(sched, intra)
                report["completed"] = f"✅ ทำเครื่องหมายเสร็จแล้ว {n_done} เคส (สถิติเห็นแล้ว)"
            except Exception as e:
                import traceback
                report["completed"] = f"❌ {e}"
                report["_done_tb"] = traceback.format_exc()

        # 2c) 🎭 mask ชื่อหมอจริงที่เพิ่ง import → SURG_xxx (กันชื่อจริงค้างบน cloud)
        with st.spinner("🎭 ปิดชื่อหมอ/พยาบาล (mask) ก่อนเก็บขึ้น cloud..."):
            try:
                from main_or_db import mask_unmasked_staff
                _nmask = mask_unmasked_staff()
                if _nmask:
                    report["mask"] = f"🎭 ปิดชื่อหมอ/พยาบาล {_nmask} ชื่อ → รหัส (PDPA)"
            except Exception as e:
                report["mask"] = f"⚠️ mask ชื่อไม่สำเร็จ: {e}"

        # 3) fine-tune (ML) — 🔒 ETHICS LOCK: ถอดออก 10 มิ.ย. 2026
        #    ข้อมูลปี 2568-2569 อยู่นอกขอบเขต ethics approval (เทรนได้เฉพาะ 2564-2567)
        #    โค้ดเดิมอยู่ใน git history · engine ติดกุญแจใน retrain_model.py
        #    คืนระบบหลังได้ amendment: ดู docs/ETHICS_LOCK_2026-06-10.md

        st.session_state["proc_report"] = report

    # ---- แสดงผลรวม ----
    rep = st.session_state.get("proc_report")
    if rep:
        st.markdown("---")
        st.markdown("#### ผลการประมวลผล")
        if "schedule" in rep:
            st.write("📅 **Dashboard — schedule:**", rep["schedule"])
            if "_sched_tb" in rep:
                with st.expander("รายละเอียด error (schedule)"):
                    st.code(rep["_sched_tb"])
        if "intraop" in rep:
            st.write("🩺 **Dashboard — intraop:**", rep["intraop"])
        if "completed" in rep:
            st.write("✅ **สถิติ (เคสเสร็จแล้ว):**", rep["completed"])
            if "_done_tb" in rep:
                with st.expander("รายละเอียด error (mark completed)"):
                    st.code(rep["_done_tb"])
        # (🔒 ส่วนแสดงผล fine-tune ถูกถอดออกพร้อม ETHICS LOCK — 10 มิ.ย. 2026)
