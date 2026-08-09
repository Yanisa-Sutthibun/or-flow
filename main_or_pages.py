"""
Main OR — OR Board + Statistics Pages
"""
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, timezone
import json

# 🕐 เวลามาตรฐานกรุงเทพ — กันเพี้ยนเมื่อ deploy บน server/cloud ต่าง timezone
# (board เดิมใช้ datetime.now() = เวลา server → บน cloud UTC จะคลาด 7 ชม.)
_BKK = timezone(timedelta(hours=7))


def _now():
    """เวลาปัจจุบันโซนกรุงเทพ (naive) — ใช้แทน datetime.now() ทุกที่บนบอร์ด"""
    return datetime.now(_BKK).replace(tzinfo=None)


# ============================================================================
# ⚡ Fragment (perf fix ก.ค. 2026) — st.fragment มีตั้งแต่ streamlit 1.37
# ครอบบอร์ดทั้งก้อนไว้ใน fragment เดียว:
#   • กดปุ่มบนบอร์ด → rerun เฉพาะก้อนบอร์ด (เดิม: rerun ทั้งแอป ×2 ต่อคลิก)
#   • run_every=30 → ดึงบอร์ดกลางแทน streamlit_autorefresh (ที่ rerun ทั้งแอป)
# streamlit เก่า (<1.37): decorator เป็น no-op → พฤติกรรมเดิมทุกอย่าง (มี fallback)
# ============================================================================
from main_or_core import rerun_board as _rerun_board

_HAS_FRAGMENT = hasattr(st, 'fragment')
if _HAS_FRAGMENT:
    _fragment = st.fragment
else:
    def _fragment(*_a, **_k):
        """no-op decorator — streamlit เก่าไม่มี st.fragment"""
        if _a and callable(_a[0]):
            return _a[0]

        def _deco(fn):
            return fn
        return _deco


# ============================================================================
# 💾 Snapshot บอร์ดลงไฟล์ — กันข้อมูลหายเมื่อกด F5 / รีสตาร์ทแอพ
# (ก่อนต่อ Supabase: board อยู่ใน session_state ซึ่งหายเมื่อ reload จริง)
# เก็บเป็น JSON ในเครื่อง 1 ไฟล์/วัน · fail-safe: พังก็ไม่กระทบบอร์ด (try/except)
# ============================================================================
import os as _os
from datetime import date as _date

_SNAPSHOT_PATH = _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'data', '_board_snapshot.json')


def _ser(v):
    """แปลงค่าใน case ให้เป็น JSON ได้ (datetime/date → marker)
    + รองรับ numpy scalar (.item()) ที่อาจหลุดมาจาก pandas/โมเดล"""
    if isinstance(v, datetime):
        return {'__dt__': v.isoformat()}
    if isinstance(v, _date):
        return {'__d__': v.isoformat()}
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if hasattr(v, 'item'):  # numpy.int64/float64 → Python native
        try:
            return v.item()
        except Exception:
            return str(v)
    return v


def _deser(v):
    """แปลง marker กลับเป็น datetime/date"""
    if isinstance(v, dict) and '__dt__' in v:
        try:
            return datetime.fromisoformat(v['__dt__'])
        except (ValueError, TypeError):
            return None
    if isinstance(v, dict) and '__d__' in v:
        try:
            return _date.fromisoformat(v['__d__'])
        except (ValueError, TypeError):
            return None
    return v


def _board_case_key(d):
    """คีย์ระบุเคสข้ามเครื่อง/ข้าม payload (ใช้ตอน merge) — id ก่อน ไม่มีค่อย composite"""
    cid = d.get('id')
    if cid not in (None, ''):
        return f"id:{cid}"
    return (f"k:{d.get('hn','')}|{d.get('procedure','')}|"
            f"{d.get('sched_hour','')}:{d.get('sched_min','')}")


def _mark_board_dirty(case=None):
    """ทำเครื่องหมายว่า 'เครื่องนี้เพิ่งแก้บอร์ดจริง' → ค่อยเซฟ + กัน pull ทับ (CR-2)
    เก็บ id เคสที่แก้ไว้ใน _board_dirty_ids เพื่อ merge ราย-เคสตอนเซฟ"""
    try:
        st.session_state['_board_dirty'] = True
        ids = st.session_state.get('_board_dirty_ids')
        if not isinstance(ids, set):
            ids = set()
        if case is not None and case.get('id') not in (None, ''):
            ids.add(case.get('id'))
        st.session_state['_board_dirty_ids'] = ids
    except Exception:
        pass


def _mask_nurse_name(name):
    """🔒 mask ชื่อพยาบาลก่อนขึ้น cloud → 'ชื่อต้น + อักษรแรกนามสกุล.'
    เช่น 'กนกวรรณ มีแก้ว' -> 'กนกวรรณ ม.' (เผื่อข้อมูลเก่ามียศติดมา ตัดยศออกก่อน)"""
    import re as _re
    s = str(name or '').strip()
    if not s:
        return s
    s = _re.sub(r'^ว่าที่\s*', '', s)   # ตัด 'ว่าที่' นำหน้ายศ
    for t in ('นางสาว', 'นาง', 'นาย', 'ด.ช.', 'ด.ญ.', 'น.ส.'):
        if s.startswith(t):
            s = s[len(t):]
            break
    else:
        m = _re.match(r'^((?:[ก-ฮ]{1,2}\.)+)', s)   # ยศตำรวจ เช่น พ.ต.ท. จ.ส.ต.
        if m:
            s = s[m.end():]
    s = _re.sub(r'^(หญิง|ชาย)\s*', '', s).strip()
    parts = s.split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1][0]}."
    return parts[0] if parts else s


def _toast_ok(msg="อัปเดตแล้ว ✓"):
    """🎨 demo (2 ส.ค. 2026): ตอบรับทันทีทุกปุ่ม (Doherty Threshold) —
    production เงียบตามเดิม รอผลประเมินผู้ทรงก่อนค่อยยกไป
    🐛 3 ส.ค. 2026: st.toast ตรง ๆ ถูก rerun_board() บรรทัดถัดไปกลืนทุกครั้ง
    (rerun ทิ้ง output ของรอบปัจจุบัน) → ฝากข้อความใน session แล้วให้
    _flush_toast() โชว์ตอนต้นรอบถัดไปแทน — ตายังเห็นเป็น 'ทันที' เหมือนเดิม
    🔊 9 ส.ค. 2026 (มุคกี้สั่ง): เสียง "กดสำเร็จ" ผูกกับจุดนี้ด้วย — ต่างจาก toast
    ข้อความ (demo เท่านั้น) เสียงเล่นทุก instance ทั้ง demo และ production"""
    _queue_sound('ok')
    try:
        if str(st.secrets.get('instance_mode', '')).lower() == 'demo':
            st.session_state['_pending_toast'] = msg
    except Exception:
        pass


def _flush_toast():
    """โชว์ toast ที่ฝากไว้ก่อน rerun — เรียกที่ต้นทุก fragment ที่มีปุ่ม
    🐛 3 ส.ค. 2026: st.toast รุ่นใหม่กลายเป็นการ์ดมุมบน+ปุ่มปิด (ดูเป็น popup)
    → ทำ snackbar เองด้วย CSS: ป้ายเล็กมุมล่างขวา เด้งขึ้น ~3 วิ จางหายเอง"""
    _msg = st.session_state.pop('_pending_toast', None)
    if _msg:
        try:
            import html as _html
            st.markdown(
                f'<div class="or-toast">{_html.escape(str(_msg))}</div>'
                '<style>'
                '.or-toast{position:fixed;bottom:84px;right:26px;z-index:99999;'
                'background:#1f2937;color:#fff;padding:11px 24px;'
                'border-radius:10px;font-size:18px;font-weight:600;'
                'box-shadow:0 4px 16px rgba(0,0,0,.28);pointer-events:none;'
                'animation:orTIn .25s ease, orTOut .5s ease 2.8s forwards;}'
                '@keyframes orTIn{from{opacity:0;transform:translateY(16px)}'
                'to{opacity:1;transform:none}}'
                '@keyframes orTOut{to{opacity:0;transform:translateY(10px);'
                'visibility:hidden}}'
                '</style>',
                unsafe_allow_html=True)
        except Exception:
            pass


def _toast_err_sound():
    """🔊 9 ส.ค. 2026 (มุคกี้สั่ง): เสียง "กดไม่สำเร็จ" — ผูกเฉพาะจุดที่มี
    st.warning ติดปุ่มบนบอร์ดอยู่แล้ว (ห้องปิด/ห้องไม่ว่าง) ไม่แตะ silent-fail
    ของ background save (research_log/override_log ฯลฯ) ซึ่งตั้งใจให้เงียบ
    เล่นทันที (ไม่ queue) เพราะจุดพวกนี้ return ก่อนถึง _rerun_board() —
    ไม่มีรอบถัดไปให้ _flush_sound() มาเล่นแทน"""
    _play_sound_now('err')


def _queue_sound(kind):
    """ฝากคิวเสียงไว้เล่นตอนต้นรอบถัดไป (เหมือน _pending_toast) — เล่นทุก
    instance ไม่ผูกกับ instance_mode ต่างจาก toast ข้อความ"""
    st.session_state['_pending_sound'] = kind


def _flush_sound():
    """เล่นเสียงที่ฝากไว้ก่อน rerun (คู่กับ _flush_toast) — เรียกที่ต้นทุก
    fragment ที่มีปุ่ม"""
    _kind = st.session_state.pop('_pending_sound', None)
    if _kind in ('ok', 'err'):
        _play_sound_now(_kind)


def _play_sound_now(kind):
    """เล่นเสียงจริงผ่าน Web Audio (ไม่ใช้ไฟล์เสียง) — ok = ไล่ขึ้น 2 โน้ตนุ่ม ·
    err = ไล่ลง 2 โน้ตทึบกว่า สไตล์คลาสสิก ตั้งใจให้สั้น/เบากว่าเสียง alarm
    เครื่องมอนิเตอร์ในห้องผ่าตัดจริง (ซึ่งมักเป็นบี๊บรัว 3 ครั้ง) กันสับสน"""
    _tones = [660, 880] if kind == 'ok' else [392, 261.6]
    _wave = 'sine' if kind == 'ok' else 'triangle'
    _step = 0.09 if kind == 'ok' else 0.13
    try:
        components.html(
            "<script>try{"
            "var ctx=new (window.AudioContext||window.webkitAudioContext)();"
            f"var now=ctx.currentTime,tones={_tones},wave='{_wave}',step={_step};"
            "tones.forEach(function(f,i){"
            "var o=ctx.createOscillator(),g=ctx.createGain();"
            "o.type=wave;o.frequency.value=f;"
            "g.gain.setValueAtTime(0, now+i*step);"
            "g.gain.linearRampToValueAtTime(0.18, now+i*step+0.01);"
            "g.gain.exponentialRampToValueAtTime(0.001, now+i*step+0.2);"
            "o.connect(g);g.connect(ctx.destination);"
            "o.start(now+i*step);o.stop(now+i*step+0.24);});"
            "}catch(e){}</script>",
            height=0)
    except Exception:
        pass


def apply_finish(cases, idx, R, dest):
    """🏁 state machine กลาง: ผ่าเสร็จ → ห้องรับ-ส่ง/พักฟื้น (สกัดจาก _do_finish
    2 ส.ค. 2026) — จอบอร์ดและจอห้องแบบโฟกัส (demo) เรียกเส้นทางเดียวกัน
    ไม่ก๊อบ logic ซ้ำ · คืน True เมื่อเปลี่ยนสถานะสำเร็จ (ผู้เรียกจัดการ rerun เอง)"""
    if cases[idx].get('status') != 'in_or':
        return False  # กันกดรัว (สถานะแสดงผลอาจเป็น 'เกินเวลา' แต่ค่าจริงคือ in_or)
    now = _now()
    cases[idx]['time_exited_or'] = now
    if cases[idx].get('time_entered_or'):
        _dur = (now - cases[idx]['time_entered_or']).total_seconds() / 60
        # กันเวลาติดลบ (เผื่อ clock เครื่องเพี้ยน) — clamp ขั้นต่ำ 1 นาที
        cases[idx]['actual_duration_min'] = max(int(_dur), 1)
    cases[idx]['status'] = 'recovery' if dest == 'ห้องพักฟื้น' else 'holding_post'
    _rk = R if R else 1
    st.session_state.or_rooms.setdefault(_rk, {}).update(
        {'status': 'ว่าง', 'current_case': None, 'start_time': None})
    st.session_state.statistics['completed_cases'] += 1
    record = {
        'timestamp': now.isoformat(),
        'case_id': cases[idx].get('id'),
        'procedure': cases[idx].get('procedure'),
        'surgeon': cases[idx].get('surgeon'),
        'division': cases[idx].get('division', '75'),
        'age': cases[idx].get('age'),
        'op_hour': cases[idx].get('op_hour'),
        'scrub': cases[idx].get('scrub_nurse', ''),
        'circ': cases[idx].get('circ_nurse', ''),
        'ai_predicted_min': cases[idx].get('ai_predicted_min', cases[idx].get('predicted_min')),
        'user_override_min': cases[idx].get('user_override_min'),
        'actual_duration_min': cases[idx].get('actual_duration_min'),
        'wait_min': cases[idx].get('wait_min', 0),
        'room': R if R else 1,
    }
    st.session_state.statistics['case_history'].append(record)
    # 🧪 เคส Demo ไม่บันทึกลงไฟล์สถิติสะสม — กันข้อมูลทดลองปนผลวิจัย
    if not cases[idx].get('_demo'):
        try:
            from main_or_core import append_case_history
            append_case_history(record)
        except Exception as ex:
            st.warning(f"บันทึก history ไม่สำเร็จ: {ex}")
    # เติมเวลาจริงเข้า override_log (ถ้าเคสนี้เคยถูกแก้เวลา) — เทียบ คน vs AI
    try:
        from main_or_db import complete_override
        complete_override(cases[idx], cases[idx].get('actual_duration_min'))
    except Exception as _ex:
        print(f"[override_log] complete_override ล้มเหลว: {_ex}")
    # 🕶️ shadow: thesis_ML_v2 ทำนายเทียบเงียบ ๆ (fail-safe ในตัว · demo ข้ามเอง)
    try:
        from shadow_v2 import log_shadow
        log_shadow(cases[idx], cases[idx].get('actual_duration_min'))
    except Exception as _sx:
        print(f"[shadow_v2] ข้าม: {_sx}")
    try:    # 📊 ตารางวิจัยถาวร — AI vs actual + override + ปลายทางออก
        from research_log import log_case_state
        log_case_state(cases[idx])
    except Exception as _rx:
        print(f"[research_log] ข้าม: {_rx}")
    _mark_board_dirty(cases[idx])   # CR-2
    return True


