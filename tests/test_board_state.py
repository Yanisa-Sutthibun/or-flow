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


# ═════════ 10. 🎬 ชุดสาธิตค้างนาน = สร้างใหม่ (มุกกี้สั่ง 12 ส.ค. 2026) ═════════
# เคสสาธิตอิงเวลา "ตอนกดเปิด" ทิ้งค้างข้ามชั่วโมงแล้วเคสที่ยังผ่าอยู่จะเลยเวลา
# ทำนายไปไกล → บอร์ดแดงยกแถว ผู้ทรงที่เปิดทีหลังเห็นภาพที่ไม่ใช่ของจริง

def _ago(minutes):
    """เวลาบันทึกล่าสุดแบบ ISO ย้อนหลัง N นาที (รูปแบบเดียวกับ payload จริง)"""
    return (P._now() - timedelta(minutes=minutes)).isoformat()


def test_demo_board_refreshed_when_idle_too_long():
    _fresh_state()
    stale = _ago(P.DEMO_IDLE_RESET_MIN + 5)
    assert P._should_refresh_demo_board([_case()], True, stale, P._now()) is True


def test_demo_board_kept_while_someone_is_using_it():
    """เกณฑ์นับจาก 'การกดปุ่มครั้งล่าสุด' — ใครกำลังใช้อยู่ต้องไม่ถูกรีเซ็ตใส่หน้า"""
    _fresh_state()
    for idle in (0, 5, P.DEMO_IDLE_RESET_MIN - 1):
        assert P._should_refresh_demo_board(
            [_case()], True, _ago(idle), P._now()) is False, f"idle={idle}"


def test_demo_board_refresh_needs_demo_instance_and_demo_cases():
    """ระบบจริง / บอร์ดเคสจริง ห้ามถูกสร้างทับเด็ดขาด (ข้อมูลผู้ป่วยจริงหาย)"""
    _fresh_state()
    stale = _ago(P.DEMO_IDLE_RESET_MIN + 120)
    real = [_case(_demo=False)]
    assert P._should_refresh_demo_board([_case()], False, stale, P._now()) is False
    assert P._should_refresh_demo_board(real, True, stale, P._now()) is False
    assert P._should_refresh_demo_board([], True, stale, P._now()) is False


def test_demo_board_refresh_fails_safe_on_unreadable_time():
    """อ่านเวลาไม่ได้ = ไม่รู้ว่าค้างจริงไหม → ห้ามล้างของใคร"""
    _fresh_state()
    for bad in (None, '', 'เมื่อกี้', '2026-13-45T99:99', 12345):
        assert P._should_refresh_demo_board(
            [_case()], True, bad, P._now()) is False, f"saved_at={bad!r}"
        assert P._demo_board_idle_min(bad, P._now()) is None


def test_demo_idle_min_reads_the_format_the_app_actually_writes():
    """_save_board_snapshot เขียน saved_at = _now().isoformat() (เวลาไทย ไม่มี tzinfo)
    ต้องอ่านกลับมาเป็นจำนวนนาทีได้ตรง — ไม่ใช่ None แล้วไม่รีเซ็ตอะไรเลยตลอดกาล"""
    _fresh_state()
    _FAKE_DB.clear()
    P._save_board_snapshot([_case()])
    import json
    saved_at = json.loads(_FAKE_DB[P._now().date().isoformat()])['saved_at']
    idle = P._demo_board_idle_min(saved_at, P._now() + timedelta(minutes=90))
    assert idle is not None and 89 <= idle <= 91, (saved_at, idle)


def test_demo_idle_min_handles_timestamp_with_timezone():
    """payload ที่ติด timezone มา (บิลด์เก่า/เครื่องอื่น) ต้องเทียบกับ _now() แบบ
    ไม่มี tzinfo ได้ ไม่ใช่ TypeError แล้วเงียบจนบอร์ดไม่มีวันรีเซ็ต"""
    _fresh_state()
    now = P._now()
    assert now.tzinfo is None, "ข้อสมมุติของเทสต์นี้เปลี่ยนไปแล้ว — _now() ไม่ naive"
    from datetime import timezone
    aware = (now - timedelta(minutes=90)).replace(
        tzinfo=timezone(timedelta(hours=7))).isoformat()
    idle = P._demo_board_idle_min(aware, now)
    assert idle is not None and 89 <= idle <= 91, idle


