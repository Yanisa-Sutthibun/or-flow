# -*- coding: utf-8 -*-
"""
research_upload_panel.py : 🌐 อัปโหลดไฟล์ HIS รายวันที่เดียว ใช้ได้ทั้งข้อมูลวิจัยและฐานสถิติ
════════════════════════════════════════════════════════════════════════════
สร้าง 24 พ.ย. 2026 (มุกกี้สั่ง: "ทำบนเว็บไซต์ดีกว่า เพราะ ข้อมูลจะมาจากเครื่องของ รพ."
และ "upload ที่เดียวแล้วใช้งานได้ทั้งสถิติ แล้วก็งานวิจัย อันไหนจับคู่ไม่ได้ก็เป็นเลื่อน/ยกเลิกไป")

ทำไมต้องมี: งานเช้า 08:00 เดิมต้องเปิด PowerShell บนเครื่องที่มี secrets รัน 3 ถึง 4 สคริปต์
แต่ไฟล์ export จากเครื่อง รพ. ซึ่งไม่มีโปรเจกต์ → อัปโหลดจากเบราว์เซอร์ครั้งเดียวจบ
ใช้แกนเดียวกับสคริปต์ทุกบรรทัด ไม่เขียนตรรกะซ้ำ

กดบันทึกครั้งเดียว ทำ 3 อย่างตามลำดับ
  1. ข้อมูลวิจัย : เติมเวลาผ่าตัดจริงจาก intraop (backfill_actual.run)
  2. ข้อมูลวิจัย : เคสของวันนั้นที่ไม่พบใน intraop ติดป้าย เลื่อน/ยกเลิก (backfill_actual.mark_not_in_file)
  3. ฐานสถิติ   : เพิ่มเคสที่ผ่าจริงของวันนั้น (update_stats_from_his.main) : ต้องมีไฟล์ตารางผ่าตัดด้วย
ก่อนกดบันทึก ระบบแสดงผลให้ดูก่อนทุกขั้น (ยังไม่เขียน)

🔒 PDPA
  · ไฟล์ HIS มี HN และชื่อผู้ป่วย : พักเป็นไฟล์ชั่วคราวระหว่างอ่านเท่านั้น แล้วลบทิ้งทุกครั้ง (finally)
  · ข้อมูลวิจัยลงแค่เวลากับจำนวนนาที จับคู่ด้วยรหัสแฮชของ HN · ฐานสถิติใช้กติกา mask เดิมของสคริปต์
  · ไม่แสดงเนื้อหาแถวบนจอ · เฉพาะผู้วิจัย (role admin) : ตัวเรียกเป็นคนตรวจสิทธิ์

วางในหน้าตั้งค่า:
    from research_upload_panel import render_research_upload
    render_research_upload()
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone


def _tmp_of(up):
    """ไฟล์ที่อัปโหลด → ไฟล์ชั่วคราว (ผู้เรียกต้องลบเอง)"""
    ext = os.path.splitext(getattr(up, 'name', '') or '')[1].lower() or '.csv'
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp.write(up.getvalue())
    tmp.close()
    return tmp.name


def _rm(*paths):
    for p in paths:
        try:
            if p:
                os.remove(p)
        except OSError:
            pass


def _stats(sched_path, intra_path, until, apply):
    """เรียกตัวเติมฐานสถิติ (สคริปต์ชุดเดิม) แล้วเก็บข้อความที่พิมพ์ · sys.exit ของสคริปต์ = หยุดอย่างปลอดภัย"""
    import update_stats_from_his as U
    argv0 = sys.argv
    buf = io.StringIO()
    try:
        sys.argv = ['update_stats_from_his.py', sched_path, intra_path, '--until', until] + (
            ['--apply'] if apply else [])
        with contextlib.redirect_stdout(buf):
            try:
                U.main()
            except SystemExit as _se:
                if _se.code not in (None, 0):
                    print(str(_se.code))
    finally:
        sys.argv = argv0
    return buf.getvalue()


def _process(intra_up, sched_up, apply):
    """รันครบ 3 ขั้นกับไฟล์ที่อัปโหลด · คืน dict ผลของแต่ละขั้น · ลบไฟล์ชั่วคราวเสมอ"""
    import backfill_actual as BA
    ip = sp = None
    try:
        ip = _tmp_of(intra_up)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = BA.run(ip, apply=apply)
            marked = BA.mark_not_in_file(ip, apply=apply)
        out = {'res': res, 'log': buf.getvalue(), 'marked': marked, 'stats': None}
        if sched_up is not None:
            today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()
            past = [d for d in (res.get('dates') or []) if d < today]
            if past:
                sp = _tmp_of(sched_up)
                out['stats'] = _stats(sp, ip, max(past), apply)
            else:
                out['stats'] = 'ไฟล์นี้มีแต่เคสของวันนี้ ซึ่งยังไม่ครบวัน : ยังไม่เติมฐานสถิติ'
        return out
    finally:
        _rm(ip, sp)


def _day_report(day):
    """สรุปของวัน (ชุดเดียวกับ check_research_day.py) เป็นข้อความ"""
    import check_research_day as CR
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        CR.main(day)
    return buf.getvalue()


def render_research_upload():
    import streamlit as st
    st.caption("ใช้ทุกเช้า : export ไฟล์ของวันก่อนหน้าแบบเต็มวันจาก HIS แล้วอัปโหลดที่นี่ที่เดียว "
               "ระบบเติมเวลาผ่าตัดจริงลงข้อมูลวิจัย ติดป้ายเลื่อน/ยกเลิกให้เคสที่ไม่พบใน intraop "
               "และเพิ่มเคสของวันนั้นเข้าฐานสถิติ")
    c1, c2 = st.columns(2)
    intra = c1.file_uploader("① ไฟล์ intraop (.csv / .xls / .xlsx)", type=["csv", "xls", "xlsx"],
                             key="rs_intra")
    sched = c2.file_uploader("② ไฟล์ตารางผ่าตัดของวันเดียวกัน (.csv)", type=["csv"], key="rs_sched",
                             help="ใช้เติมฐานสถิติ ถ้าไม่ใส่ ระบบจะทำเฉพาะส่วนข้อมูลวิจัย")
    if intra is None:
        _last = st.session_state.get('_rs_last')
        if _last:
            st.success(_last.get('msg', 'บันทึกแล้ว'))
            st.code(_last.get('report', ''), language=None)
        return
    try:
        pv = _process(intra, sched, apply=False)
    except Exception as _ex:
        st.error("อ่านไฟล์นี้ไม่ได้ : ตรวจว่าเป็นไฟล์ที่ export จาก HIS โดยตรง")
        with st.expander("รายละเอียดทางเทคนิค (สำหรับผู้วิจัย)"):
            st.code(f"{type(_ex).__name__}: {_ex}"[:600], language=None)
        return
    res, marked = pv['res'], pv['marked']
    _dates = ' , '.join(res.get('dates') or []) or '-'
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("เคสในไฟล์ intraop", res['rows'])
    k2.metric("จับคู่กับข้อมูลวิจัยได้", res['matched'])
    k3.metric("จะติดป้ายเลื่อน/ยกเลิก", len(marked))
    k4.metric("ไม่อยู่ในข้อมูลวิจัย", res['missed'])
    st.caption(f"วันที่ในไฟล์ : {_dates} · เคสที่ไม่อยู่ในข้อมูลวิจัย คือ เคสนอกเวลา เคสฉุกเฉิน "
               f"หรือเคสที่ไม่ได้อยู่ในตารางผ่าตัดที่อัปโหลดขึ้นบอร์ด ซึ่งเป็นเรื่องปกติ"
               + (f" · ข้ามผู้ป่วยที่ผ่ามากกว่า 1 ครั้งในวันเดียว {res['dup']} ราย" if res.get('dup') else ''))
    if marked:
        with st.expander(f"เคสที่จะติดป้ายเลื่อน/ยกเลิก ({len(marked)} เคส) : ตรวจก่อนบันทึก", expanded=True):
            st.code('\n'.join(f"{d} · ห้อง {rm} · นัด {tm or '-'} · {str(pr or '-')[:50]}"
                               for d, rm, tm, pr in marked), language=None)
    with st.expander("ผลจับคู่รายเคสของข้อมูลวิจัย (แสดงเฉพาะรหัสย่อ ไม่มีชื่อหรือ HN)"):
        st.code(pv['log'], language=None)
    if pv['stats'] is not None:
        with st.expander("แผนเติมฐานสถิติ"):
            st.code(pv['stats'], language=None)
    else:
        st.info("ยังไม่ได้ใส่ไฟล์ตารางผ่าตัด : จะบันทึกเฉพาะข้อมูลวิจัย ฐานสถิติไม่เปลี่ยน")
    if not res['matched']:
        st.warning("ยังจับคู่กับข้อมูลวิจัยไม่ได้สักเคส : ตรวจว่าตารางผ่าตัดของวันนั้นถูกอัปโหลดขึ้นบอร์ดแล้ว "
                   "และไฟล์นี้เป็นของวันเดียวกัน (ระบบจะไม่ติดป้ายเลื่อน/ยกเลิกให้วันที่จับคู่ไม่ได้เลย)")
    if st.button("💾 บันทึกทั้งหมด", key="rs_apply", type="primary", width='stretch'):
        try:
            ap = _process(intra, sched, apply=True)
            _rep = '\n\n'.join(_day_report(d) for d in (ap['res'].get('dates') or []))
            if ap['stats'] is not None:
                _rep += '\n\n' + ap['stats']
            _msg = (f"บันทึกแล้ว : เติมเวลาจริง {ap['res']['updated']} เคส · "
                    f"ติดป้ายเลื่อน/ยกเลิก {len(ap['marked'])} เคส"
                    + (" · เติมฐานสถิติแล้ว (ดูรายละเอียดด้านล่าง)" if ap['stats'] is not None else ''))
            st.session_state['_rs_last'] = {'msg': _msg, 'report': _rep}
            st.success(_msg)
            st.code(_rep, language=None)
        except Exception as _ex:
            st.error("บันทึกไม่สำเร็จ ลองใหม่อีกครั้ง ถ้ายังไม่ได้ให้ส่งภาพหน้าจอนี้ให้ผู้วิจัย")
            with st.expander("รายละเอียดทางเทคนิค (สำหรับผู้วิจัย)"):
                st.code(f"{type(_ex).__name__}: {_ex}"[:600], language=None)