def apply_undo_finish(cases, idx):
    """↩️ state machine กลาง: ย้อนผลการกดเสร็จ (holding_post/recovery → in_or)
    สกัดจาก _do_undo (2 ส.ค. 2026) — บอร์ดและจอโฟกัส (demo) ใช้เส้นทางเดียวกัน
    ครบทุก side effect: ห้อง/ตัวนับ/history/override_log/research upsert"""
    c = cases[idx]
    if c.get('status') not in ('holding_post', 'recovery'):
        return False
    c['status'] = 'in_or'
    c['time_exited_or'] = None
    c['actual_duration_min'] = None
    st.session_state.statistics['completed_cases'] = max(
        st.session_state.statistics['completed_cases'] - 1, 0)
    _rk = c.get('or_room_assigned') or 1
    st.session_state.or_rooms.setdefault(_rk, {}).update(
        {'status': 'กำลังผ่าตัด', 'current_case': c,
         'start_time': c.get('time_entered_or')})
    _hist = st.session_state.statistics.get('case_history', [])
    for _i in range(len(_hist) - 1, -1, -1):
        if (_hist[_i].get('case_id') == c.get('id')
                and _hist[_i].get('procedure') == c.get('procedure')):
            _hist.pop(_i)
            break
    # ลบแถวที่เพิ่งบันทึกออกจากไฟล์ CSV history ด้วย (สถิติ Top-N ไม่เพี้ยน)
    try:
        from main_or_core import remove_last_case_history
        remove_last_case_history(c.get('id'), c.get('procedure'))
    except Exception as _ex:
        print(f"[history] remove_last_case_history ล้มเหลว: {_ex}")
    # ล้างเวลาจริงใน override_log ด้วย — เคสกลับไปกำลังผ่า
    try:
        from main_or_db import reset_override_actual
        reset_override_actual(c)
    except Exception as _ex:
        print(f"[override_log] reset_override_actual ล้มเหลว: {_ex}")
    try:    # 📊 research upsert — สถานะ/เวลาย้อนกลับให้ตรงจริง
        from research_log import log_case_state
        log_case_state(c)
    except Exception as _rx:
        print(f"[research_log] ข้าม: {_rx}")
    _mark_board_dirty(c)
    return True


def _save_board_snapshot(cases):
    """บันทึกบอร์ดปัจจุบันลง DB กลาง + ไฟล์ local — ไม่ throw
    🔒 mask ชื่อ/HN **เสมอ ไม่มีข้อยกเว้น** (นโยบาย 11 มิ.ย. 2026 · มาตรา 3.6.4):
    ชื่อ = คำนำหน้า+ชื่อต้น+นามสกุลย่อ · HN = 4 ตัวท้าย — ทั้ง Supabase และไฟล์ local
    🔁 optimistic concurrency (CR-2): ใส่ version + merge ราย-เคส ก่อนเขียน —
    ถ้าเครื่องอื่นเขียนแซงหลังเราโหลด จะ merge เฉพาะเคสที่เครื่องนี้แก้ทับบนของล่าสุด
    ไม่ทับทั้งกระดาน (กันงานของเครื่องอื่นหายเงียบ)"""
    try:
        from main_or_db import mask_patient_name, mask_hn
        today = _now().date().isoformat()
        out = []
        for c in cases:
            d = {k: _ser(val) for k, val in c.items()}
            if d.get('name'):
                d['name'] = mask_patient_name(d['name'])
            if d.get('hn'):
                d['hn'] = mask_hn(d['hn'])
            # หมายเหตุ: ชื่อแพทย์ (surgeon) "โชว์จริง" บนบอร์ด — ทีม OR ต้องรู้ว่าใครผ่า
            #   Supabase อยู่หลัง credentials+รหัสแอป (ไม่ใช่สาธารณะ) จึงเก็บได้ตามการใช้งานจริง
            for _nk in ('scrub_nurse', 'circ_nurse'):   # 🔒 พยาบาล: ย่อตามที่ผู้ใช้เลือกไว้
                if d.get(_nk):
                    d[_nk] = _mask_nurse_name(d[_nk])
            d.pop('procnote', None)   # 🔒 free text จาก HIS ไม่ขึ้น cloud (data minimization)
            out.append(d)

        # ---- optimistic concurrency: อ่านสถานะ DB ล่าสุดก่อนเขียน ----
        base_ver = int(st.session_state.get('_board_base_version', 0) or 0)
        dirty_ids = {str(x) for x in st.session_state.get('_board_dirty_ids', set())}
        merged, new_ver = out, base_ver + 1
        try:
            from main_or_db import load_board_state
            _s = load_board_state(today)
            if _s:
                _dbp = json.loads(_s)
                db_ver = int(_dbp.get('version', 0) or 0)
                if _dbp.get('date') == today and db_ver > base_ver:
                    # มีเครื่องอื่นเขียนแซง → merge ราย-เคส (เริ่มจากของ DB ล่าสุด)
                    by_key = {_board_case_key(d): d for d in _dbp.get('cases', [])}
                    overlay_all = not dirty_ids   # งานเป็นชุด (upload) → ของเราชนะ
                    for d in out:
                        k = _board_case_key(d)
                        if overlay_all or str(d.get('id')) in dirty_ids or k not in by_key:
                            by_key[k] = d
                    merged, new_ver = list(by_key.values()), db_ver + 1
                elif db_ver >= base_ver:
                    new_ver = db_ver + 1
        except Exception as _mx:
            print(f"[snapshot] merge ข้าม (เขียนตรง): {_mx}")

        payload = {
            'date': today,
            'pii_kept': False,   # คงคีย์ไว้เข้ากันได้กับ payload เก่า — False เสมอ
            'version': new_ver,
            'saved_at': _now().isoformat(),
            'cases': merged,
        }
        payload_str = json.dumps(payload, ensure_ascii=False, default=str)  # default=str = ตาข่ายกันพัง
        # 🖥️ บอร์ดกลาง: เขียนลง DB (app_settings) → ทุกเครื่อง/ผู้บริหารเห็นชุดเดียวกัน
        _saved = False
        try:
            from main_or_db import save_board_state
            _ok = save_board_state(today, payload_str)
            if _ok:
                _saved = True
                st.session_state['_board_base_version'] = new_ver  # ซิงก์แล้ว = ฐานใหม่
                st.session_state['_board_dirty_ids'] = set()        # ล้างหลังเซฟสำเร็จ
                st.session_state['_board_db_fail'] = 0              # 🔌 M-09: เซฟสำเร็จ → รีเซ็ตตัวนับ
            else:
                # 🔌 M-09: เซฟล้มเหลว (return False) — นับไว้ ไม่เคลม "ซิงก์แล้ว"
                st.session_state['_board_db_fail'] = st.session_state.get('_board_db_fail', 0) + 1
        except Exception as _dx:
            st.session_state['_board_db_fail'] = st.session_state.get('_board_db_fail', 0) + 1
            print(f"[snapshot] DB save ล้มเหลว (ใช้ local แทน): {_dx}")
        # ไฟล์ local = backup + โหมด offline (db_mode=sqlite เครื่องเดียว)
        _os.makedirs(_os.path.dirname(_SNAPSHOT_PATH), exist_ok=True)
        with open(_SNAPSHOT_PATH, 'w', encoding='utf-8') as f:
            f.write(payload_str)
        if not _saved:
            try:
                from db_connection import IS_SQLITE as _is_sqlite
            except Exception:
                _is_sqlite = True
            if _is_sqlite:
                _saved = True   # โหมดเครื่องเดียว: ไฟล์ local = สำเร็จ (ไม่มีบอร์ดกลาง)
        return _saved
    except Exception as _ex:
        print(f"[snapshot] save ล้มเหลว: {_ex}")
        return False