def test_demo_refresh_overwrites_finished_cases_on_central_board():
    """ชุดสาธิตใหม่ต้องเขียนทับของเก่าได้จริง แม้ของเก่าจะเดินไปถึง 'จำหน่าย' แล้ว
    (ด่าน CR-3 ห้ามสถานะถอยหลังต้องไม่บล็อกการสร้างชุดใหม่ทั้งกระดาน —
    เส้นทางนี้ไม่เข้า merge ราย-เคส เพราะ base_version เพิ่ง sync จากตอนโหลด)
    เคสสาธิตจริงไม่มีคีย์ id → คีย์ merge = hn|หัตถการ|เวลานัด"""
    _fresh_state()
    _FAKE_DB.clear()
    old = _case(id=None, status='discharged', actual_duration_min=88)
    old.pop('id')
    P._save_board_snapshot([old])                    # ชุดเก่าอยู่บนบอร์ดกลาง

    _fresh_state()                                   # ผู้ทรงคนใหม่เปิดแอป = session ใหม่
    restored = P._load_board_snapshot()
    assert restored and restored[0]['status'] == 'discharged'
    assert P._should_refresh_demo_board(
        restored, True, _ago(P.DEMO_IDLE_RESET_MIN + 30), P._now()) is True

    new = _case(id=None, status='not_arrived')       # ชุดใหม่ = ทุกเคสกลับไปตั้งต้น
    new.pop('id')
    st.session_state['_board_dirty_ids'] = set()
    P._save_board_snapshot([new])

    import json
    saved = json.loads(_FAKE_DB[P._now().date().isoformat()])['cases']
    assert len(saved) == 1, saved
    assert saved[0]['status'] == 'not_arrived', "ชุดสาธิตใหม่ถูกด่าน CR-3 บล็อก"


# ═══ 11. 🛡️ ถามก่อนสลับสวิตช์สาธิต ถ้ามีเครื่องอื่นออนไลน์ (มุกกี้สั่ง 12 ส.ค. 2026) ═══
# สวิตช์นี้เขียนทับ "บอร์ดกลาง" ที่ทุกจอใช้ร่วมกัน ผู้ทรงที่กดเล่นอยู่คนละเครื่อง
# จะโดนล้าง/รีเซ็ตใส่หน้าโดยไม่รู้ตัว → ไม่มีใครออนไลน์ = กดผ่านเลย มีคน = ถามก่อน

import presence as PR                                # noqa: E402


def _fake_online(*counts_by_kind):
    """แทน presence.counts() ด้วยยอดปลอม (รวมเครื่องที่ถามเองด้วยเสมอ)"""
    PR.counts = lambda: dict(counts_by_kind)


def test_others_online_does_not_count_myself():
    _fresh_state()
    _fake_online(('staff', 3), ('room', 2))
    assert PR.others_online() == 4


def test_others_online_is_zero_when_alone_or_unreadable():
    """อ่าน heartbeat ไม่ได้ = ถือว่าไม่มีใคร (ห้ามขวางการใช้งาน) และห้ามติดลบ"""
    _fresh_state()
    _fake_online(('staff', 1))
    assert PR.others_online() == 0
    _fake_online()
    assert PR.others_online() == 0


def test_demo_switch_goes_through_when_nobody_else_online():
    """อยู่คนเดียว: กดแล้วต้องทำงานทันที ไม่มีขั้นตอนเพิ่ม"""
    _fresh_state()
    _fake_online(('staff', 1))
    assert P._demo_switch_pressed('on', False) is True
    assert P._demo_switch_pressed('off', True) is False
    assert st.session_state.get('_demo_switch_confirm') is None


def test_demo_switch_asks_first_when_others_online():
    """มีเครื่องอื่นอยู่: ยังไม่สลับ แต่ตั้งธงขอยืนยัน + จำจำนวนเครื่องไว้แสดง"""
    _fresh_state()
    _fake_online(('staff', 2), ('room', 1))
    assert P._demo_switch_pressed('off', True) is True, "ปิดไปแล้วทั้งที่ยังไม่ยืนยัน"
    assert st.session_state['_demo_switch_confirm'] == 'off'
    assert st.session_state['_demo_switch_others'] == 2

    _fresh_state()
    _fake_online(('staff', 2))
    assert P._demo_switch_pressed('on', False) is False
    assert st.session_state['_demo_switch_confirm'] == 'on'


