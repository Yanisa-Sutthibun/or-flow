# -*- coding: utf-8 -*-
"""
tests/test_board_state.py — ชุดทดสอบหัวใจของบอร์ด (11 ส.ค. 2026 · ตรวจระบบข้อ 10)
════════════════════════════════════════════════════════════════════════════
ทำไมต้องมี: apply_finish / apply_undo_finish / logic merge คือส่วนที่ "พังแล้ว
กระทบผู้ป่วยจริง" (บอร์ดบอกห้องว่างทั้งที่ยังผ่าอยู่ / สถานะถูกดึงย้อน) แต่เดิม
ตรวจด้วยการ mock ทีละครั้งด้วยมือทุกรอบที่แก้โค้ด ซึ่งลืมได้และไม่ครบ

วิธีรัน (ไม่ต้องติดตั้งอะไรเพิ่ม — โปรเจกต์นี้ไม่มี pytest):
    python tests\test_board_state.py
ถ้าเครื่องไหนมี pytest อยู่แล้วก็รันได้เหมือนกัน (ฟังก์ชันชื่อ test_* + assert ล้วน):
    pytest tests\test_board_state.py -q
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import st_stub                                     # noqa: E402

st = st_stub.install()                             # ต้องมาก่อน import โมดูลแอป

import main_or_core as C                           # noqa: E402
import main_or_pages as P                          # noqa: E402
import main_or_app as A                            # noqa: E402
import main_or_db as D                             # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 🔌 ตัดขาดจาก I/O จริงก่อนรันเทสต์ใด ๆ  ⛔ ห้ามลบบล็อกนี้
# ───────────────────────────────────────────────────────────────────────────
# บทเรียน 11 ส.ค. 2026: เทสต์รอบแรกเรียก _save_board_snapshot ตรง ๆ
# แล้วมันเขียนทั้ง data/_board_snapshot.json ของจริง "และ" board_state
# บน Supabase production (เพราะ .streamlit/secrets.toml ในเครื่องนี้ชี้ orsurg)
# = เคสปลอมชื่อ "TEST OPERATION" ไปโผล่บนบอร์ดกลางของจริง
#
# กติกาถาวรของไฟล์เทสต์นี้: ไม่แตะ DB จริง ไม่แตะไฟล์จริง ไม่ว่าเครื่องไหนรัน
# ═══════════════════════════════════════════════════════════════════════════
_FAKE_DB: dict = {}          # board_state ปลอมในหน่วยความจำ


def _isolate_io():
    import tempfile
    # ① snapshot ไปลงไฟล์ชั่วคราว ไม่ใช่ data/_board_snapshot.json ของจริง
    P._SNAPSHOT_PATH = os.path.join(
        tempfile.mkdtemp(prefix='orflow_test_'), '_board_snapshot.json')

    # ② ตัดทางเขียน/อ่าน DB ทุกเส้นที่ _save_board_snapshot ใช้
    #    (มัน import ข้างในฟังก์ชัน → patch ที่ตัวโมดูล main_or_db ได้ผลจริง)
    def _fake_save(op_date, payload):
        _FAKE_DB[str(op_date)] = payload
        return True

    def _fake_load(op_date):
        return _FAKE_DB.get(str(op_date))

    D.save_board_state = _fake_save
    D.load_board_state = _fake_load

    # ③ กันพลาดชั้นสุดท้าย: ถ้ามีอะไรเผลอเปิด connection จริง ให้ระเบิดทันที
    #    ดังกว่าเงียบ — เทสต์ที่แอบเขียน production คือสิ่งที่เรากำลังกันอยู่
    def _no_conn(*_a, **_k):
        raise AssertionError(
            "⛔ เทสต์พยายามเปิด connection ฐานข้อมูลจริง — ห้ามเด็ดขาด "
            "(ให้ mock ฟังก์ชันที่แตะ DB ในเทสต์นั้นแทน)")

    D.get_conn = _no_conn


_isolate_io()


# ═════════════════════════════ helpers ═════════════════════════════

def _fresh_state():
    """ล้าง session_state + ตั้งค่าเริ่มต้นที่ apply_finish/undo ต้องใช้"""
    st.session_state.clear()
    for _k in st.calls:
        if isinstance(st.calls[_k], list):
            st.calls[_k].clear()
        else:
            st.calls[_k] = 0
    st.session_state['or_rooms'] = {}
    st.session_state['statistics'] = {
        'total_cases': 0, 'completed_cases': 0, 'cancelled_cases': 0,
        'case_history': [], 'predictions_history': []}


def _case(**kw):
    """เคสตัวอย่าง — ค่าตั้งต้นเป็นเคสสาธิต (_demo) เพื่อไม่ให้แตะ log วิจัยจริง"""
    c = {
        'id': 'C1', 'name': 'ทดสอบ ระบบ', 'hn': '9999999',
        'procedure': 'TEST OPERATION', 'surgeon': 'หมอทดสอบ',
        'room': 91, 'or_room_assigned': 91, 'division': '75',
        'status': 'in_or', 'case_type': 'Elective', 'is_emergency': False,
        'sched_hour': 9, 'sched_min': 0, 'is_tf': False,
        'ai_predicted_min': 60, 'predicted_min': 60, 'effective_min': 60,
        'user_override_min': None, 'actual_duration_min': None,
        'time_arrived_holding': None, 'time_entered_or': None,
        'time_exited_or': None, 'time_discharged': None,
        '_demo': True,
    }
    c.update(kw)
    return c


# ═══════════════ 1. state machine: ผ่าเสร็จ / ย้อนกลับ ═══════════════

def test_finish_sets_status_and_duration():
    """กด 'ผ่าเสร็จ' → สถานะเปลี่ยน + คิดเวลาที่ใช้จริงจากเวลาเข้าห้อง"""
    _fresh_state()
    c = _case(time_entered_or=P._now() - timedelta(minutes=75))
    cases = [c]
    assert P.apply_finish(cases, 0, 91, 'ห้องรับ-ส่ง') is True
    assert c['status'] == 'holding_post'
    assert c['time_exited_or'] is not None
    assert 70 <= c['actual_duration_min'] <= 80, c['actual_duration_min']
    assert st.session_state['statistics']['completed_cases'] == 1


def test_finish_to_recovery_sets_recovery_status():
    _fresh_state()
    c = _case(time_entered_or=P._now() - timedelta(minutes=30))
    assert P.apply_finish([c], 0, 91, 'ห้องพักฟื้น') is True
    assert c['status'] == 'recovery'


def test_finish_twice_is_ignored():
    """กดรัว/สองเครื่องกดพร้อมกัน — ครั้งที่สองต้องไม่นับซ้ำ"""
    _fresh_state()
    c = _case(time_entered_or=P._now() - timedelta(minutes=30))
    cases = [c]
    assert P.apply_finish(cases, 0, 91, 'ห้องรับ-ส่ง') is True
    assert P.apply_finish(cases, 0, 91, 'ห้องรับ-ส่ง') is False
    assert st.session_state['statistics']['completed_cases'] == 1


def test_finish_clamps_negative_duration():
    """นาฬิกาเครื่องเพี้ยน (เวลาเข้าห้องอยู่ในอนาคต) ต้องไม่ได้เวลาติดลบ"""
    _fresh_state()
    c = _case(time_entered_or=P._now() + timedelta(minutes=20))
    P.apply_finish([c], 0, 91, 'ห้องรับ-ส่ง')
    assert c['actual_duration_min'] >= 1


def test_undo_finish_restores_in_or():
    """กด ↩️ หลังกดเสร็จ → กลับเป็นกำลังผ่า + ตัวนับลดกลับ + ล้างเวลาออกห้อง"""
    _fresh_state()
    c = _case(time_entered_or=P._now() - timedelta(minutes=40))
    cases = [c]
    P.apply_finish(cases, 0, 91, 'ห้องรับ-ส่ง')
    assert P.apply_undo_finish(cases, 0) is True
    assert c['status'] == 'in_or'
    assert c['time_exited_or'] is None
    assert c['actual_duration_min'] is None
    assert st.session_state['statistics']['completed_cases'] == 0


def test_undo_finish_rejects_wrong_status():
    """↩️ ใช้ได้เฉพาะเคสที่เพิ่งกดเสร็จ — เคสกำลังผ่าอยู่ห้ามย้อน"""
    _fresh_state()
    assert P.apply_undo_finish([_case(status='in_or')], 0) is False
    assert P.apply_undo_finish([_case(status='not_arrived')], 0) is False


def test_undo_marks_intentional_undo():
    """↩️ ต้องติดธง undo ไว้ ไม่งั้น merge จะกันการย้อนของจริงทิ้ง"""
    _fresh_state()
    c = _case(time_entered_or=P._now() - timedelta(minutes=40))
    cases = [c]
    P.apply_finish(cases, 0, 91, 'ห้องรับ-ส่ง')
    P.apply_undo_finish(cases, 0)
    assert 'C1' in st.session_state.get('_board_undo_ids', set())


# ═══════════ 2. merge หลายเครื่อง: ห้ามสถานะถอยหลัง (CR-3) ═══════════

def test_phase_rank_order():
    assert (P._phase_rank({'status': 'not_arrived'})
            < P._phase_rank({'status': 'holding_pre'})
            < P._phase_rank({'status': 'in_or'})
            < P._phase_rank({'status': 'holding_post'})
            < P._phase_rank({'status': 'discharged'})
            < P._phase_rank({'status': 'removed'}))
    assert (P._phase_rank({'status': 'recovery'})
            == P._phase_rank({'status': 'holding_post'}))
    assert P._phase_rank({'status': 'อะไรไม่รู้'}) == 0
    assert P._phase_rank(None) == 0


def test_merge_blocks_status_regression():
    """แกนกลางของ CR-3: เครื่องค้างหน้าเก่ากด ✏️ ต้องไม่ดึงเคสกลับเป็นกำลังผ่า"""
    _fresh_state()
    mine = _case(status='in_or', effective_min=95, time_exited_or=None)
    theirs = _case(status='holding_post', effective_min=60,
                   time_exited_or='2026-08-11T10:30:00',
                   actual_duration_min=72)
    out, blocked = P._merge_case_no_regress(mine, theirs)
    assert blocked is True
    assert out['status'] == 'holding_post'          # ขั้นของเคสคงของล่าสุด
    assert out['actual_duration_min'] == 72
    assert out['time_exited_or'] == '2026-08-11T10:30:00'
    assert out['effective_min'] == 95               # แต่สิ่งที่คนแก้ยังอยู่ครบ


def test_merge_keeps_ours_when_we_are_ahead():
    """เครื่องเราเดินหน้ากว่า → ของเราชนะทั้งก้อน (พฤติกรรมเดิม)"""
    _fresh_state()
    mine = _case(status='holding_post', actual_duration_min=50)
    theirs = _case(status='in_or', actual_duration_min=None)
    out, blocked = P._merge_case_no_regress(mine, theirs)
    assert blocked is False
    assert out['status'] == 'holding_post'
    assert out['actual_duration_min'] == 50


def test_merge_same_phase_ours_wins():
    _fresh_state()
    mine = _case(status='in_or', effective_min=120)
    theirs = _case(status='in_or', effective_min=60)
    out, blocked = P._merge_case_no_regress(mine, theirs)
    assert blocked is False and out['effective_min'] == 120


def test_merge_allows_intentional_undo():
    """↩️ ที่คนตั้งใจกด ต้องย้อนได้จริง ไม่ถูก guard บล็อก"""
    _fresh_state()
    mine = _case(status='in_or', time_exited_or=None)
    theirs = _case(status='holding_post', time_exited_or='2026-08-11T10:30:00')
    out, blocked = P._merge_case_no_regress(mine, theirs, allow_undo=True)
    assert blocked is False
    assert out['status'] == 'in_or'
    assert out['time_exited_or'] is None


def test_merge_no_counterpart_keeps_ours():
    """เคสที่อีกเครื่องยังไม่มี (เพิ่งเพิ่มเข้ามา) ต้องไม่หาย"""
    _fresh_state()
    mine = _case(status='holding_pre')
    for _theirs in (None, {}):
        out, blocked = P._merge_case_no_regress(mine, _theirs)
        assert blocked is False and out['status'] == 'holding_pre'


def test_merge_does_not_resurrect_removed_case():
    """เคสที่ถูกเอาออกจากบอร์ดแล้ว ห้ามเครื่องเก่าปลุกกลับมา"""
    _fresh_state()
    mine = _case(status='in_or')
    theirs = _case(status='removed')
    out, blocked = P._merge_case_no_regress(mine, theirs)
    assert blocked is True and out['status'] == 'removed'


def test_merge_drops_stale_phase_field_not_in_theirs():
    """ถ้าของล่าสุดไม่มีช่องเวลานั้นแล้ว (ถูกล้างไป) ของเก่าต้องไม่ค้าง"""
    _fresh_state()
    mine = _case(status='in_or', time_entered_or='2026-08-11T09:00:00')
    theirs = {'id': 'C1', 'status': 'discharged'}
    out, blocked = P._merge_case_no_regress(mine, theirs)
    assert blocked is True
    assert out['status'] == 'discharged'
    assert 'time_entered_or' not in out


# ═════════ 3. ✏️ แก้เวลา: กันพิมพ์ผิดหลัก (ตรวจระบบข้อ 8) ═════════

def test_override_warns_on_typo_ten_times():
    """30 → 300 นาที (พิมพ์เกินหลัก) ต้องเตือน"""
    assert C.override_sanity_warning(300, 30)


def test_override_warns_when_far_below():
    assert C.override_sanity_warning(20, 180)


def test_override_silent_on_normal_edit():
    """แก้ตามปกติหน้างานต้องไม่เตือน (ไม่งั้นกลายเป็นเตือนหมาป่า)"""
    assert C.override_sanity_warning(90, 60) == ''
    assert C.override_sanity_warning(120, 60) == ''      # 2 เท่าพอดี ยังไม่เตือน
    assert C.override_sanity_warning(45, 60) == ''


def test_override_silent_on_short_cases():
    """เคสสั้น 10 → 25 นาที เป็น 2.5 เท่าก็จริง แต่ห่างกันแค่ 15 นาที = ปกติ"""
    assert C.override_sanity_warning(25, 10) == ''


def test_override_silent_without_ai_value():
    """ไม่รู้ค่า AI = ไม่มีอะไรให้เทียบ ห้ามเดา"""
    assert C.override_sanity_warning(300, None) == ''
    assert C.override_sanity_warning(300, 0) == ''
    assert C.override_sanity_warning('อะไรไม่รู้', 60) == ''


# ═══════════ 4. หน้า login: เทียบรหัส + กันเดา (ข้อ 1-2) ═══════════

def test_pwd_match_basic():
    assert A._pwd_match('secret123', 'secret123') is True
    assert A._pwd_match('secret124', 'secret123') is False
    assert A._pwd_match('', '') is False              # ไม่ตั้งรหัส = ไม่ผ่าน
    assert A._pwd_match('x', None) is False


def test_login_locks_after_max_tries():
    """พลาดครบโควตา → ถูกล็อก และยังไม่ล็อกก่อนหน้านั้น"""
    _fresh_state()
    A._GLOBAL_FAIL_LOG.clear()
    for _i in range(A._LOGIN_MAX_TRY - 1):
        A._login_note_fail()
        assert A._login_lock_left() == 0, f"ล็อกเร็วไปตั้งแต่ครั้งที่ {_i + 1}"
    A._login_note_fail()
    assert 0 < A._login_lock_left() <= A._LOGIN_LOCK_SEC


def test_login_lock_escalates():
    """ยิ่งพลาดซ้ำ ยิ่งล็อกนานขึ้น (แต่ไม่เกินเพดาน)"""
    _fresh_state()
    A._GLOBAL_FAIL_LOG.clear()
    for _ in range(A._LOGIN_MAX_TRY):
        A._login_note_fail()
    first = A._login_lock_left()
    A._login_note_fail()
    second = A._login_lock_left()
    assert second > first
    assert second <= A._LOGIN_LOCK_MAX


def test_login_counter_is_per_session():
    """ตัวนับผูกกับ session — ล้าง session แล้วต้องไม่ค้างล็อกไว้ข้ามคน"""
    _fresh_state()
    A._GLOBAL_FAIL_LOG.clear()
    for _ in range(A._LOGIN_MAX_TRY):
        A._login_note_fail()
    assert A._login_lock_left() > 0
    _fresh_state()
    assert A._login_lock_left() == 0


def test_global_fail_log_counts_across_sessions():
    """ชั้นที่สอง: นับรวมทั้งแอป เพื่อกันคนเปิด session ใหม่หนีตัวนับชั้นแรก"""
    _fresh_state()
    A._GLOBAL_FAIL_LOG.clear()
    A._login_note_fail()
    _fresh_state()                      # เปลี่ยน session แต่ตัวนับรวมต้องยังอยู่
    A._login_note_fail()
    assert A._login_recent_global_fails() >= 2


# ═════════ 5. สิทธิ์ผู้วิจัยหมดอายุเมื่อทิ้งไว้ (ข้อ 5) ═════════

def test_idle_timeout_logs_out_admin():
    _fresh_state()
    import time as _t
    st.session_state['role'] = 'admin'
    st.session_state['authenticated'] = True
    st.session_state['_maint_unlocked'] = True
    st.session_state['_last_activity'] = _t.monotonic() - (A._ADMIN_IDLE_SEC + 5)
    A._enforce_idle_timeout()
    assert st.session_state.get('authenticated') is None
    assert st.session_state.get('role') is None
    assert st.session_state.get('_maint_unlocked') is None
    assert st.session_state.get('_idle_logged_out') is True


def test_idle_timeout_keeps_active_admin():
    _fresh_state()
    import time as _t
    st.session_state['role'] = 'admin'
    st.session_state['authenticated'] = True
    st.session_state['_last_activity'] = _t.monotonic() - 60
    A._enforce_idle_timeout()
    assert st.session_state.get('authenticated') is True


def test_idle_timeout_never_touches_room_screen():
    """จอประจำห้อง/จอรับ-ส่ง เปิดค้างทั้งวันโดยตั้งใจ ห้ามถูกตัดสิทธิ์"""
    import time as _t
    for _role in ('room', 'user'):
        _fresh_state()
        st.session_state['role'] = _role
        st.session_state['authenticated'] = True
        st.session_state['_last_activity'] = _t.monotonic() - (A._ADMIN_IDLE_SEC * 3)
        A._enforce_idle_timeout()
        assert st.session_state.get('authenticated') is True, _role


# ═══════════ 6. ร่องรอยว่าเครื่องไหนกด (ข้อ 3 · ไม่ระบุตัวบุคคล) ═══════════

def test_current_actor_room_screen():
    _fresh_state()
    st.session_state['role'] = 'room'
    st.session_state['room_scope'] = 93
    assert D.current_actor() == ('room', 93)


def test_current_actor_admin_has_no_room():
    _fresh_state()
    st.session_state['role'] = 'admin'
    st.session_state['room_scope'] = 93      # ค่าค้างจากที่อื่นต้องไม่ถูกเก็บ
    assert D.current_actor() == ('admin', None)


def test_current_actor_unknown_when_not_logged_in():
    _fresh_state()
    assert D.current_actor() == (None, None)


def test_current_actor_survives_bad_room_value():
    _fresh_state()
    st.session_state['role'] = 'room'
    st.session_state['room_scope'] = 'ไม่ใช่ตัวเลข'
    assert D.current_actor() == ('room', None)


# ═════════ 7. สุขภาพสายการทำนาย AI (ข้อ 7) ═════════

def test_prediction_health_quiet_when_healthy():
    C._PRED_TALLY.clear()
    for _ in range(50):
        C._tally_prediction('thesis_ML_v2')
    h = C.prediction_health()
    assert h['total'] == 50 and h['fallback_n'] == 0 and h['alert'] is False


def test_prediction_health_alerts_on_fallback_storm():
    """โมเดลโหลดไม่ขึ้นแล้วตกไปใช้ค่าเริ่มต้น 60 นาที = ต้องเตือน"""
    C._PRED_TALLY.clear()
    for _ in range(30):
        C._tally_prediction('default')
    h = C.prediction_health()
    assert h['alert'] is True
    assert h['fallback_pct'] == 100.0
    assert 'thesis_ML_v2' in h['message']


def test_prediction_health_needs_enough_samples():
    """ทำนาย 2 ครั้งแล้วพลาด 1 = 50% แต่ยังสรุปไม่ได้ ห้ามเตือนหมาป่า"""
    C._PRED_TALLY.clear()
    C._tally_prediction('thesis_ML_v2')
    C._tally_prediction('default')
    assert C.prediction_health()['alert'] is False


def test_prediction_health_empty_is_safe():
    C._PRED_TALLY.clear()
    h = C.prediction_health()
    assert h['total'] == 0 and h['alert'] is False


# ═════════ 8. PDPA: mask ก่อนขึ้น snapshot (กติกาข้อ 2 ของโปรเจกต์) ═════════

def test_snapshot_masks_name_hn_and_drops_procnote():
    """snapshot ที่จะขึ้น cloud ต้องไม่มีชื่อเต็ม/HN เต็ม/free text จาก HIS
    (เขียนลงไฟล์ชั่วคราว + DB ปลอม — ดู _isolate_io ด้านบน)"""
    _fresh_state()
    _FAKE_DB.clear()
    assert 'orflow_test_' in P._SNAPSHOT_PATH, "ไฟล์เทสต์ไม่ได้ถูกแยกจากของจริง"
    st.session_state['_board_base_version'] = 0
    c = _case(name='สมชาย ใจดีมาก', hn='1234567',
              procnote='ข้อความอิสระจาก HIS ที่ห้ามขึ้น cloud',
              scrub_nurse='กนกวรรณ มีแก้ว')
    P._save_board_snapshot([c])
    import json
    with open(P._SNAPSHOT_PATH, encoding='utf-8') as f:
        saved = json.load(f)['cases'][0]
    assert 'procnote' not in saved
    assert saved['name'] != 'สมชาย ใจดีมาก'
    assert saved['hn'] != '1234567'
    assert saved['scrub_nurse'] != 'กนกวรรณ มีแก้ว'
    assert c['name'] == 'สมชาย ใจดีมาก'      # ของบนจอต้องไม่ถูกแก้ตาม


# ═════════ 9. 🎬 ธงสาธิตต้องรอด "ปิดเครื่องแล้วล็อกอินใหม่" ═════════
# มุคกี้แจ้ง 12 ส.ค. 2026: เปิดสาธิตไว้ → ปิดเครื่อง → ล็อกอินใหม่ แล้วปุ่มขึ้น
# "🎬 เปิดโหมดสาธิต" ทั้งที่เคสสาธิตยังอยู่บนบอร์ด · กดปุ่มนั้น = โหลดชุดจำลอง
# ใหม่ทับสิ่งที่ผู้ทรงเพิ่งกดเล่นไปทั้งหมด

def test_demo_flag_recovered_after_relogin():
    """session ใหม่ (ธงหาย) + บอร์ดกลางยังเป็นชุดสาธิต → ต้องกู้ธงกลับมาเอง"""
    _fresh_state()
    assert st.session_state.get('_or_demo') is None      # เหมือนเพิ่งล็อกอินใหม่
    restored = [_case(id='D1'), _case(id='D2')]          # _case มี _demo=True
    assert P._sync_demo_flag_from_board(restored, True) is True
    assert st.session_state['_or_demo'] is True


def test_demo_flag_not_set_on_production_instance():
    """ระบบจริงไม่มีปุ่มสาธิต — เคส 🧪 ทดสอบที่อัปโหลดไว้ต้องไม่ปลุกธงสาธิต"""
    _fresh_state()
    assert P._sync_demo_flag_from_board([_case()], False) is False
    assert not st.session_state.get('_or_demo')


def test_demo_flag_not_set_for_real_cases():
    """บอร์ดที่เป็นเคสจริงล้วน (ไม่มีธง _demo) ต้องไม่ถูกมองว่าเป็นชุดสาธิต"""
    _fresh_state()
    real = [_case(id='R1', _demo=False), _case(id='R2', _demo=False)]
    assert P._sync_demo_flag_from_board(real, True) is False
    assert not st.session_state.get('_or_demo')
    assert P._sync_demo_flag_from_board([], True) is False   # บอร์ดว่าง


def test_demo_flag_survives_walkin_case_added_during_demo():
    """แอป DEMO เพิ่มเคส walk-in ระหว่างสาธิตได้ (เคสที่พิมพ์เองไม่มีธง _demo)
    บอร์ดผสมแบบนี้ยังต้องนับเป็นชุดสาธิต ไม่งั้นล็อกอินใหม่แล้วธงหายอีก"""
    _fresh_state()
    mixed = [_case(id='D1'), _case(id='W1', _demo=False, name='เคสแทรก')]
    assert P._sync_demo_flag_from_board(mixed, True) is True
    assert st.session_state['_or_demo'] is True


def test_demo_flag_never_auto_turned_off():
    """ห้ามปิดธงอัตโนมัติ: การปิดสาธิตจะล้างบอร์ดกลางทิ้ง (clear_board_state)
    จอที่ดึงข้อมูลช้ากว่าจะพากันล้างบอร์ดของเครื่องอื่น — ปิดได้จากปุ่ม ⏹️ เท่านั้น"""
    _fresh_state()
    st.session_state['_or_demo'] = True
    for board in ([], [_case(_demo=False)], [_case()]):
        assert P._sync_demo_flag_from_board(board, True) is False   # ไม่ต้องเปิดซ้ำ
        assert st.session_state['_or_demo'] is True, "ธงถูกปิดอัตโนมัติ = อันตราย"


# ═════════════════════════════ runner ═════════════════════════════

def _run_all():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith('test_') and callable(f)]
    ok, fails = 0, []
    for name, fn in fns:
        try:
            fn()
            ok += 1
            print(f"  PASS  {name}")
        except AssertionError as ex:
            fails.append((name, f"assert ไม่ผ่าน: {ex}"))
            print(f"  FAIL  {name} : {ex}")
        except Exception as ex:
            fails.append((name, f"{type(ex).__name__}: {ex}"))
            print(f"  ERROR {name} : {type(ex).__name__}: {ex}")
    print("\n" + "=" * 62)
    print(f"ผ่าน {ok}/{len(fns)} รายการ")
    if fails:
        print(f"ไม่ผ่าน {len(fails)} รายการ:")
        for n, why in fails:
            print(f"  - {n}: {why}")
    print("=" * 62)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(_run_all())