def _load_board_snapshot():
    """โหลด snapshot บอร์ด 'วันนี้' — อ่าน DB (บอร์ดกลาง) ก่อน → fallback ไฟล์ local
    คืน None ถ้าไม่มี/เป็นของวันอื่น (กันกู้ของเมื่อวาน)"""
    _today = _now().date().isoformat()
    try:
        payload = None
        # 🖥️ บอร์ดกลาง: อ่านจาก DB ก่อน (เห็นสถานะที่เครื่องอื่นกดล่าสุด)
        try:
            from main_or_db import load_board_state
            _s = load_board_state(_today)
            if _s:
                payload = json.loads(_s)
        except Exception as _dx:
            print(f"[snapshot] DB load ล้มเหลว: {_dx}")
        # fallback: ไฟล์ local (offline / DB ใช้ไม่ได้)
        if payload is None:
            if not _os.path.exists(_SNAPSHOT_PATH):
                return None
            with open(_SNAPSHOT_PATH, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        if payload.get('date') != _today:
            return None  # ของวันอื่น — อย่ากู้
        try:
            st.session_state['_snap_pii_kept'] = bool(payload.get('pii_kept', False))
            # 🔁 CR-2: จำ version ที่เพิ่งโหลด = ฐานสำหรับ optimistic concurrency ตอนเซฟ
            st.session_state['_board_base_version'] = int(payload.get('version', 0) or 0)
        except Exception:
            pass
        return [{k: _deser(val) for k, val in c.items()}
                for c in payload.get('cases', [])]
    except Exception as _ex:
        print(f"[snapshot] load ล้มเหลว: {_ex}")
        return None


def _or_board_demo():
    """เคสสาธิต Main OR — สร้างจาก demo_cases_data.DEMO_POOL (28 ก.ค. 2026)
    ═══════════════════════════════════════════════════════════════════
    ที่มา: ตารางผ่าตัดจริง 5 วัน (13-17 ก.ค. 69) mix แบบ "ห้องละหนึ่งวัน"
    → คง pattern แพทย์ประจำวัน · mask ครบ (ชื่อแพทย์จำลอง เช่น "ปิติ ก" /
    ชื่อผู้ป่วยจำลอง เช่น "สมชาย 3" / HN ปลอม — เปลี่ยนชุดชื่อ 9 ส.ค. 2026)
    แต่หัตถการ+วินิจฉัย+ASA/BMI คงจริง → ทำนายด้วยโมเดลจริง
    ตอนเปิดสาธิต (ส่ง SURG_xxx เข้าโมเดล) — ตัวเลข AI จึงเท่า production

    🎓 เคสแรกของแต่ละห้องเรียงเฟสตาม workflow ไว้สอนผู้ใช้:
    OR2 รอผ่าตัด(ฉุกเฉิน+นาฬิการอ) → OR3 กำลังผ่า(เขียว) → OR4 ใกล้ครบ(ส้ม)
    → OR5 เกินเวลา(แดง) → OR6 ห้องรับ-ส่ง → OR7 พักฟื้น → OR8 จำหน่าย(เทา)
    เคสถัดไปของทุกห้อง = ยังไม่มา/รอผ่าตัด (มีปุ่ม "รับเข้า" ให้กดเล่นครบ flow)
    ทุกเคส _demo=True → ไม่เขียน DB วิจัย/สถิติจริงเด็ดขาด"""
    from datetime import timedelta
    now = _now()
    try:
        from demo_cases_data import DEMO_POOL
    except ImportError:
        print("[demo] ไม่พบ demo_cases_data.py — โหมดสาธิตว่าง")
        return []
    try:
        from main_or_core import predict_surgical_time as _pst
    except ImportError:
        _pst = None

    # เฟสสอนของ "เคสแรก" แต่ละห้อง (ห้องอื่น ๆ ของเคสถัดไป = ยังไม่มา)
    _PHASE = {91: 'wait', 92: 'run_ok', 93: 'run_near', 94: 'run_over',
              95: 'post_hold', 96: 'post_rec', 97: 'done'}
    cases = []
    for d in DEMO_POOL:
        # 🔮 ทำนายด้วยโซ่โมเดลจริง — surgeon ส่งเป็น SURG_xxx (TE ตรงตัวจริง)
        pred, rng, conf, pn = 60, None, 'ต่ำ', 0
        if _pst is not None:
            try:
                _r = _pst(d['procedure'], d['age'],
                          surgeon=d.get('surgeon_code') or d['surgeon'],
                          division=d.get('division') or '1',
                          orroom=d['room'],
                          diagnosis=d.get('diagnosis') or '',
                          ward=d.get('ward') or '',
                          asa=d.get('ASA'), bmi=d.get('BMI'),
                          planicu=d.get('planicu'), blood=d.get('blood'))
                pred = int(_r.get('predicted_min') or 60)
                rng = _r.get('predicted_range')
                conf = _r.get('confidence', 'ปานกลาง')
                pn = int(_r.get('proc_n') or 0)
            except Exception as _px:
                print(f"[demo] ทำนายไม่ได้ ใช้ 60 นาที: {_px}")
        _emg = d.get('optype', 'Elective') != 'Elective'
        from fam_code import gen_fam_code
        _demo_seed = f"{d['hn']}|{d['room']}|{d['ororder']}"
        c = {'status': 'not_arrived', 'ororder': d['ororder'],
             'fam_code': gen_fam_code(_demo_seed),
             'sched_hour': d['sched_h'], 'sched_min': d['sched_m'],
             'name': d['name'], 'hn': d['hn'], 'age': d['age'],
             'procedure': d['procedure'], 'diagnosis': d.get('diagnosis') or d['procedure'],
             'surgeon': d['surgeon'],          # 🎭 ชื่อ mask — โชว์บนบอร์ด
             'division': d.get('division') or '1', 'room': d['room'],
             'ward': d.get('ward') or '',
             'predicted_min': pred, 'effective_min': pred,
             'ai_predicted_min': pred, 'predicted_range': rng,
             'range_method': ('conformal' if rng else None),
             'proc_n': pn, 'confidence': conf,
             'is_tf': False, '_demo': True,
             'is_emergency': _emg,
             'case_type': d.get('optype', 'Elective') if _emg else 'Elective'}
        for _k in ('ASA', 'BMI', 'planicu', 'blood'):   # 💉 preop (โชว์/ส่ง shadow)
            if d.get(_k) is not None:
                c[_k] = d[_k]

        # 🎬 จัดสถานะ: เคสแรกของห้อง = เฟสสอน · เคสถัดไป = ยังไม่มา (กดเล่นเอง)
        ph = _PHASE.get(d['room']) if d['ororder'] == 1 else None
        if ph == 'wait':                      # รอผ่าตัด (91 = เคสฉุกเฉินจริง → ไฟแดง)
            c['status'] = 'holding_pre'
            c['time_arrived_holding'] = now - timedelta(minutes=12)
        elif ph == 'run_ok':                  # กำลังผ่า เหลือเวลาเยอะ (เขียว)
            c['status'] = 'in_or'
            c['time_entered_or'] = now - timedelta(minutes=max(5, int(pred * 0.4)))
        elif ph == 'run_near':                # ใกล้ครบเวลา ~3 นาที (ส้ม mm:ss)
            c['status'] = 'in_or'
            c['time_entered_or'] = now - timedelta(minutes=max(1, pred - 3))
        elif ph == 'run_over':                # เกิน 1.5 เท่า (แดง + แจ้งเตือนหน้าบริหาร)
            c['status'] = 'in_or'
            c['time_entered_or'] = now - timedelta(minutes=int(pred * 1.5) + 8)
        elif ph == 'post_hold':               # ผ่าเสร็จ → ห้องรับ-ส่ง (ปุ่ม "จำหน่าย")
            act = pred + 9
            c.update(status='holding_post', actual_duration_min=act,
                     time_exited_or=now - timedelta(minutes=25),
                     time_entered_or=now - timedelta(minutes=25 + act))
        elif ph == 'post_rec':                # ผ่าเสร็จ → ห้องพักฟื้น (อีกปลายทาง)
            act = max(10, pred - 6)
            c.update(status='recovery', actual_duration_min=act,
                     time_exited_or=now - timedelta(minutes=35),
                     time_entered_or=now - timedelta(minutes=35 + act))
        elif ph == 'done':                    # จำหน่ายแล้ว (แถบเทา — จบ flow)
            act = pred + 4
            c.update(status='discharged', actual_duration_min=act,
                     time_discharged=now - timedelta(minutes=10),
                     time_exited_or=now - timedelta(minutes=95),
                     time_entered_or=now - timedelta(minutes=95 + act))
        # 🎬 เคสสอนเวลารอ (มุคกี้ปรับ 3 ส.ค. 2026):
        #    ทดสอบ4 (92#2) รอ 40 นาที = ใกล้เกณฑ์ · ทดสอบ5 (92#3) รอ 72 นาที
        #    = เกิน 60 → เห็นทั้งแจ้งเตือนรอนาน + ลอยขึ้นบนสุดของบอร์ด
        if d['room'] == 92 and d['ororder'] == 2:
            c['status'] = 'holding_pre'
            c['time_arrived_holding'] = now - timedelta(minutes=40)
        elif d['room'] == 92 and d['ororder'] == 3:
            c['status'] = 'holding_pre'
            c['time_arrived_holding'] = now - timedelta(minutes=72)
        # 🕓 เคส TF — to follow (มุคกี้สั่ง 4 ส.ค. 2026): เพื่อความสมจริงของบอร์ด
        #    OR4#3 กับ OR8#2 ไม่ระบุเวลานัด → ป้าย "นัด" ขึ้น TF และ placeholder
        #    23:55 ดันเคสไปท้ายคิวของห้องตัวเองอัตโนมัติ (กลไกเดียวกับ production)
        if (d['room'], d['ororder']) in ((93, 3), (97, 2)):
            c['is_tf'] = True
            c['sched_hour'], c['sched_min'] = 23, 55
        cases.append(c)
    return cases


_CUT_MIN = 15 * 60 + 30   # 15:30 = นาทีจากเที่ยงคืน


def _sched_min(c):
    h = c.get('sched_hour')
    return (h * 60 + (c.get('sched_min', 0) or 0)) if h is not None else None


def _case_end_min(c):
    """เวลาที่เคส 'จบ' (นาที) — ใช้เวลาจริงถ้ามี ไม่งั้นประเมินจาก sched + predicted
    เคส TF (ไม่ระบุเวลา — sched เป็น placeholder 23:55): ประเมินจากเวลาเข้าห้องจริง
    ถ้ายังไม่เข้าห้องถือว่ายังไม่รู้ → คืน 0 (ไม่นับเป็นรับเวรล่วงหน้า)"""
    for k in ('time_discharged', 'time_exited_or'):
        ts = c.get(k)
        if ts is not None and hasattr(ts, 'hour'):
            return ts.hour * 60 + ts.minute
    pred = int(c.get('effective_min') or c.get('predicted_min') or 60)
    if c.get('is_tf'):
        ent = c.get('time_entered_or')
        if ent is not None and hasattr(ent, 'hour'):
            return min(ent.hour * 60 + ent.minute + pred, 23 * 60 + 59)
        return 0  # TF ที่ยังไม่เริ่ม — เวลาไม่รู้จริง อย่าใช้ placeholder 23:55
    sh = c.get('sched_hour', 8) or 8
    sm = c.get('sched_min', 0) or 0
    return min(sh * 60 + sm + pred, 23 * 60 + 59)


def case_shift_class(c):
    """จัดประเภทเคส → 'นอกเวลา' / 'รับเวร' / 'ในเวลา' (3 กลุ่มไม่ทับกัน)
    - นอกเวลา: procnote ระบุ 'นอกเวลา' หรือ เวลานัดจริง >= 15:30
                (เคส TF ไม่นับ — 23:55 เป็นแค่ placeholder เรียงท้ายคิว)
    - รับเวร : ไม่ใช่นอกเวลา + ยังไม่เสร็จ/จบหลัง 15:30
    - ในเวลา : ที่เหลือ
    """
    sm = _sched_min(c)
    if c.get('is_after_note') or (not c.get('is_tf')
                                  and sm is not None and sm >= _CUT_MIN):
        return 'นอกเวลา'
    if _case_end_min(c) >= _CUT_MIN:
        return 'รับเวร'
    return 'ในเวลา'


# 🔐 PIN ปลดล็อกอัปโหลด CSV (เฉพาะผู้ดูแล) — อ่านจาก st.secrets['admin_pin']
# (เดิม hardcode ในโค้ด = ใครอ่านซอร์สบน GitHub ก็ปลดล็อกได้ — ย้ายเข้า secrets แล้ว)
from main_or_db import get_admin_pin as _get_admin_pin


def _enabled_room_options():
    """คืน [(room_no, ชื่อห้อง)] เฉพาะห้องที่เปิดใช้ (ไม่ถูกปิดในหน้าตั้งค่า)
    — ชื่อล้วน ไม่มีรหัสห้อง · ห้องที่ไม่มีใน settings = ถือว่าเปิด (default)"""
    from room_config import NEW_BUILDING_ROOMS, room_label
    try:
        from main_or_db import load_room_settings
        settings = load_room_settings()
    except Exception:
        settings = {}
    opts = []
    for r in NEW_BUILDING_ROOMS:
        s = settings.get(r)
        if s is None or s.get('enabled', True):
            opts.append((r, room_label(r)))
    return opts or [(r, room_label(r)) for r in NEW_BUILDING_ROOMS]

# สาขา (code → ชื่อ) สำหรับ dropdown ฟอร์มเพิ่มเคส — ตรงกับ DIV_CODE_MAP
_DIV_OPTIONS = [
    ('1', 'ศัลยกรรมทั่วไป'), ('2', 'ศัลยกรรมประสาทและสมอง'),
    ('3', 'ศัลยกรรมหู คอ จมูก'), ('4', 'ศัลยกรรมตกแต่ง'),
    ('5', 'ศัลยกรรมระบบทางเดินปัสสาวะ'), ('6', 'ศัลยกรรมลำไส้ใหญ่และทวารหนัก'),
    ('7', 'ศัลยกรรมหลอดเลือด'), ('8', 'ศัลยกรรมทรวงอก'),
    ('9', 'ศัลยกรรมตับ ตับอ่อน ทางเดินน้ำดี'), ('10', 'ปลูกถ่ายอวัยวะ'),
    ('41', 'ศัลยกรรมโรคหัวใจ'), ('71', 'ศัลยกรรมเด็ก'),
]


@st.cache_data(ttl=3600, show_spinner=False)
def _surgeons_by_specialty():
    """🧑‍⚕️ {ชื่อสาขา: [ชื่อแพทย์]} จากประวัติในตาราง cases — เติม dropdown
    "แพทย์ผ่าตัด" ตามสาขาที่เลือก · unmask รหัส SURG_xxx ได้เมื่อเครื่องมีกุญแจ
    (เครื่องที่ไม่มีกุญแจ เช่น cloud → รายชื่อว่าง = ช่องกลายเป็นพิมพ์อิสระ ไม่พัง)
    key ด้วย "ชื่อสาขา" (div_name) — ครอบทั้งรหัสสาขาชุดเก่า (75,74,…) และใหม่ (1-10)"""
    try:
        from main_or_db import get_conn, div_name
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT DISTINCT division_code, surgeon_name FROM cases "
                "WHERE surgeon_name IS NOT NULL AND surgeon_name <> ''").fetchall()
        finally:
            conn.close()
    except Exception:
        return {}
    try:
        from staff_unmask import unmask
    except Exception:
        def unmask(x):
            return x

    import re as _re
    _thai = _re.compile(r'[ก-๙]')

    # 🛡️ ชั้นที่ 1: whitelist จากทะเบียนแพทย์ (staff_mapping.csv — เครื่องที่มีกุญแจ)
    #    กันข้อมูล "กรอกผิดช่อง" ในตาราง cases (เช่นชื่อวินิจฉัย/หัตถการหลุดมา
    #    อยู่คอลัมน์แพทย์: 'C spondylosis', 'Sequelae of stroke') — เจอจริง 4 ก.ค. 2026
    _wl = set()
    try:
        import csv as _csv
        _mp = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                            'staff_mapping.csv')
        with open(_mp, encoding='utf-8-sig') as _f:
            for _r in _csv.DictReader(_f):
                if str(_r.get('role', '')).strip() == 'surgeon':
                    _nm = _re.sub(r'\s+', ' ',
                                  str(_r.get('original_name', '')).strip())
                    if _nm:
                        _wl.add(_nm)
    except Exception:
        pass    # ไม่มีไฟล์ (เช่นบน cloud) → ใช้ heuristic ชั้นที่ 2 แทน

    out = {}
    for _dv, _nm in rows:
        _nm2 = _re.sub(r'\s+', ' ', str(unmask(str(_nm))).strip())
        if not _nm2 or _nm2.upper().startswith(('SURG_', 'SCRUB_', 'CIRC_')):
            continue    # ยังเป็นรหัส mask (ไม่มีกุญแจบนเครื่องนี้) — ไม่โชว์รหัสให้ผู้ใช้
        if _nm2.lower() == 'resident':
            continue    # 🧑‍⚕️ dropdown = แพทย์ staff เท่านั้น (มุคกี้กำหนด 4 ก.ค. 2026)
            # เคส resident: พยาบาลพิมพ์ชื่อเองในช่องได้ (accept_new_options)
        if _wl:
            if _nm2 not in _wl:
                continue    # ไม่อยู่ในทะเบียนแพทย์ = ขยะกรอกผิดช่อง — ตัดทิ้ง
        else:
            # 🛡️ ชั้นที่ 2 (ไม่มีทะเบียน): ชื่อแพทย์ไทยต้องมีอักษรไทย ไม่มีตัวเลข
            #    และยาวพอเหมาะ — ตัดชื่อโรค/หัตถการภาษาอังกฤษที่ปนมา
            if (not _thai.search(_nm2) or any(ch.isdigit() for ch in _nm2)
                    or len(_nm2) > 45):
                continue
        out.setdefault(div_name(_dv), set()).add(_nm2)
    return {k: sorted(v) for k, v in out.items()}