def _buttons(*pressed):
    """คุมว่าปุ่มคีย์ไหนถูกกดในรอบนี้ — st_stub ตั้งต้นให้ทุกปุ่มเป็น 'ถูกกด' เสมอ
    ซึ่งใช้ทดสอบกล่องยืนยันไม่ได้ (ต้องแยกให้ออกระหว่างกดยืนยัน/กดยกเลิก/ไม่กดเลย)"""
    st.button = lambda *_a, **_k: _k.get('key') in pressed


def test_demo_switch_confirm_box_states_the_consequence():
    """กล่องยืนยันต้องบอกจำนวนเครื่อง + ผลที่จะเกิดกับ 'ทุกจอ' ไม่ใช่แค่จอตัวเอง"""
    _fresh_state()
    _buttons()                                   # ยังไม่กดปุ่มไหน
    st.session_state['_demo_switch_others'] = 3
    assert P._render_demo_switch_confirm('off', True) is True, "สลับทั้งที่ยังไม่ยืนยัน"
    _warn = ' '.join(st.calls['warning'])
    assert '3' in _warn and 'ทุกจอ' in _warn, _warn

    _fresh_state()
    _buttons()
    st.session_state['_demo_switch_others'] = 2
    P._render_demo_switch_confirm('on', False)
    assert 'ทับบอร์ดของทุกจอ' in ' '.join(st.calls['warning'])


def test_demo_switch_confirm_yes_applies_the_action():
    _fresh_state()
    _buttons('orboard_demo_confirm_yes')
    st.session_state['_demo_switch_confirm'] = 'off'
    st.session_state['_demo_switch_others'] = 2
    assert P._render_demo_switch_confirm('off', True) is False   # ปิดจริง
    assert st.session_state.get('_demo_switch_confirm') is None, "ธงยืนยันค้าง"
    assert st.session_state.get('_demo_switch_others') is None

    _fresh_state()
    _buttons('orboard_demo_confirm_yes')
    assert P._render_demo_switch_confirm('on', False) is True     # เปิดจริง


def test_demo_switch_confirm_cancel_changes_nothing():
    """กดยกเลิก = สถานะเดิมทุกอย่าง + ธงต้องถูกล้าง ไม่งั้นกล่องจะค้างถามซ้ำ"""
    _fresh_state()
    _buttons('orboard_demo_confirm_no')
    st.session_state['_demo_switch_confirm'] = 'off'
    st.session_state['_demo_switch_others'] = 2
    assert P._render_demo_switch_confirm('off', True) is True
    assert st.session_state.get('_demo_switch_confirm') is None
    assert st.session_state.get('_demo_switch_others') is None


def test_demo_switch_survives_broken_presence():
    """presence ใช้ไม่ได้ (DB ล่ม) = ต้องกดได้ตามปกติ ไม่ใช่ค้างหรือ error"""
    _fresh_state()

    def _boom():
        raise RuntimeError("presence ล่ม")

    PR.counts = _boom
    assert P._demo_switch_others_online() == 0
    assert P._demo_switch_pressed('on', False) is True


# ═══ 12. 🎭 PDPA: แอปสาธิตห้ามมีชื่อแพทย์จริง (มุคกี้พบ 12 ส.ค. 2026) ═══
# ช่อง "แพทย์ผ่าตัด" ในฟอร์มเพิ่มเคสเคยดึง DISTINCT surgeon_name จากตาราง cases
# ซึ่งบนแอปสาธิตคือ schema demo ที่มีชื่อแพทย์จริงปนอยู่ → ชื่อจริงโผล่ให้คนนอกเห็น
# กติกาข้อ 6 ของโปรเจกต์: ผู้ทรงคุณวุฒิ/คนนอกได้สิทธิ์ DEMO เท่านั้น

def _as_demo_instance(on=True):
    st.secrets = {'instance_mode': 'demo'} if on else {}


def test_demo_surgeon_list_comes_only_from_demo_pool():
    _fresh_state()
    from demo_cases_data import DEMO_POOL
    _ok = {str(d.get('surgeon') or '').strip() for d in DEMO_POOL}
    got = P._demo_surgeons_by_specialty()
    assert got, "รายชื่อแพทย์สาธิตว่างเปล่า"
    for _spec, _names in got.items():
        for _n in _names:
            assert _n in _ok, f"ชื่อ '{_n}' ไม่ได้มาจากชุดเคสสาธิต"