def _render_add_case_form(demo_active):
    """ฟอร์มเพิ่มเคส walk-in/แทรก — กรอกเฉพาะข้อมูลที่โมเดลใช้ แล้วทำนายเวลา เข้าบอร์ด"""
    import uuid
    # 🖥️ 2 ส.ค. 2026 (มุคกี้สั่ง): แอป DEMO เปิด Manual ได้แม้สวิตช์ 🎬 เปิดอยู่ —
    #    ผู้ทรงพิมพ์เคสแทรกเข้าบอร์ดสาธิตเองได้ (จำลองสถานการณ์ walk-in)
    try:
        _demo_inst = str(st.secrets.get('instance_mode', '')).lower() == 'demo'
    except Exception:
        _demo_inst = False
    if demo_active and not _demo_inst:
        st.caption("ℹ️ ปิดสวิตช์ 🎬 สาธิต ด้านบนก่อน เพื่อเพิ่มเคสจริง")
        return
    if demo_active and _demo_inst:
        st.caption("🖥️ เพิ่มเคสจำลองแทรกเข้าบอร์ดสาธิตได้เลย — "
                   "ลองสถานการณ์เคส walk-in/เคสแทรก ระบบทำนายเวลาด้วย AI จริง")
    _room_opts = _enabled_room_options()  # เฉพาะห้องที่เปิดใช้ · ชื่อล้วน
    st.caption("กรอกเฉพาะข้อมูลที่จำเป็น — ช่องที่มี 🤖 คือข้อมูลที่ AI ใช้ทำนายเวลา "
               "(ระบบจับคู่ชื่อหัตถการ/แพทย์ใกล้เคียงให้อัตโนมัติ)")

    c1, c2 = st.columns(2)
    name = c1.text_input("ชื่อ-สกุล", key="ac_name", placeholder="ชื่อผู้ป่วย")
    age = c2.number_input("🤖 อายุ (ปี)", min_value=0, max_value=120, value=50,
                          step=1, key="ac_age")
    proc = st.text_input("🤖 หัตถการ (ICD-9) *", key="ac_proc",
                         placeholder="เช่น Laparoscopic cholecystectomy")
    diag = st.text_input("🤖 วินิจฉัย (ICD-10)", key="ac_diag",
                         placeholder="เช่น Cholelithiasis")
    # 🧑‍⚕️ ลำดับใหม่ (4 ก.ค. 2026): เลือก "สาขา" ก่อน → ช่องแพทย์กรองรายชื่อตามสาขา
    #    แต่ยังพิมพ์ชื่อใหม่ได้ (แพทย์ที่ไม่เคยมีในระบบ) · บังคับกรอกเพราะโมเดลใช้
    #    แพทย์ (~24%) + หัตถการ (~30%) เป็น feature หลัก
    c3, c4 = st.columns(2)
    _div_label = c3.selectbox("🤖 สาขา (เลือกก่อน — ใช้กรองรายชื่อแพทย์)",
                              [d[1] for d in _DIV_OPTIONS], key="ac_div")
    _div_code = next((d[0] for d in _DIV_OPTIONS if d[1] == _div_label), '75')
    _known_surg = _surgeons_by_specialty().get(_div_label, [])
    with c4:
        try:
            # Streamlit ≥1.45: selectbox พิมพ์ค้นหาได้ + accept_new_options
            surg = st.selectbox(
                "🤖 แพทย์ผ่าตัด *", options=_known_surg, index=None,
                key="ac_surg_sel", accept_new_options=True,
                placeholder="พิมพ์ค้นหา หรือพิมพ์ชื่อแพทย์ใหม่แล้วกด Enter",
                help=(f"รายชื่อจากประวัติเคสสาขานี้ ({len(_known_surg)} คน) — "
                      "ถ้าเป็นแพทย์ใหม่ พิมพ์ชื่อ-สกุลเต็มแล้วกด Enter ได้เลย"))
        except TypeError:   # streamlit เก่ากว่า 1.45 — พิมพ์อิสระตามเดิม
            surg = st.text_input("🤖 แพทย์ผ่าตัด *", key="ac_surg",
                                 placeholder="ชื่อแพทย์")
    surg = (surg or '').strip()
    c5, c6 = st.columns(2)
    _room_label = c5.selectbox("🤖 ห้อง", [lbl for _, lbl in _room_opts],
                               key="ac_room")
    from datetime import time as _time
    _sched = c6.time_input("🤖 เวลานัด", value=_time(9, 0), key="ac_time")
    # 💉 feature จาก preop (19 ก.ค. 2026) — จอง ICU 8.5% · จองเลือด 8.0% · ASA 5.9%
    #    ของ feature importance รวม — ไม่รู้ก็ข้ามได้ (โมเดลใช้ค่ากลางแทน)
    cp1, cp2, cp3 = st.columns(3)
    _asa = cp1.selectbox("🤖 ASA", ['ไม่ระบุ', '1', '2', '3', '4', '5',
                                    '1E', '2E', '3E', '4E', '5E'],
                         key="ac_asa", help="จากใบประเมิน preop วิสัญญี — ถ้ามี")
    _blood = cp2.selectbox("🤖 จองเลือด", ['ไม่ระบุ', 'จอง', 'ไม่จอง'],
                           key="ac_blood")
    _icu = cp3.selectbox("🤖 จอง ICU", ['ไม่ระบุ', 'จอง', 'ไม่จอง'],
                         key="ac_icu")
    ce1, ce2 = st.columns(2)
    _no_time = ce1.checkbox("ไม่ระบุเวลา (เคส TF — เรียงท้ายคิว)", key="ac_tf")
    is_emer = ce2.checkbox("🔴 เคสฉุกเฉิน (ติดไฟแดงบนบอร์ด)", key="ac_emer")
    if _no_time:
        _sched = None

    cbtn1, cbtn2 = st.columns([3, 1])
    if cbtn1.button("🤖 เพิ่มเคส + ทำนายเวลา", type="primary", width='stretch',
                    key="ac_submit"):
        if not (proc or '').strip() or not surg:
            st.error("กรุณากรอก 'หัตถการ' และ 'แพทย์ผ่าตัด' ให้ครบ — "
                     "AI ใช้สองช่องนี้เป็นข้อมูลหลักในการทำนายเวลา")
            return
        _room_no = next((rn for rn, lbl in _room_opts if lbl == _room_label),
                        _room_opts[0][0])
        if _sched is not None:
            sched_h, sched_m, is_tf = _sched.hour, _sched.minute, False
        else:
            sched_h, sched_m, is_tf = 23, 55, True  # ไม่ระบุเวลา = TF (เรียงท้าย)
        # แปลงค่าฟอร์ม preop → รูปแบบที่โมเดลใช้ ('ไม่ระบุ' = ไม่ส่ง)
        _asa_v = _asa if _asa != 'ไม่ระบุ' else None
        _blood_v = {'จอง': 'มี', 'ไม่จอง': 'ไม่มี'}.get(_blood)
        _icu_v = {'จอง': 'มี', 'ไม่จอง': 'ไม่มี'}.get(_icu)
        try:
            from preop_merge import sex_from_name as _sfn
            _sex_v = _sfn(name)
        except Exception:
            _sex_v = None
        # ทำนายเวลาด้วยโมเดล (ส่งข้อมูลครบที่กรอก)
        try:
            from main_or_core import predict_surgical_time
            _pred = predict_surgical_time(
                procedure=proc.strip().upper(), age=int(age),
                surgeon=(surg or '').strip(), division=str(_div_code),
                op_hour=sched_h if sched_h < 23 else 9,
                op_date=_now(), orroom=int(_room_no),
                diagnosis=(diag or '').strip(),
                asa=_asa_v, blood=_blood_v, planicu=_icu_v, sex=_sex_v)
            _pm = int(_pred.get('predicted_min') or 60)
            _conf = _pred.get('confidence')
            _pn = _pred.get('proc_n', 0)
            _rng = _pred.get('predicted_range')
            _rngm = _pred.get('range_method')
        except Exception as _ex:
            print(f"[add_case] predict ล้มเหลว: {_ex}")
            _pm, _conf, _pn, _rng, _rngm = 60, 'ต่ำ', 0, None, None
        from fam_code import gen_fam_code
        _manual_id = f"MANUAL_{uuid.uuid4().hex[:8]}"
        case = {
            'id': _manual_id, 'fam_code': gen_fam_code(_manual_id),
            'hn': '', 'name': (name or '').strip() or 'ไม่ระบุ',
            'age': int(age), 'diagnosis': (diag or '').strip() or '-',
            'procedure': proc.strip().upper(), 'anesthesia': '-',
            'surgeon': (surg or '').strip(), 'room': _room_no,
            'division': str(_div_code), 'ororder': 99,
            'case_type': 'Emergency' if is_emer else 'Elective',
            'is_emergency': is_emer, 'ward': '',
            'sched_date': _now().date(), 'sched_hour': sched_h,
            'sched_min': sched_m, 'is_tf': is_tf, 'is_after_note': False,
            'procnote': '', 'predicted_min': _pm, 'confidence': _conf,
            'proc_n': _pn,
            'predicted_range': _rng, 'range_method': _rngm,   # 📏 ช่วง conformal 90%
            'status': 'not_arrived', 'ai_predicted_min': _pm,
            'user_override_min': None, 'effective_min': _pm,
            'or_room_assigned': _room_no,
            'time_arrived_holding': None, 'time_entered_or': None,
            'time_exited_or': None, 'time_discharged': None,
            'actual_duration_min': None,
            # 💉 เก็บ feature preop ติดเคสไว้ — shadow log ใช้ชุดเดียวกับบอร์ด
            'ASA': _asa_v, 'blood': _blood_v, 'planicu': _icu_v, 'sex': _sex_v,
        }
        _cur = list(st.session_state.patient_cases)
        _cur.append(case)
        st.session_state.patient_cases = _cur
        # 🖥️ แอป DEMO ขณะสาธิต: คงธงสาธิตไว้ — ถ้าปิดธง toggle จะโหลดชุดจำลอง
        #    ใหม่ทับเคสที่เพิ่งพิมพ์เพิ่ม (บั๊กแฝงเดิม) · production พฤติกรรมเดิม
        if not (_demo_inst and demo_active):
            st.session_state['_or_demo'] = False
        _mark_board_dirty(case)   # CR-2: เพิ่มเคสใหม่ → ดันขึ้นบอร์ดกลาง
        _rng_txt = (f" · ช่วง 90%: {int(_rng[0])}–{int(_rng[1])} นาที"
                    if (_rngm == 'conformal' and _rng) else "")
        from main_or_db import mask_patient_name as _mpn
        st.success(f"✅ เพิ่มเคส '{_mpn(case['name'])}' แล้ว — AI ทำนาย {_pm} นาที "
                   f"(จาก {_pn} เคส){_rng_txt}")
        _rerun_board()
    if cbtn2.button("ล้างฟอร์ม", key="ac_clear", width='stretch'):
        for _k in ('ac_name', 'ac_proc', 'ac_diag', 'ac_surg', 'ac_surg_sel'):
            st.session_state.pop(_k, None)
        _rerun_board()