def test_demo_instance_never_queries_real_case_table():
    """บนแอปสาธิต ต้องไม่แตะตาราง cases เลย — _isolate_io ทำให้ get_conn ระเบิด
    ถ้าเผลอเปิด connection เทสต์นี้จึงจับได้ทันทีว่ามีเส้นทางหลุดไปอ่านของจริง"""
    _fresh_state()
    _as_demo_instance(True)
    try:
        got = P._surgeons_by_specialty()
    finally:
        _as_demo_instance(False)
    assert got == P._demo_surgeons_by_specialty(), "แอปสาธิตไม่ได้ใช้รายชื่อสมมุติ"


def test_demo_instance_refuses_to_unmask_staff_codes():
    """ด่านที่สอง: ต่อให้มีไฟล์ staff_mapping.csv วางอยู่ข้างแอป (เช่นเปิด demo_app.py
    บนเครื่อง รพ.) ระบบสาธิตก็ต้องไม่แปลง SURG_xxx กลับเป็นชื่อจริง
    ปิดที่ _load_mapping จุดเดียว = ปิดครบทุกทางที่แสดงผล"""
    _fresh_state()
    import staff_unmask as SU
    _keep = SU._cache
    try:
        _as_demo_instance(True)
        SU._cache = None
        assert SU._load_mapping() == {}
        assert SU.is_available() is False
        assert SU.unmask('SURG_003') == 'SURG_003', "ระบบสาธิตถอดรหัสเป็นชื่อจริง"
        assert SU.unmask_multi('SURG_003, SURG_011') == 'SURG_003, SURG_011'
    finally:
        _as_demo_instance(False)
        SU._cache = _keep


def test_demo_instance_does_not_download_staff_map():
    """ด่านแรก: แอปสาธิตต้องไม่ดึงทะเบียนชื่อจริงจากฐานข้อมูลมาเขียนไฟล์ตอนบูต
    (_isolate_io ทำให้ get_conn ระเบิด ถ้าเผลอไปดึงจริงเทสต์นี้จะจับได้)"""
    _fresh_state()
    import staff_map_sync as SMS
    try:
        _as_demo_instance(True)
        assert SMS.ensure_staff_mapping() == 'demo-skip'
    finally:
        _as_demo_instance(False)


# 🎭 ชื่อแพทย์ในชุดสาธิต ต้องเป็นชื่อตัวละครในวรรณคดี/แบบเรียนภาษาไทยเท่านั้น
# (มุคกี้เลือกเอง 12 ส.ค. 2026): คนไทยทุกคนจำได้ทันทีว่าเป็นชื่อสมมุติ ไม่ใช่คนจริง
# ⛔ รายชื่อนี้คือด่านสุดท้ายกันชื่อจริงหลุดเข้า DEMO_POOL — ถ้าจะเพิ่มแพทย์สาธิต
#    ต้องมาเพิ่มชื่อที่นี่ด้วย จะได้มีคนตรวจซ้ำเสมอว่าไม่ใช่ชื่อคนจริง
_DEMO_SURGEON_WHITELIST = {
    'มานะ รักเผ่าไทย', 'มานี รักเผ่าไทย', 'ปิติ พิทักษ์ถิ่น',
    'ชูใจ เลิศล้ำ', 'วีระ ประสงค์สุข', 'สุดสาคร เกาะแก้ว',
    'ก้านกล้วย คชสาร', 'โกมินทร์ กุมาร', 'พิมพิลาลัย วันทอง',
    'เจ้าหญิง พิกุลทอง', 'ฟ้าลั่น มะม่วง',
}


def test_demo_surgeon_names_are_fictional_only():
    """กันวันหลังมีคนเผลอเอาชื่อแพทย์จริงใส่ DEMO_POOL แล้วไม่มีอะไรเตือน"""
    _fresh_state()
    for _spec, _names in P._demo_surgeons_by_specialty().items():
        for _n in _names:
            assert _n in _DEMO_SURGEON_WHITELIST, f"ชื่อ '{_n}' ไม่อยู่ในรายชื่อสมมุติที่อนุมัติ"


def test_demo_surgeon_names_are_unique_per_code():
    """แพทย์สาธิตแต่ละรหัส SURG_ ต้องมีชื่อไม่ซ้ำกัน — คนละรหัสคือคนละคน
    (คนละประวัติ คนละค่าทำนายของ AI) ถ้าชื่อซ้ำ บอร์ดจะดูเหมือนหมอคนเดียวอยู่ 2 ห้อง"""
    _fresh_state()
    from demo_cases_data import DEMO_POOL
    by_code = {}
    for d in DEMO_POOL:
        _c, _n = d.get('surgeon_code'), str(d.get('surgeon') or '').strip()
        if _c:
            assert by_code.setdefault(_c, _n) == _n, f"รหัส {_c} มีหลายชื่อ"
    _names = list(by_code.values())
    assert len(set(_names)) == len(_names), "มีชื่อแพทย์สาธิตซ้ำกันข้ามรหัส"


# ═══════════ 8. 🔔 ระบบคิวถัดไป/กระดิ่ง (call_queue · rev.3 13 ส.ค. 2026) ═══════════
# จอรับ-ส่ง: แถบบอกเวลา "ตามผู้ป่วยมารอ" (AI ล้วน ไม่มีปุ่ม/ไม่มีแก้มือ) ·
# จอห้อง: กระดิ่ง 🔔 = เรียกมารอได้เลย (สัญญาณขึ้นจอรับ-ส่ง) — เทสต์ logic ล้วน

import call_queue as Q                             # noqa: E402

_T0 = datetime(2026, 8, 13, 10, 0)                 # "ตอนนี้" คงที่ของชุดเทสต์นี้


def _call_cases():
    """ห้อง 92: เคสกำลังผ่า (เข้า 09:00 ทำนาย 60) + คิว 2 ยังไม่มา + คิว 3 ยังไม่มา"""
    cur = _case(id='CUR', room=92, status='in_or', ororder=1,
                time_entered_or=datetime(2026, 8, 13, 9, 0), effective_min=60)
    n2 = _case(id='N2', room=92, status='not_arrived', ororder=2,
               effective_min=45)
    n3 = _case(id='N3', room=92, status='not_arrived', ororder=3,
               effective_min=30)
    return [cur, n2, n3]


def test_call_next_case_picks_smallest_order():
    """คิวถัดไปของห้อง = เคส 'ยังไม่มา' ที่เลขคิวเล็กสุด (ไม่ใช่เคสกำลังผ่า)"""
    cases = _call_cases()
    nxt = Q.next_call_case(cases, 92)
    assert nxt is not None and nxt['id'] == 'N2'


def test_call_suggested_matches_board_formula():
    """สูตรเดียวกับบรรทัด 'เรียกคิวถัดไป ~' บนบอร์ด: เข้า 09:00 + 60 นาที
    + เตรียมห้อง 15 - เผื่อเดินทาง 30 = 09:45"""
    cases = _call_cases()
    dt = Q.suggested_call_dt(cases, cases[1], _T0, {})
    assert dt == datetime(2026, 8, 13, 9, 45), dt


def test_call_suggested_chains_cases_ahead():
    """คิว 3 ต้องรอคิว 2 ผ่าเสร็จก่อน: ออก 10:00 → (เตรียม 15 + คิว 2 ใช้ 45)
    → ออก 11:00 → +15 -30 = เรียก 10:45"""
    cases = _call_cases()
    dt = Q.suggested_call_dt(cases, cases[2], _T0, {})
    assert dt == datetime(2026, 8, 13, 10, 45), dt


def test_call_room_free_suggests_now():
    """ห้องว่างและไม่มีเคสคั่น = เรียกได้เลย (คืนเวลาปัจจุบัน)"""
    n = _case(id='N1', room=93, status='not_arrived', ororder=1)
    assert Q.suggested_call_dt([n], n, _T0, {}) == _T0


def test_call_skips_unqueued_tf_manual_emergency():
    """เคสไม่ได้จัดคิว (TF / Manual 99 / ฉุกเฉิน) ไม่ถูกเลือกเป็นคิวถัดไป —
    ตาม wireframe: แถวเรียกคิวว่าง"""
    tf = _case(id='TF', room=92, status='not_arrived', ororder=2, is_tf=True)
    manual = _case(id='M', room=92, status='not_arrived', ororder=99)
    emer = _case(id='E', room=92, status='not_arrived', ororder=3,
                 is_emergency=True)
    assert Q.next_call_case([tf, manual, emer], 92) is None