def render_csv_upload(bare=False):
    """📤 อัปโหลดตารางผ่าตัด (CSV+preop) — อยู่บนหน้าตารางผ่าตัด เหนือ ➕ เพิ่มเคส
    🔓 19 ก.ค. 2026 (มุคกี้สั่ง): อัปโหลดเปิดให้พยาบาลทุกคน ไม่ต้องใส่ PIN —
    PIN ย้ายไปคุมเฉพาะ 🗑️ ล้างกระดาน (ลบได้เฉพาะผู้ดูแล)
    bare=True (5 ส.ค. 2026): วาดเนื้อในโดยไม่ห่อ expander — ใช้ในแท็บ 🧰 เครื่องมือ"""
    import contextlib
    _demo_active = bool(st.session_state.get('_or_demo'))
    _wrap = (contextlib.nullcontext() if bare else
             st.expander("📤 อัปโหลดตารางผ่าตัดวันนี้ (CSV/Excel)", expanded=False))
    with _wrap:
        # 🖥️ ข้อความนำต่างกันตาม instance (มุคกี้สั่ง 2 ส.ค. 2026)
        try:
            _demo_inst_up = str(st.secrets.get('instance_mode', '')).lower() == 'demo'
        except Exception:
            _demo_inst_up = False
        if _demo_inst_up:
            st.caption("🖥️ ระบบสาธิต: กดปุ่ม 🎬 เปิดโหมดสาธิต จะมีเคสจำลองพร้อมใช้งานทันที")
        else:
            st.caption("📅 งานประจำทุกเช้า: อัปโหลดตารางผ่าตัดวันนี้จากไฟล์ HIS "
                       "(แนะนำไฟล์ Excel — กันปัญหาคอลัมน์เลื่อนจาก comma)")
        if _demo_active:
            st.caption("ℹ️ กดปุ่ม ⏹️ ปิดโหมดสาธิต ด้านบนก่อน เพื่ออัปโหลดตารางจริง")
        # 📊 1 ส.ค. 2026: เปิดรับ Excel — แนะนำใช้ .xls/.xlsx จาก HIS แทน CSV
        #    (CSV ที่ HIS ไม่ครอบ quote เจอ comma ในช่องหัตถการแล้วคอลัมน์เลื่อน)
        _up = st.file_uploader("① ไฟล์ตารางผ่าตัดจาก HIS (.xls/.xlsx/.csv)",
                               type=["xls", "xlsx", "csv"],
                               key="orboard_csv", disabled=_demo_active,
                               help="แนะนำไฟล์ Excel — กันปัญหาคอลัมน์เลื่อน"
                                    "จาก comma ในชื่อหัตถการ/วินิจฉัยของไฟล์ CSV")
        # 💉 ไฟล์ preop วิสัญญี (19 ก.ค. 2026) — เติม ASA/BMI/จองเลือด/จอง ICU
        #    ให้โมเดล (feature ที่บอร์ดไม่เคยมี) · ไม่ใส่ = ทำงานแบบเดิม
        _up_pre = st.file_uploader(
            "② ไฟล์ preop ของวิสัญญี (.xls/.csv)",
            type=["xls", "xlsx", "csv"], key="orboard_preop", disabled=_demo_active,
            help="ไฟล์ประเมินก่อนผ่าตัดจากวิสัญญี — ระบบจับคู่ผู้ป่วยด้วย HN "
                 "แล้วเติม ASA / BMI / จองเลือด / จอง ICU ให้ AI ใช้ทำนาย")
        _rep = st.checkbox("แทนที่เคส 'ยังไม่มา' เดิม (กันซ้ำ)", value=True,
                           key="orboard_rep", disabled=_demo_active)
        # 🧪 อัปโหลดเพื่อ "ทดสอบระบบ": ติดธง _demo ทุกเคส → กดได้ครบทุก flow
        #    แต่ override_log / shadow_v2_log / case_history จะไม่ถูกเขียนเลย
        #    (ไม่มีรอยใน DB วิจัย) · ทดสอบเสร็จกด 🗑️ ล้างกระดานวันนี้ = จบสะอาด
        _testmode = st.checkbox(
            "🧪 โหมดทดสอบระบบ — เคสชุดนี้จะไม่ถูกบันทึกลงฐานข้อมูลวิจัย",
            value=False, key="orboard_testmode", disabled=_demo_active,
            help="ติ๊กเมื่อใช้ไฟล์ทดสอบ: บอร์ดทำงานเหมือนจริงทุกอย่าง แต่ไม่เขียน "
                 "override/shadow/case_history · เสร็จแล้วลบทิ้งด้วยปุ่ม "
                 "'🗑️ ล้างกระดานวันนี้' ด้านล่าง")
        if _up is not None and not _demo_active and st.button(
                "✅ โหลดเข้าบอร์ด + ทำนายเวลา",
                type="primary", width='stretch', key="orboard_load"):
            with st.spinner("กำลังอ่านไฟล์ + ทำนายเวลา..."):
                try:
                    from main_or_app import parse_schedule_csv_to_cases
                    _new = parse_schedule_csv_to_cases(_up)
                except Exception as _ex:
                    _new = []
                    st.error(f"อ่านไฟล์ไม่สำเร็จ: {_ex}")
            if not _new:
                st.warning("ไม่พบเคสในไฟล์ — ลองตรวจหัวคอลัมน์ (hn/ชื่อ/หัตถการ/เวลา/ห้อง)")
            else:
                # 💉 เติมเพศจากคำนำหน้า + ข้อมูล preop วิสัญญี → ทำนายใหม่ครบ feature
                try:
                    from preop_merge import enrich_cases, load_preop
                    _pm = load_preop(_up_pre) if _up_pre is not None else None
                    _nm = enrich_cases(_new, _pm)
                    if _pm is not None:
                        st.info(f"💉 จับคู่ข้อมูลวิสัญญีได้ {_nm}/{len(_new)} เคส "
                                f"(จับคู่ด้วย HN — เคสที่ไม่เจอใช้ค่าทำนายแบบเดิม)")
                    from main_or_core import predict_surgical_time as _pst
                    for _ec in _new:
                        if not (_ec.get('ASA') or _ec.get('BMI') or _ec.get('sex')
                                or _ec.get('planicu') or _ec.get('blood')):
                            continue
                        _pr = _pst(
                            _ec['procedure'], _ec['age'], _ec['surgeon'],
                            _ec['division'],
                            _ec['sched_hour'] if _ec['sched_hour'] < 23 else 9,
                            diagnosis=(_ec.get('diagnosis')
                                       if _ec.get('diagnosis') != '-' else ''),
                            ward=_ec.get('ward') or '',
                            asa=_ec.get('ASA'), bmi=_ec.get('BMI'),
                            sex=_ec.get('sex'), planicu=_ec.get('planicu'),
                            blood=_ec.get('blood'))
                        _ec['predicted_min'] = _pr['predicted_min']
                        _ec['ai_predicted_min'] = _pr['predicted_min']
                        _ec['effective_min'] = _pr['predicted_min']
                        _ec['confidence'] = _pr['confidence']
                        _ec['proc_n'] = _pr.get('proc_n', 0)
                        _ec['predicted_range'] = _pr.get('predicted_range')
                except Exception as _px:
                    st.warning(f"เติมข้อมูล preop ไม่สำเร็จ (ใช้ค่าทำนายเดิม): {_px}")
                _cur = list(st.session_state.patient_cases)
                if _rep:
                    _cur = [c for c in _cur if c.get('status') != 'not_arrived']
                _seen_hn = {c.get('hn') for c in _cur if c.get('hn')}
                _added = 0
                for _nc in _new:
                    if _nc.get('hn') and _nc['hn'] in _seen_hn:
                        continue
                    if _testmode:
                        _nc['_demo'] = True   # 🧪 เคสทดสอบ — guard ทุกจุดจะไม่เขียน DB วิจัย
                    _cur.append(_nc)
                    _added += 1
                st.session_state.patient_cases = _cur
                st.session_state['_or_demo'] = False
                st.session_state['_board_dirty'] = True   # CR-2: โหลดตารางใหม่ → ดันขึ้นบอร์ดกลาง
                _msg = f"✅ โหลด {_added} เคสเข้าบอร์ดแล้ว — ไปดูที่หน้า 📋 ตารางผ่าตัด"
                if _testmode:
                    _msg += " · 🧪 โหมดทดสอบ (ไม่บันทึกลงฐานข้อมูลวิจัย)"
                st.success(_msg)
                st.rerun()

        # ---- 🗑️ ล้างกระดานวันนี้ — ล็อก PIN เฉพาะผู้ดูแล (Mukky) ----
        #      (19 ก.ค. 2026: สลับกุญแจ — อัปโหลดฟรี / การลบต้องมี PIN)
        st.markdown("---")
        if st.checkbox("🗑️ ล้างกระดานวันนี้ (สำหรับลบเคสทดสอบ) 🔒",
                       key="orb_clear_open",
                       help="ลบเคสทั้งหมดของวันนี้ออกจากบอร์ด+บอร์ดกลาง (ทุกเครื่อง) "
                            ": เฉพาะผู้วิจัย · ไม่กระทบสถิติย้อนหลัง"):
            # 👤 production 19 ก.ค. 2026: เช็กบทบาทจากหน้า login — ไม่ถามรหัสซ้ำ
            if st.session_state.get('role') != 'admin':
                st.caption("🔒 การล้างกระดานทำได้เฉพาะผู้วิจัย : ออกจากระบบ "
                           "แล้วเข้าใหม่ด้วยรหัสผู้ดูแลระบบ")
            else:
                _render_clear_board_body()


def _render_clear_board_body():
    """เนื้อใน 🗑️ ล้างกระดานวันนี้ — เรียกจากตัวเลือกใน render_csv_upload
    (อยู่หลังประตู PIN ของอัปโหลดแล้ว จึงไม่มีประตูซ้ำ)"""
    st.caption("ลบเคสทั้งหมดของวันนี้ออกจากบอร์ด + บอร์ดกลาง (ทุกเครื่อง) — "
               "ใช้เคลียร์ข้อมูลทดสอบ · ไม่กระทบสถิติย้อนหลัง/ฐานข้อมูลเคสที่ import")
    _ok_clear = st.checkbox("ยืนยันต้องการล้างกระดานวันนี้", key="orb_clear_ok")
    if st.button("🗑️ ล้างกระดานวันนี้", type="secondary", width='stretch',
                 disabled=not _ok_clear, key="orb_clear_btn"):
        st.session_state.patient_cases = []
        st.session_state['_or_demo'] = False
        st.session_state['_board_dirty'] = False          # ล้างแล้ว ไม่มีอะไรต้องเซฟ
        st.session_state['_board_dirty_ids'] = set()
        st.session_state['_board_was_restored'] = False
        _td = _now().date().isoformat()
        # 🧹 ล้างข้ามเครื่อง: เขียน payload "ว่าง" version+1 แทนการลบ key —
        #    ลบ key เฉยๆ เครื่องอื่นจะ fallback ไฟล์ local ตัวเอง แล้วเซฟเคสกลับมา
        #    (เคสผีคืนชีพ) · payload ว่างทำให้ทุกเครื่อง pull แล้วเห็นกระดานว่างจริง
        try:
            from main_or_db import load_board_state, save_board_state
            _ver = 0
            try:
                _s0 = load_board_state(_td)
                if _s0:
                    _ver = int(json.loads(_s0).get('version', 0) or 0)
            except Exception:
                pass
            _empty = json.dumps(
                {'date': _td, 'pii_kept': False, 'version': _ver + 1,
                 'saved_at': _now().isoformat(), 'cleared': True, 'cases': []},
                ensure_ascii=False)
            save_board_state(_td, _empty)
            st.session_state['_board_base_version'] = _ver + 1
        except Exception as _ex:
            st.session_state['_board_base_version'] = 0
            print(f"[clear_board] DB ล้มเหลว: {_ex}")
        try:                                              # ลบไฟล์ snapshot local ด้วย
            if _os.path.exists(_SNAPSHOT_PATH):
                _os.remove(_SNAPSHOT_PATH)
        except Exception:
            pass
        st.success("✅ ล้างกระดานวันนี้แล้ว (ทุกเครื่อง)")
        st.rerun()


def page_or_board():
    """หน้า 📋 ตารางผ่าตัด — เนื้อบอร์ดทั้งหมดย้ายไปอยู่ใน _board_fragment
    (⚡ perf: กดปุ่ม/tick 30 วิ rerun เฉพาะก้อนบอร์ด ไม่ใช่ทั้งแอป)"""
    _board_fragment()