def test_call_distrusts_duplicate_orders():
    """เลขคิวซ้ำในห้อง (HIS ยังไม่จัดคิวจริง) = ไม่โชว์เรียกคิวทั้งห้อง —
    กติกาเดียวกับป้าย 🔒 ล็อคคิว"""
    a = _case(id='A', room=92, status='not_arrived', ororder=1)
    b = _case(id='B', room=92, status='not_arrived', ororder=1)
    assert Q.next_call_case([a, b], 92) is None


def test_call_map_returns_case_and_ai_time():
    """next_call_map = {ห้อง: (เคสคิวถัดไป, เวลาที่ AI แนะนำ)} — rev.3 ไม่มี
    override เวลาบนแถบเป็นค่า AI ล้วน ขยับตามสถานการณ์เอง"""
    cases = _call_cases()
    room92 = Q.next_call_map(cases, _T0, {})[92]
    assert room92[0]['id'] == 'N2'
    assert room92[1] == datetime(2026, 8, 13, 9, 45)


def test_apply_call_once_only():
    """กดเรียกซ้ำ (สองจอกดพร้อมกัน) ครั้งที่สองต้องไม่ทับเวลาแรก"""
    c = _case(id='N2', status='not_arrived')
    assert Q.apply_call(c, _T0, 'room:92', planned_hhmm='09:45')
    assert c['call_time'] == _T0 and c['call_from'] == 'room:92'
    assert c['call_planned_hhmm'] == '09:45'
    assert not Q.apply_call(c, _T0 + timedelta(minutes=5), 'board')
    assert c['call_time'] == _T0          # เวลาแรกอยู่ครบ


def test_apply_undo_call_sets_flag():
    """↩️ ยกเลิกเรียก: ล้างเวลา + ตั้งธง call_undone (กัน merge ดึงคืน)"""
    c = _case(id='N2', status='not_arrived')
    Q.apply_call(c, _T0, 'board')
    assert Q.apply_undo_call(c)
    assert c['call_time'] is None and c['call_undone'] is True
    assert not Q.apply_undo_call(c)       # ไม่มีอะไรให้ยกเลิกแล้ว


def test_merge_keeps_call_from_other_machine():
    """เครื่องที่ถือ snapshot เก่า (ไม่เห็นการเรียก) เซฟทับ — เวลาเรียกที่จอห้อง
    กดไว้ต้องไม่หาย (การเรียกเดินหน้าอย่างเดียว เหมือนขั้นของเคส)"""
    mine = _case(id='N2', status='not_arrived')
    theirs = _case(id='N2', status='not_arrived',
                   call_time={'__dt__': '2026-08-13T10:05:00'},
                   call_from='room:92', call_planned_hhmm='09:45')
    out, blocked = P._merge_case_no_regress(mine, theirs)
    assert not blocked
    assert out['call_time'] == {'__dt__': '2026-08-13T10:05:00'}
    assert out['call_from'] == 'room:92'


def test_merge_respects_intentional_call_undo():
    """แต่ถ้าเครื่องนี้เพิ่งกด ↩️ ยกเลิกการเรียกเอง (call_undone) —
    merge ต้องไม่ดึงเวลาเรียกจากเครื่องอื่นกลับมา (เจตนาคนชนะ)"""
    mine = _case(id='N2', status='not_arrived', call_time=None,
                 call_undone=True)
    theirs = _case(id='N2', status='not_arrived',
                   call_time={'__dt__': '2026-08-13T10:05:00'},
                   call_from='room:92')
    out, _ = P._merge_case_no_regress(mine, theirs)
    assert out.get('call_time') is None


def test_merge_call_forward_survives_phase_merge():
    """เครื่องเก่าแก้เวลาผ่าตัดของเคสที่เครื่องอื่นทั้งรับเข้า+เคยเรียกไว้ —
    ทั้งขั้นของเคส (holding_pre) และเวลาเรียก ต้องคงของล่าสุดไว้คู่กัน"""
    mine = _case(id='N2', status='not_arrived', user_override_min=50)
    theirs = _case(id='N2', status='holding_pre',
                   time_arrived_holding={'__dt__': '2026-08-13T10:20:00'},
                   call_time={'__dt__': '2026-08-13T10:05:00'},
                   call_from='board')
    out, blocked = P._merge_case_no_regress(mine, theirs)
    assert blocked and out['status'] == 'holding_pre'
    assert out['user_override_min'] == 50          # สิ่งที่เราแก้ยังอยู่
    assert out['call_time'] == {'__dt__': '2026-08-13T10:05:00'}


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