@_fragment(run_every=30)
def _board_fragment():
    from main_or_db import div_name
    from room_config import room_label
    import time as _tmod

    # 🛡️ 2 ส.ค. 2026: fragment รันอิสระจาก main() ได้ (auto-rerun 30 วิ /
    #    reconnect หลัง reboot) — init เองกัน session ไม่มี patient_cases
    #    (idempotent: มี key แล้ว = ไม่ทำอะไร)
    from main_or_core import init_session_state as _iss
    _iss()
    _flush_toast()   # 🎨 โชว์ toast ที่ฝากไว้จากปุ่มรอบก่อน (demo)
    _flush_sound()   # 🔊 เล่นเสียงที่ฝากไว้จากปุ่มรอบก่อน (demo+production)

    # 🖥️ instance นี้เป็นแอป DEMO ไหม — ใช้ตัดสินตลอดทั้ง fragment:
    #    demo instance = โหมดสาธิตซิงก์ขึ้นบอร์ดกลาง (schema demo) เต็มรูปแบบ
    #    จอญาติ/จอห้อง demo จึงเห็นเคสสาธิตเหมือนใช้งานจริงทุกจอ
    try:
        _is_demo_instance = str(st.secrets.get('instance_mode', '')).lower() == 'demo'
    except Exception:
        _is_demo_instance = False

    def _rid(c):
        """หมายเลขห้องจริง (90-97) หรือ None ถ้าไม่ระบุ/placeholder"""
        try:
            r = int(float(c.get('room')))
        except (TypeError, ValueError):
            return None
        return r if r and r != 1 else None

    def _loc(c):
        r = _rid(c)
        return room_label(r) if r else div_name(c.get('division', ''))

    def _tlabel(c):
        if c.get('is_tf'):
            return 'TF'
        return f'{c.get("sched_hour",8):02d}:{c.get("sched_min",0):02d}'

    cases = st.session_state.patient_cases

    # 🖥️ บอร์ดกลาง (shared ผ่าน DB) + auto-refresh ทุก ~30 วิ
    # ทุกเครื่อง/ผู้บริหารดึงสถานะล่าสุดเมื่อ: เปิดครั้งแรก · กด 🔄 · ครบรอบ refresh
    # ไม่ดึงตอน "เพิ่งกดปุ่มบนเครื่องตัวเอง" (กันทับการเปลี่ยนที่ยังไม่ได้ save)
    # 🖥️ แอป DEMO: ซิงก์บอร์ดกลางแม้เปิดสาธิตอยู่ (หลายจอเห็นชุดเดียวกัน)
    if _is_demo_instance or not st.session_state.get('_or_demo'):
        # 🕛 M-10: ข้ามเที่ยงคืน → ล้างเคส "เมื่อวาน" + บังคับดึงบอร์ดของ "วันนี้"
        #          (กันเคสเก่าถูกเซฟทับด้วย key วันใหม่ → เช้ามาเห็นเคสเมื่อวานปนบอร์ด)
        _today_iso = _now().date().isoformat()
        if st.session_state.get('_board_last_date') not in (None, _today_iso):
            st.session_state.patient_cases = []
            cases = []
            st.session_state['_board_dirty'] = False
            st.session_state['_board_dirty_ids'] = set()
            st.session_state['_board_base_version'] = 0
            st.session_state['_board_force_pull'] = True
            st.session_state['_board_restored'] = False
            st.session_state['_board_was_restored'] = False
            # 🖥️ demo (3 ส.ค. 2026): ข้ามเที่ยงคืน → ปิดสวิตช์สาธิตให้ด้วย
            #    จบวงจรเหมือนระบบจริง (บอร์ดว่างรอวันใหม่ ไม่ค้างสวิตช์เปิดกำกวม)
            if _is_demo_instance and st.session_state.get('_or_demo'):
                st.session_state['_or_demo'] = False
        st.session_state['_board_last_date'] = _today_iso
        if _HAS_FRAGMENT:
            # ⏲️ fragment run_every=30 คือ "tick" ในตัว — ครบ ~25 วิจาก pull ล่าสุด
            #    ให้ดึงบอร์ดกลางรอบใหม่ (แทน streamlit_autorefresh ที่ rerun ทั้งแอป)
            _last_pull = float(st.session_state.get('_board_last_pull') or 0.0)
            if _tmod.monotonic() - _last_pull >= 25.0:
                st.session_state['_board_force_pull'] = True
        else:
            try:    # fallback: streamlit เก่า (<1.37) — พฤติกรรมเดิมทุกอย่าง
                from streamlit_autorefresh import st_autorefresh
                _tick = st_autorefresh(interval=30000, key='_board_live')
                if _tick != st.session_state.get('_board_tick_seen'):
                    st.session_state['_board_tick_seen'] = _tick
                    st.session_state['_board_force_pull'] = True
            except Exception:
                pass
        # ✏️ 2 ส.ค. 2026 (มุคกี้สั่ง): มีร่างแก้เวลาใน ✏️ ที่ยังไม่เซฟบนเครื่องนี้
        #    → เลื่อนการดึงบอร์ดกลางของรอบ tick นั้น (กัน pull มาสลับ/รีเซ็ต
        #    กลางมือพิมพ์) · per-session — เครื่องอื่น tick ปกติไม่กระทบ
        #    เพดาน 4 รอบ (~2 นาที): พิมพ์ค้างแล้วเดินหนี = กลับมาดึงตามปกติ
        #    กด 🔄 เอง (_board_user_pull) = ดึงเสมอ ไม่ถูกเลื่อน
        def _editing_in_progress():
            try:
                for _i, _c in enumerate(cases):
                    _v = st.session_state.get(f'tb_ov_{_i}')
                    if _v is None:
                        continue
                    _e = (_c.get('effective_min') or _c.get('ai_predicted_min')
                          or _c.get('predicted_min') or 30)
                    if int(_v) != int(_e):
                        return True
            except Exception:
                pass
            return False

        _editing = _editing_in_progress()
        _user_pull = st.session_state.pop('_board_user_pull', False)
        _pull = st.session_state.pop('_board_force_pull', False)
        if not _editing:
            st.session_state['_edit_skip_n'] = 0
        elif _pull and not _user_pull:
            _n = int(st.session_state.get('_edit_skip_n', 0)) + 1
            st.session_state['_edit_skip_n'] = _n
            if _n <= 4:
                _pull = False       # เลื่อนรอบนี้ — tick ถัดไปตั้งธงใหม่เอง
        if not cases and not st.session_state.get('_board_restored'):
            _pull = True
        st.session_state['_board_restored'] = True
        # 🚫 CR-2: ถ้าเครื่องนี้เพิ่งแก้แต่ยังไม่ได้เซฟ → อย่าดึงทับ (กันงานตัวเองหาย)
        #         เซฟท้ายหน้าจะ merge ขึ้น DB เอง แล้วรอบหน้าค่อยดึงผลรวมกลับมา
        if _pull and not st.session_state.get('_board_dirty'):
            _shared = _load_board_snapshot()
            st.session_state['_board_last_pull'] = _tmod.monotonic()
            # 🎨 demo: เวลานาฬิกาสำหรับป้าย "อัปเดตล่าสุด HH:MM:SS" (Doherty)
            st.session_state['_board_last_pull_wall'] = _now().strftime('%H:%M:%S')
            if _shared is not None:
                st.session_state.patient_cases = _shared
                cases = _shared
                st.session_state['_board_was_restored'] = True
    if cases and st.session_state.get('_board_db_fail', 0) > 2:
        # 🔌 M-09: เซฟขึ้น DB กลางล้มเหลวติดกัน → บอกตรงๆ ว่าออฟไลน์ (ไม่โกหกว่า "ซิงก์แล้ว")
        st.warning("⚠️ บอร์ดกลางออฟไลน์: เครื่องนี้ยังไม่ได้แชร์ขึ้นเซิร์ฟเวอร์ "
                   "(บันทึกไว้ในเครื่องชั่วคราว) · ตรวจการเชื่อมต่อแล้วกด 🔄 รีเฟรช")
    # (เอา caption "บอร์ดกลาง — ซิงก์ทุกเครื่อง" ออกเพื่อเพิ่มพื้นที่ — สถานะซิงก์โชว์เป็นชิปบนหัวแล้ว)

    # (วันที่/เวลาปรับล่าสุด ย้ายไปเป็นชิปบนแถบหัวแล้ว — board เริ่มที่แถวควบคุมเลย)

    # ---------- แถวควบคุม: Demo Mode + ปุ่มรีเฟรช (มุมขวา) ----------
    _ctl_l, _ctl_warn, _ctl_r = st.columns([3, 1.5, 1], vertical_alignment="center")
    with _ctl_r:
        if st.button("🔄 รีเฟรช", key="orboard_refresh", width='stretch',
                     type='primary',
                     help="ดึงสถานะล่าสุดจากบอร์ดกลาง (เห็นที่เครื่องอื่นกด)"):
            st.session_state['_board_force_pull'] = True   # บังคับดึงจาก DB กลาง
            st.session_state['_board_user_pull'] = True    # ✋ คนสั่งเอง — ห้ามถูกเลื่อน
            _rerun_board()
    with _ctl_warn:
        st.markdown("<div style=\x27text-align:right;color:#808495;font-size:var(--fs-meta);line-height:1.3;\x27>⚠️ อย่ากด F5 — ใช้ปุ่มนี้แทน</div>", unsafe_allow_html=True)
        # 🎨 demo: บอกเวลาซิงก์ล่าสุด — ช่องว่าง 30 วิ จะไม่ถูกอ่านว่า "ค้าง"
        if _is_demo_instance and st.session_state.get('_board_last_pull_wall'):
            st.markdown(
                f"<div style='text-align:right;color:#b6c2cf;font-size:var(--fs-meta);'>"
                f"อัปเดตล่าสุด {st.session_state['_board_last_pull_wall']}</div>",
                unsafe_allow_html=True)
    # 🚪 โหมดจอประจำห้อง: ไม่มีสวิตช์สาธิต (กันจอห้องเผลอสลับบอร์ดทั้งตึกเป็นสาธิต)
    _room_scope_board = (st.session_state.get('room_scope')
                         if st.session_state.get('role') == 'room' else None)
    # 🧪 2 ส.ค. 2026 (มุคกี้สั่ง): ปุ่ม 🎬 สาธิต แสดงเฉพาะ "ระบบ DEMO"
    #    (_is_demo_instance คำนวณไว้หัว fragment แล้ว) — production ซ่อนถาวร
    with _ctl_l:
        if not _is_demo_instance:
            # 🔒 production: บังคับปิดสาธิตเสมอ (โค้ดถัดไปจะล้างเคสสาธิตค้างให้เอง)
            _demo_on = False
        elif _room_scope_board:
            _demo_on = bool(st.session_state.get('_or_demo'))
        else:
            # 🔘 4 ส.ค. 2026 (มุคกี้สั่ง): toggle เคยค้าง (widget-state cleanup
            #    ข้ามแท็บ ทำให้กดเปิด-ปิดไม่ติด) → เปลี่ยนเป็นปุ่มกดตรง ๆ
            #    ปุ่ม = stateless สั่งธง _or_demo ทันที ไม่มีสถานะ widget ให้ค้าง
            #    เห็นทีละปุ่มตามสถานะจริง (Hick's Law: ทางเลือกเดียว กดไม่พลาด)
            _demo_on = bool(st.session_state.get('_or_demo'))
            if _demo_on:
                if st.button("⏹️ ปิดโหมดสาธิต", key="orboard_demo_off",
                             help="ปิดแล้วเคสสาธิตทั้งหมดจะถูกล้างออกจากบอร์ด"):
                    _demo_on = False
            else:
                if st.button("🎬 เปิดโหมดสาธิต", key="orboard_demo_on",
                             help="เปิดแล้วจะมีเคสสาธิตพร้อมใช้งาน "
                                  "กดปุ่มต่าง ๆ ได้เหมือนระบบจริง"):
                    _demo_on = True
    if _demo_on and not st.session_state.get('_or_demo'):
        st.session_state.patient_cases = _or_board_demo()
        st.session_state['_or_demo'] = True
        if _is_demo_instance:
            # 🖥️ ดันเคสสาธิตขึ้นบอร์ดกลาง (schema demo) ทันที —
            #    จอญาติ/จอห้อง demo เห็นภายในรอบ refresh ถัดไป
            st.session_state['_board_dirty_ids'] = set()   # ชุดใหม่ทั้งกระดาน = overlay ทั้งหมด
            _save_board_snapshot(st.session_state.patient_cases)
        _rerun_board()
    if (not _demo_on) and st.session_state.get('_or_demo'):
        st.session_state.patient_cases = []
        st.session_state['_or_demo'] = False
        if _is_demo_instance:
            # 🖥️ ปิดสาธิต = ล้างบอร์ดกลาง demo ด้วย (จอญาติ/จอห้องกลับเป็นว่าง)
            try:
                from main_or_db import clear_board_state
                clear_board_state(_now().date().isoformat())
            except Exception as _cx:
                print(f"[demo] ล้างบอร์ดกลางล้มเหลว: {_cx}")
            try:
                _os.remove(_SNAPSHOT_PATH)   # กัน fallback ไฟล์ local คืนชีพเคสสาธิต
            except Exception:
                pass
            st.session_state['_board_base_version'] = 0
        _rerun_board()
    if st.session_state.get('_or_demo'):
        # 🎬 โหมดสาธิต: UI เหมือนโหมดจริงทุกอย่าง — เหลือชิปจาง ๆ กันสับสนเท่านั้น
        st.markdown(
            '<div style="text-align:right;margin:-4px 0 2px;">'
            '<span style="font-size:var(--fs-meta);color:#b6c2cf;border:1px solid #eef2f6;'
            'border-radius:999px;padding:4px 14px;">สาธิต · ไม่บันทึกจริง</span></div>',
            unsafe_allow_html=True)
    else:
        # 🧪 มีเคสทดสอบ (อัปโหลดแบบติ๊กโหมดทดสอบ) ปนบนบอร์ด — เตือนจาง ๆ
        #    ให้ทุกเครื่องที่เปิดบอร์ดรู้ว่าไม่ใช่ผู้ป่วยจริง (เคสพวกนี้ไม่เขียน DB วิจัย)
        _n_test = sum(1 for _c in st.session_state.patient_cases if _c.get('_demo'))
        if _n_test:
            st.markdown(
                f'<div style="text-align:right;margin:-4px 0 2px;">'
                f'<span style="font-size:var(--fs-meta);color:#9a6700;border:1px solid #fdf3dd;'
                f'background:#fffcf3;border-radius:999px;padding:4px 14px;">'
                f'🧪 เคสทดสอบ {_n_test} เคสบนบอร์ด · ไม่บันทึกจริง · '
                f'ลบที่ ⚙️ ล้างกระดาน</span></div>',
                unsafe_allow_html=True)

    _demo_active = bool(st.session_state.get('_or_demo'))

    # ❓ วิธีใช้ (UX audit 3 ก.ค. 2026)
    def _board_help_md():
        st.markdown(
            "แผนการไหลของผู้ป่วย (Patient work flow) เมื่อมารับการผ่าตัด\n\n"
            "1. ผู้ป่วยมาถึงห้องรับ-ส่ง → กด **รับเข้า**\n"
            "2. ผู้ป่วยเข้าห้องผ่าตัด → กด **เข้าห้อง** "
            "(ห้องที่มีเคสผ่าอยู่ ปุ่มจะกดไม่ได้จนกว่าเคสก่อนหน้าออกจากห้อง)\n"
            "3. ผ่าเสร็จ → เลือกปลายทาง: **เสร็จ → รับ-ส่ง** หรือ **เสร็จ → พักฟื้น**\n"
            "4. ผู้ป่วยกลับตึก/กลับบ้าน → กด **จำหน่าย**\n\n"
            "- กดพลาด? ปุ่ม **↩️** ท้ายแถวย้อนกลับได้หนึ่งขั้น\n"
            "- **✏️** = แก้เวลาทำนายการใช้ห้องหรือย้ายห้อง ตัวเลข AI เป็นค่าประมาณ "
            "พยาบาลปรับเวลาได้เสมอ\n"
            "- **จาก N เคส** ใต้ค่า AI = ทำนายจากเคสใกล้เคียงกี่เคส ยิ่งมากยิ่งน่าเชื่อถือ\n"
            "- หน้าจออัปเดตเองทุก 30 วินาที — **ไม่ต้องกด F5** "
            "(อยากดึงข้อมูลทันทีกด 🔄 รีเฟรช มุมขวาบน)\n\n"
            "---\n"
            "**ตัวเลขใต้ค่าทำนาย อ่านอย่างไร**\n\n"
            "1. **จาก N เคส** — แบบจำลองทำนายโดยอ้างอิงเคสหัตถการใกล้เคียง"
            "จำนวนกี่เคสในข้อมูลที่ใช้พัฒนา (พ.ศ. 2564–2566) ยิ่งมากยิ่งหนักแน่น · "
            "*ไม่มีเคสใกล้เคียง* = ทำนายจากค่ากลาง ควรตรวจสอบและปรับด้วย ✏️\n"
            "2. **ช่วง 90%** (เช่น ช่วง 29–98 น.) — เคสลักษณะนี้ราว 9 ใน 10 เคส"
            "จะใช้เวลาจริงอยู่ในช่วงนี้ (คำนวณด้วยวิธี conformal prediction "
            "สอบเทียบกับเคสจริง พ.ศ. 2567)\n"
            "   - *ช่วงแคบ* = เวลาค่อนข้างแน่นอน วางแผนต่อเคสได้มั่นใจ\n"
            "   - *ช่วงกว้าง* = เวลาแกว่งได้มาก ควรเผื่อเวลาและติดตามใกล้ชิด\n\n"
            "พยาบาลสามารถปรับเวลาทับค่าที่ AI ทำนายได้เสมอ (✏️) "
            "และระบบบันทึกทั้งสองค่าไว้เปรียบเทียบ")

    # ---------- 🧰 เครื่องมือ — มุคกี้สั่ง 5 ส.ค. 2026: ยุบ 3 แถวเหลือแถวเดียว ----------
    #    (อัปโหลดใช้แค่ตอนเช้า · เพิ่มเคส/วิธีใช้นาน ๆ ครั้ง) คืนพื้นที่ให้ KPI เด่นขึ้น
    #    🚪 โหมดจอประจำห้อง: เหลือเฉพาะแท็บวิธีใช้ — อัปโหลด/เพิ่มเคส = งานจอรับ-ส่ง
    if not _room_scope_board:
        with st.expander("🧰 เครื่องมือ : อัปโหลดตารางวันนี้ · เพิ่มเคส · วิธีใช้บอร์ด",
                         expanded=False):
            _tb_up, _tb_add, _tb_help = st.tabs(
                ["📤 อัปโหลดตารางวันนี้ (CSV/Excel)", "➕ เพิ่มเคส (Manual)",
                 "❓ วิธีใช้บอร์ด"])
            with _tb_up:
                render_csv_upload(bare=True)
            with _tb_add:
                _render_add_case_form(_demo_active)
            with _tb_help:
                _board_help_md()
    else:
        with st.expander("❓ วิธีใช้บอร์ดตารางผ่าตัด", expanded=False):
            _board_help_md()

    # ---------- empty state ----------
    if not cases:
        # 🧪 ข้อความหน้าว่างต่างกันตามบริบท — production ไม่พูดถึงโหมดสาธิตอีกต่อไป
        if _room_scope_board:
            st.info("ยังไม่มีเคสบนบอร์ดวันนี้ — รอจอห้องรับ-ส่งอัปโหลดตารางผ่าตัด "
                    "เคสจะขึ้นที่นี่อัตโนมัติ")
        elif _is_demo_instance:
            st.info("ยังไม่มีเคสบนบอร์ดวันนี้\n\n"
                    "- อยากลองใช้ก่อน → กดปุ่ม **🎬 เปิดโหมดสาธิต** ด้านบน "
                    "(ข้อมูลตัวอย่าง ไม่บันทึกจริง)\n"
                    "- หรืออัปโหลดไฟล์ทดสอบที่ **🧰 เครื่องมือ** ด้านบน "
                    "แท็บ 📤 อัปโหลดตารางวันนี้")
        else:
            st.info("ยังไม่มีเคสบนบอร์ดวันนี้\n\n"
                    "- อัปโหลดตารางจาก HIS ที่ **🧰 เครื่องมือ** ด้านบน "
                    "แท็บ 📤 อัปโหลดตารางวันนี้ (แนะนำไฟล์ Excel)\n"
                    "- หรือเพิ่มเคสเองที่แท็บ **➕ เพิ่มเคส (Manual)**")
        return

    # ---------- counters ----------
    n_not = sum(1 for c in cases if c['status'] == 'not_arrived')
    n_hold = sum(1 for c in cases if c['status'] == 'holding_pre')
    n_inor = sum(1 for c in cases if c['status'] == 'in_or')
    n_post = sum(1 for c in cases if c['status'] in ('holding_post', 'recovery'))
    n_done = sum(1 for c in cases if c['status'] == 'discharged')

    # 🎨 KPI การ์ดใหญ่ (มุคกี้สั่ง 5 ส.ค. 2026): เลขเด่น อ่านข้ามห้องได้
    #    ป้ายสถานะใช้สีชุดเดียวกับชิปบนบอร์ด · ไม่มีไอคอน (เรนเดอร์ไม่เข้าชุด)
    _KPI = [('ยังไม่มา', n_not, '#64748b', '#f1f5f9'),
            ('รอผ่าตัด', n_hold, '#9a6700', '#fdf3dd'),
            ('ในห้องผ่าตัด', n_inor, '#0f6e56', '#e1f5ee'),
            ('รอจำหน่าย', n_post, '#1565c0', '#e3f0fb'),
            ('จำหน่าย', n_done, '#475569', '#eceff3')]
    st.markdown(
        '<div style="display:flex;gap:12px;margin:6px 0 12px;">'
        + ''.join(
            f'<div style="flex:1;background:#ffffff;border:1px solid #eef2f6;'
            f'border-radius:14px;padding:14px 16px 12px;">'
            f'<span style="display:inline-block;background:{_bg};color:{_fg};'
            f'border-radius:10px;padding:4px 12px;font-size:var(--fs-meta);'
            f'font-weight:600;white-space:nowrap;">{_lb}</span>'
            f'<div style="font-size:32px;font-weight:800;color:#0f172a;'
            f'line-height:1.15;margin-top:6px;">{_v}</div></div>'
            for _lb, _v, _fg, _bg in _KPI)
        + '</div>', unsafe_allow_html=True)

    # ---------- action handlers ----------
    # (มี guard กันกดรัว/กดซ้ำ — ถ้าสถานะเปลี่ยนไปแล้วจากคลิกก่อนหน้า ไม่ทำซ้ำ)
    def _rlog(c):
        """📊 upsert ตารางวิจัยถาวร research_case_log (waiting time + AI vs actual
        + override) — fail-safe: พังก็เงียบ ไม่กระทบบอร์ด · เคส _demo ถูกข้ามในตัว"""
        try:
            from research_log import log_case_state
            log_case_state(c)
        except Exception as _rx:
            print(f"[research_log] ข้าม: {_rx}")

    def _do_arrive(idx):
        if cases[idx].get('status') != 'not_arrived':
            return  # กดซ้ำ/สถานะเปลี่ยนแล้ว — ไม่ทำซ้ำ
        cases[idx]['status'] = 'holding_pre'
        cases[idx]['time_arrived_holding'] = _now()
        _rlog(cases[idx])               # 📊 จุดเริ่มนาฬิกา waiting time
        _mark_board_dirty(cases[idx])   # CR-2: เครื่องนี้แก้จริง → ค่อยเซฟ + กันถูกดึงทับ
        _toast_ok("รับเข้าแล้ว ✓")
        _rerun_board()

    def _do_enter(idx, R):
        if cases[idx].get('status') != 'holding_pre':
            return  # กันกดรัว
        # 🚫 กันเข้าห้องที่ถูก "ปิด" ในหน้าตั้งค่า — เคสที่ schedule ผูกห้องปิดมา ก็เข้าไม่ได้
        if R and R not in {_r for _r, _ in _enabled_room_options()}:
            _toast_err_sound()
            st.warning(f"ห้อง {_loc(cases[idx])} ถูกปิดอยู่ (ตั้งค่า) — "
                       f"เปิดใช้งานห้องในหน้า ⚙️ ตั้งค่า ก่อน หรือเลือกห้องอื่น")
            return
        # 🚫 defense-in-depth: กันห้องซ้ำแม้ปุ่มจะ guard อยู่แล้ว (เผื่อเรียกตรง)
        if R and any(_c.get('status') == 'in_or' and _rid(_c) == R
                     for _c in cases):
            _toast_err_sound()
            st.warning(f"ห้อง {_loc(cases[idx])} มีเคสกำลังผ่าอยู่ — เข้าห้องไม่ได้")
            return
        now = _now()
        cases[idx]['status'] = 'in_or'
        cases[idx]['or_room_assigned'] = R
        cases[idx]['time_entered_or'] = now
        _rk = R if R else 1
        _rm = st.session_state.or_rooms.setdefault(_rk, {
            'status': 'ว่าง', 'current_case': None, 'start_time': None,
            'predicted_time': None, 'override_time': None, 'is_emergency': False,
            'staff': {'scrub': '', 'circulating': ''},
            'name': room_label(R) if R else 'OR', 'specialty': ''})
        _rm['status'] = 'กำลังผ่าตัด'
        _rm['current_case'] = cases[idx]
        _rm['start_time'] = now
        _rm['predicted_time'] = cases[idx].get('effective_min', 30)
        st.session_state.statistics['total_cases'] += 1
        _rlog(cases[idx])               # 📊 ปิดนาฬิกา waiting time (ได้ wait_holding_min)
        _mark_board_dirty(cases[idx])   # CR-2
        _toast_ok("เข้าห้องแล้ว ✓")
        _rerun_board()

    def _do_finish(idx, R, dest):
        # 🏁 logic กลางย้ายไป apply_finish (2 ส.ค. 2026) — จอโฟกัส demo ใช้ร่วม
        if apply_finish(cases, idx, R, dest):
            _toast_ok("ผ่าเสร็จ ✓")
        _rerun_board()

    def _do_undo(idx):
        """ย้อนสถานะกลับหนึ่งขั้น (กันกดพลาด) — คืนค่าตัวนับ/ห้อง/history ให้ถูก."""
        c = cases[idx]
        s = c['status']
        if s == 'holding_pre':
            c['status'] = 'not_arrived'
            c['time_arrived_holding'] = None
        elif s == 'in_or':
            c['status'] = 'holding_pre'
            c['time_entered_or'] = None
            _rk = c.get('or_room_assigned') or 1
            st.session_state.or_rooms.setdefault(_rk, {}).update(
                {'status': 'ว่าง', 'current_case': None, 'start_time': None})
            st.session_state.statistics['total_cases'] = max(
                st.session_state.statistics['total_cases'] - 1, 0)
        elif s in ('holding_post', 'recovery'):
            # 🏁 logic กลางย้ายไป apply_undo_finish (2 ส.ค. 2026) — จอโฟกัสใช้ร่วม
            #    (rlog/dirty ที่ท้ายฟังก์ชันซ้ำกับใน apply = upsert เดิม ไม่มีผลข้างเคียง)
            apply_undo_finish(cases, idx)
        elif s == 'discharged':
            c['status'] = 'holding_post'
            c['time_discharged'] = None
        _rlog(c)               # 📊 undo แล้วเขียนสถานะล่าสุดทับ — ตารางวิจัยตรงกับบอร์ดเสมอ
        _mark_board_dirty(c)   # CR-2
        _toast_ok("ย้อนสถานะแล้ว ↩️")
        _rerun_board()

    # ---------- กระดานติดตาม (production tracking board) ----------
    from tracking_board import render_tracking_board
    render_tracking_board(cases, _do_arrive, _do_enter, _do_finish, _do_undo,
                          _loc, _rid, _tlabel, _sched_min,
                          room_opts=_enabled_room_options(),
                          mark_dirty=_mark_board_dirty)

    # 💾 บันทึก snapshot บอร์ดปัจจุบัน — เฉพาะตอน "เครื่องนี้เพิ่งแก้จริง" (CR-2)
    #    เลิกเซฟทุก rerun แล้ว → กัน rerun เฉย ๆ (เปิด popover/refresh) เขียนทับเครื่องอื่น
    # 🖥️ แอป DEMO: เซฟขึ้นบอร์ดกลางแม้อยู่โหมดสาธิต (ทุกจอ demo เห็นปุ่มที่กด)
    if (cases and (_is_demo_instance or not st.session_state.get('_or_demo'))
            and st.session_state.get('_board_dirty')):
        if _save_board_snapshot(cases):
            st.session_state['_board_dirty'] = False   # เซฟสำเร็จ = สะอาด รอบหน้าดึงผลรวมได้
        # เซฟล้ม → คง dirty ไว้: (1) กัน pull ทับงานที่ยังไม่ขึ้น DB (บรรทัด 495)
        # (2) rerun หน้า/tick หน้า จะ retry เซฟเองอัตโนมัติ · เตือนผู้ใช้เมื่อล้มติดกัน >2 (M-09)


# ============================================================================
# (page_statistics ถูกถอดออก 4 ก.ค. 2026 — ไม่ถูก route จากเมนูตั้งแต่ยุค sidebar
#  สถิติจริงย้ายไปหน้า "📈 สถิติย้อนหลัง" ใน main_or_admin นานแล้ว
#  ต้องการคืน → ดู git history ก่อน commit "chore: ตัดโค้ดตาย")
# ============================================================================

# ════════════════════════════════════════════════════════════════════
# 🚪🎯 จอห้องผ่าตัดแบบโฟกัส — ทดลองในแอป DEMO (มุคกี้เคาะ 3 ส.ค. 2026)
#    ตาม skill or-patient-tracking-dashboard: "one decision only" —
#    จอห้องเห็นเคสตัวเอง + ปุ่มปลายทาง 2 ปุ่มใหญ่ (Hick's + Fitts's Law)
#    production ยังใช้บอร์ด 3 แท็บเดิม · route เลือกที่ main_or_app
# ════════════════════════════════════════════════════════════════════
def page_room_focus(room_no):
    _room_focus_fragment(room_no)


@_fragment(run_every=30)
def _room_focus_fragment(room_no):
    from room_config import room_label
    from main_or_db import mask_patient_name
    _flush_toast()   # 🎨 โชว์ toast ที่ฝากไว้จากปุ่มรอบก่อน (demo)
    _flush_sound()   # 🔊 เล่นเสียงที่ฝากไว้จากปุ่มรอบก่อน (demo+production)

    # ดึงบอร์ดกลางทุกรอบ (จอนี้ไม่มีช่องพิมพ์ — ดึงได้เสมอ เว้นมีงานค้างยังไม่เซฟ)
    if not st.session_state.get('_board_dirty'):
        _shared = _load_board_snapshot()
        if _shared is not None:
            st.session_state.patient_cases = _shared
            st.session_state['_board_last_pull_wall'] = _now().strftime('%H:%M:%S')
    cases = st.session_state.patient_cases

    def _r(c):
        try:
            return int(float(c.get('room')))
        except (TypeError, ValueError):
            return None

    # Fitts's Law: เป้าใหญ่ กดถนัดแม้สวมถุงมือ
    # 🔤 9 ส.ค. 2026 (มุคกี้สั่ง): จอนี้ออกด่านเร็ว (?room=) ก่อนถึง main_or_app
    #    จะ inject_theme() ปกติ — การ์ด ✏️ แก้เวลา ใช้ widget เนทีฟ Streamlit
    #    (markdown/caption/number_input/form_submit_button) เลยหลุด floor 18px
    #    ของแอป ต้องกำหนดเองที่นี่ตรง ๆ
    # 💜 ปุ่ม ห้องพักฟื้น: สีม่วงอ่อนคู่เดียวกับชิปสถานะบนบอร์ดวันนี้
    #    (_STATUS_META['recovery'] ใน tracking_board.py = #6b21a8 บนพื้น #edd2ff)
    st.markdown("""<style>
    div[data-testid="stButton"] > button {height:76px; font-size:22px; font-weight:700;}
    .st-key-rf_fin_rec button {
        background-color:#edd2ff !important; color:#6b21a8 !important;
        border-color:#edd2ff !important;
    }
    div[data-testid="stNumberInput"] input {font-size:18px !important;}
    div[data-testid="stFormSubmitButton"] button {font-size:18px !important; height:56px;}
    </style>""", unsafe_allow_html=True)

    st.markdown(f"### 🚪 {room_label(room_no)}")

    cur = next((i for i, c in enumerate(cases)
                if c.get('status') == 'in_or' and _r(c) == room_no), None)

    if cur is not None:
        c = cases[cur]
        eff = int(c.get('effective_min') or c.get('ai_predicted_min')
                  or c.get('predicted_min') or 30)
        ent = c.get('time_entered_or')
        elapsed = (max(int((_now() - ent).total_seconds() / 60), 0)
                   if (ent is not None and hasattr(ent, 'hour')) else 0)
        over = elapsed > eff
        pct = min(int(elapsed / max(eff, 1) * 100), 100)
        chip = (('<span style="background:#FBE9E8;color:#A32D2D;border-radius:999px;'
                 'padding:5px 18px;font-size:18px;font-weight:700;">เกินเวลา</span>')
                if over else
                ('<span style="background:#E1F5EE;color:#085041;border-radius:999px;'
                 'padding:5px 18px;font-size:18px;font-weight:700;">กำลังผ่า</span>'))
        bar_color = '#A32D2D' if over else '#1D9E75'
        st.markdown(
            f'<div style="background:#fff;border:2px solid #1D9E75;border-radius:16px;'
            f'padding:20px 24px;margin-bottom:14px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-size:26px;font-weight:800;color:#0f172a;">'
            f'{mask_patient_name(c.get("name") or "-")}</span>{chip}</div>'
            f'<div style="font-size:18px;color:#475569;margin-top:4px;">'
            f'{(c.get("procedure") or "-")}</div>'
            f'<div style="background:#eef2f6;height:12px;border-radius:6px;'
            f'margin:16px 0 8px;overflow:hidden;">'
            f'<div style="background:{bar_color};height:100%;width:{pct}%;'
            f'border-radius:6px;transition:width 1s ease;"></div></div>'
            f'<div style="display:flex;justify-content:space-between;font-size:18px;'
            f'color:#475569;"><span>ผ่าไป {elapsed} นาที</span>'
            f'<span>คาดการณ์ ~{eff} นาที</span></div>'
            f'</div>', unsafe_allow_html=True)
        # ✏️ แก้เวลาคาดการณ์ใช้ห้อง — ย้ายมาอยู่เหนือปุ่มผ่าเสร็จ (9 ส.ค. 2026
        #    มุคกี้สั่ง): แก้ระหว่างเคสยังดำเนินอยู่ ก่อนกดปิดจ็อบ — ไล่ตามลำดับ
        #    เหตุการณ์จริง ดูเคส → ปรับเวลาถ้าจำเป็น → กดเสร็จ → ดูคิวถัดไป
        #    ทั้ง demo และ production — บันทึกเวลาแล้วดันขึ้นบอร์ดกลางทันที
        _ce = cases[cur]
        _eff0 = int(_ce.get('effective_min') or _ce.get('ai_predicted_min')
                    or _ce.get('predicted_min') or 30)
        with st.container(border=True):
            _ecol1, _ecol2 = st.columns([3, 2])
            with _ecol1:
                st.markdown('<span style="font-size:18px;font-weight:600;'
                             'color:#0f172a;">✏️ แก้เวลาคาดการณ์ใช้ห้อง</span>',
                             unsafe_allow_html=True)
                st.markdown('<span style="font-size:18px;color:#64748b;">'
                             'แก้ได้เฉพาะเคสที่กำลังผ่าของห้องนี้</span>',
                             unsafe_allow_html=True)
            with _ecol2:
                with st.form("rf_ov_form", border=False):
                    _fcol1, _fcol2 = st.columns([3, 2])
                    with _fcol1:
                        _new_t = st.number_input("นาที", min_value=5, max_value=600,
                                                 value=_eff0, key="rf_ov_min",
                                                 label_visibility="collapsed")
                    with _fcol2:
                        _sv = st.form_submit_button("💾 บันทึก", width='stretch')
        if _sv and int(_new_t) != _eff0:
            # 🔗 ทางเดินเดียวกับ ✏️ บนบอร์ดหลัก: override + log + ขึ้นบอร์ดกลาง
            _ce['user_override_min'] = int(_new_t)
            _ce['effective_min'] = int(_new_t)
            try:
                from main_or_db import log_override
                log_override(_ce, int(_new_t))
            except Exception as _ex:
                print(f"[override_log] log_override ล้มเหลว: {_ex}")
            _save_board_snapshot(cases)
            st.session_state['_board_dirty'] = False
            _toast_ok("บันทึกเวลาแล้ว ✓")
            _rerun_board()

        # 🔤 9 ส.ค. 2026: font-size:18px ตรง ๆ (จอนี้ไม่ผ่าน inject_theme())
        #    + แก้ em dash → ":" ตามกติกา UI (นร 0106 ไม่เกี่ยว แต่กติกาแอปเอง)
        st.markdown('<span style="font-size:18px;font-weight:600;color:#0f172a;">'
                     'ผ่าเสร็จ : ส่งผู้ป่วยไปที่</span>', unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        if b1.button("🚪 ห้องรับ-ส่ง", key="rf_fin_hold", width='stretch',
                     type='primary'):
            if apply_finish(cases, cur, room_no, 'ห้องรับ-ส่ง'):
                _save_board_snapshot(cases)
                st.session_state['_board_dirty'] = False
                _toast_ok("ผ่าเสร็จ ✓ → ห้องรับ-ส่ง")
            _rerun_board()
        if b2.button("🛏️ ห้องพักฟื้น", key="rf_fin_rec", width='stretch'):
            if apply_finish(cases, cur, room_no, 'ห้องพักฟื้น'):
                _save_board_snapshot(cases)
                st.session_state['_board_dirty'] = False
                _toast_ok("ผ่าเสร็จ ✓ → ห้องพักฟื้น")
            _rerun_board()
    else:
        nxt = [c for c in cases if _r(c) == room_no
               and c.get('status') in ('not_arrived', 'holding_pre')]
        if nxt:
            n0 = sorted(nxt, key=lambda c: (
                0 if c.get('status') == 'holding_pre' else 1,
                c.get('ororder') or 999))[0]
            _st_txt = ('พร้อมแล้วที่ห้องรับ-ส่ง' if n0.get('status') == 'holding_pre'
                       else 'ยังไม่มา')
            st.info(f"ห้องว่าง — คิวถัดไป: **{mask_patient_name(n0.get('name') or '-')}** · "
                    f"{n0.get('procedure', '-')} ({_st_txt})\n\n"
                    f"จอรับ-ส่งเป็นผู้กด 'เข้าห้อง' · คิวของห้องนี้เหลือ {len(nxt)} เคส")
        else:
            st.success("ห้องว่าง — ไม่มีเคสค้างของห้องนี้แล้ววันนี้ 🎉")

    # 🕓 คิวรอของห้อง — เต็มความกว้าง อยู่ล่างสุด (9 ส.ค. 2026 มุคกี้สั่ง: ย้าย
    #    ออกจากคอลัมน์ขวาเดิมที่วางคู่กับแก้เวลา ทำให้หน้าจอเอียง สูงไม่เท่ากัน)
    st.markdown("---")
    _wait = [c for c in cases if _r(c) == room_no
             and c.get('status') in ('not_arrived', 'holding_pre')]
    st.markdown(f'<span style="font-size:18px;font-weight:600;color:#0f172a;">'
                f'🕓 คิวรอของ {room_label(room_no)} ({len(_wait)} เคส)</span>',
                unsafe_allow_html=True)
    if _wait:
        # 🔒 กติกาเดียวกับบอร์ดหลัก: โชว์ล็อกคิวเมื่อเลขคิวในห้อง "ไม่ซ้ำกัน"
        _ords = []
        for _x in cases:
            if _r(_x) != room_no or _x.get('is_tf'):
                continue
            try:
                _xo = int(_x.get('ororder'))
            except (TypeError, ValueError):
                continue
            if _xo and _xo != 99:
                _ords.append(_xo)
        _lock_ok = len(_ords) == len(set(_ords))

        def _skey(c):
            try:
                _sm = (int(c.get('sched_hour') or 8) * 60
                       + int(c.get('sched_min') or 0))
            except (TypeError, ValueError):
                _sm = 9999
            return (0 if c.get('status') == 'holding_pre' else 1,
                    _sm, c.get('ororder') or 999)

        _rows = []
        for _w in sorted(_wait, key=_skey):
            _t = ('TF' if _w.get('is_tf') else
                  f"{int(_w.get('sched_hour') or 8):02d}:"
                  f"{int(_w.get('sched_min') or 0):02d}")
            try:
                _o = int(_w.get('ororder'))
            except (TypeError, ValueError):
                _o = None
            _q = (f'🔒 คิว {_o} · ' if (_lock_ok and _o and _o != 99
                                        and not _w.get('is_tf')) else '')
            _ai = int(_w.get('effective_min') or _w.get('predicted_min') or 0)
            _ai_txt = f' · AI ~{_ai} นาที' if _ai else ''
            if _w.get('status') == 'holding_pre':
                _chip = ('<span style="background:#fdf3dd;color:#9a6700;'
                         'border-radius:10px;padding:4px 14px;font-size:18px;'
                         'white-space:nowrap;">รอผ่าตัด</span>')
            else:
                _chip = ('<span style="background:#f1f5f9;color:#64748b;'
                         'border-radius:10px;padding:4px 14px;font-size:18px;'
                         'white-space:nowrap;">ยังไม่มา</span>')
            _rows.append(
                f'<div style="display:flex;align-items:center;gap:10px;'
                f'border-top:1px solid #eef2f6;padding:9px 0;font-size:18px;">'
                f'<span style="color:#94a3b8;white-space:nowrap;">{_q}{_t}</span>'
                f'<span style="font-weight:600;color:#0f172a;white-space:nowrap;">'
                f'{mask_patient_name(_w.get("name") or "-")}</span>'
                f'<span style="color:#64748b;flex:1;min-width:0;overflow:hidden;'
                f'text-overflow:ellipsis;white-space:nowrap;">'
                f'{(_w.get("procedure") or "-")}{_ai_txt}</span>'
                f'{_chip}</div>')
        st.markdown(''.join(_rows), unsafe_allow_html=True)
        st.markdown('<span style="font-size:18px;color:#94a3b8;">'
                     'อ่านอย่างเดียว : การรับเข้า/เข้าห้อง กดที่จอรับ-ส่ง</span>',
                     unsafe_allow_html=True)
    else:
        st.markdown('<span style="font-size:18px;color:#64748b;">'
                     'ไม่มีเคสรอของห้องนี้แล้ววันนี้</span>', unsafe_allow_html=True)

    # ↩️ Forgiveness: เลิกทำการกดเสร็จล่าสุดของห้องนี้ (แก้กดพลาด/เลือกปลายทางผิด)
    done_last = next((i for i in range(len(cases) - 1, -1, -1)
                      if _r(cases[i]) == room_no
                      and cases[i].get('status') in ('holding_post', 'recovery')),
                     None)
    if done_last is not None:
        _cu = cases[done_last]
        if st.button(f"↩️ เลิกทำ — ดึง {mask_patient_name(_cu.get('name') or '-')} "
                     f"กลับเป็นกำลังผ่า", key="rf_undo"):
            if apply_undo_finish(cases, done_last):
                _save_board_snapshot(cases)
                st.session_state['_board_dirty'] = False
                _toast_ok("ย้อนสถานะแล้ว ↩️")
            _rerun_board()

    if st.session_state.get('_board_last_pull_wall'):
        st.caption(f"อัปเดตล่าสุด {st.session_state['_board_last_pull_wall']} · "
                   "ซิงก์อัตโนมัติทุก 30 วินาที")
