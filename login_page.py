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

_SPRITE = '<svg class="bob" width="100" height="100" viewBox="0 0 25 25" shape-rendering="crispEdges" aria-hidden="true"><g><rect x="6" y="0" width="8" height="1" fill="#1F8A4C"></rect><rect x="4" y="1" width="12" height="1" fill="#1F8A4C"></rect><rect x="3" y="2" width="14" height="1" fill="#1F8A4C"></rect><rect x="3" y="3" width="14" height="1" fill="#1F8A4C"></rect><rect x="3" y="4" width="14" height="1" fill="#176E3E"></rect><rect x="3" y="5" width="1" height="1" fill="#6B4226"></rect><rect x="4" y="5" width="12" height="1" fill="#EBC9A6"></rect><rect x="16" y="5" width="1" height="1" fill="#6B4226"></rect><rect x="3" y="6" width="1" height="1" fill="#6B4226"></rect><rect x="4" y="6" width="1" height="1" fill="#EBC9A6"></rect><rect x="5" y="6" width="2" height="1" fill="#1E2A38"></rect><rect x="7" y="6" width="6" height="1" fill="#EBC9A6"></rect><rect x="13" y="6" width="2" height="1" fill="#1E2A38"></rect><rect x="15" y="6" width="1" height="1" fill="#EBC9A6"></rect><rect x="16" y="6" width="1" height="1" fill="#6B4226"></rect><rect x="3" y="7" width="1" height="1" fill="#6B4226"></rect><rect x="4" y="7" width="12" height="1" fill="#EBC9A6"></rect><rect x="16" y="7" width="1" height="1" fill="#6B4226"></rect><rect x="3" y="8" width="1" height="1" fill="#6B4226"></rect><rect x="4" y="8" width="12" height="1" fill="#8EDBC9"></rect><rect x="16" y="8" width="1" height="1" fill="#6B4226"></rect><rect x="3" y="9" width="1" height="1" fill="#6B4226"></rect><rect x="4" y="9" width="12" height="1" fill="#8EDBC9"></rect><rect x="16" y="9" width="1" height="1" fill="#6B4226"></rect><rect x="4" y="10" width="1" height="1" fill="#6CC5B2"></rect><rect x="5" y="10" width="10" height="1" fill="#8EDBC9"></rect><rect x="15" y="10" width="1" height="1" fill="#6CC5B2"></rect><rect x="8" y="11" width="4" height="1" fill="#EBC9A6"></rect><rect x="4" y="12" width="5" height="1" fill="#1E8A4E"></rect><rect x="9" y="12" width="2" height="1" fill="#176E3E"></rect><rect x="11" y="12" width="5" height="1" fill="#1E8A4E"></rect><rect x="3" y="13" width="6" height="1" fill="#1E8A4E"></rect><rect x="9" y="13" width="2" height="1" fill="#176E3E"></rect><rect x="11" y="13" width="6" height="1" fill="#1E8A4E"></rect><rect x="2" y="14" width="16" height="1" fill="#1E8A4E"></rect><rect x="18" y="14" width="1" height="1" fill="#A9D8F0"></rect><rect x="2" y="15" width="4" height="1" fill="#1E8A4E"></rect><rect x="6" y="15" width="2" height="1" fill="#145C33"></rect><rect x="8" y="15" width="4" height="1" fill="#1E8A4E"></rect><rect x="12" y="15" width="2" height="1" fill="#145C33"></rect><rect x="14" y="15" width="4" height="1" fill="#1E8A4E"></rect><rect x="18" y="15" width="1" height="1" fill="#A9D8F0"></rect><rect x="2" y="16" width="4" height="1" fill="#1E8A4E"></rect><rect x="6" y="16" width="2" height="1" fill="#145C33"></rect><rect x="8" y="16" width="4" height="1" fill="#1E8A4E"></rect><rect x="12" y="16" width="2" height="1" fill="#145C33"></rect><rect x="14" y="16" width="4" height="1" fill="#1E8A4E"></rect><rect x="2" y="17" width="1" height="1" fill="#A9D8F0"></rect><rect x="3" y="17" width="15" height="1" fill="#1E8A4E"></rect><rect x="2" y="18" width="1" height="1" fill="#A9D8F0"></rect><rect x="4" y="18" width="12" height="1" fill="#1E8A4E"></rect><rect x="4" y="19" width="12" height="1" fill="#1E8A4E"></rect></g><g class="fa"><rect x="4" y="20" width="5" height="1" fill="#1E8A4E"></rect><rect x="11" y="20" width="5" height="1" fill="#1E8A4E"></rect><rect x="4" y="21" width="5" height="1" fill="#1E8A4E"></rect><rect x="11" y="21" width="5" height="1" fill="#1E8A4E"></rect><rect x="4" y="22" width="5" height="1" fill="#1E8A4E"></rect><rect x="11" y="22" width="5" height="1" fill="#1E8A4E"></rect><rect x="4" y="23" width="5" height="1" fill="#1E8A4E"></rect><rect x="11" y="23" width="5" height="1" fill="#1E8A4E"></rect><rect x="3" y="24" width="6" height="1" fill="#FFFFFF"></rect><rect x="11" y="24" width="6" height="1" fill="#FFFFFF"></rect></g><g class="fb"><rect x="3" y="20" width="5" height="1" fill="#1E8A4E"></rect><rect x="11" y="20" width="5" height="1" fill="#1E8A4E"></rect><rect x="3" y="21" width="5" height="1" fill="#1E8A4E"></rect><rect x="11" y="21" width="5" height="1" fill="#1E8A4E"></rect><rect x="3" y="22" width="5" height="1" fill="#1E8A4E"></rect><rect x="11" y="22" width="5" height="1" fill="#1E8A4E"></rect><rect x="2" y="23" width="6" height="1" fill="#FFFFFF"></rect><rect x="11" y="23" width="5" height="1" fill="#1E8A4E"></rect><rect x="11" y="24" width="5" height="1" fill="#FFFFFF"></rect></g><g class="fc"><rect x="4" y="20" width="5" height="1" fill="#1E8A4E"></rect><rect x="12" y="20" width="5" height="1" fill="#1E8A4E"></rect><rect x="4" y="21" width="5" height="1" fill="#1E8A4E"></rect><rect x="12" y="21" width="5" height="1" fill="#1E8A4E"></rect><rect x="4" y="22" width="5" height="1" fill="#1E8A4E"></rect><rect x="12" y="22" width="5" height="1" fill="#1E8A4E"></rect><rect x="4" y="23" width="5" height="1" fill="#1E8A4E"></rect><rect x="12" y="23" width="6" height="1" fill="#FFFFFF"></rect><rect x="4" y="24" width="5" height="1" fill="#FFFFFF"></rect></g><g class="d1"><g class="steam"><rect x="20" y="4" width="1" height="1" fill="#AEB8C2"></rect><rect x="19" y="5" width="1" height="1" fill="#AEB8C2"></rect><rect x="20" y="6" width="1" height="1" fill="#AEB8C2"></rect></g><rect x="19" y="7" width="3" height="1" fill="#E6EBF0"></rect><rect x="18" y="8" width="5" height="1" fill="#E6EBF0"></rect><rect x="19" y="9" width="3" height="1" fill="#8B5A3C"></rect><rect x="19" y="10" width="3" height="1" fill="#E6EBF0"></rect><rect x="19" y="11" width="3" height="1" fill="#8B5A3C"></rect><rect x="19" y="12" width="3" height="1" fill="#8B5A3C"></rect><rect x="20" y="13" width="1" height="1" fill="#8B5A3C"></rect></g><g class="d2"><rect x="19" y="7" width="2" height="1" fill="#C9D3DD"></rect><rect x="18" y="8" width="2" height="1" fill="#E53935"></rect><rect x="20" y="8" width="2" height="1" fill="#1E63D6"></rect><rect x="18" y="9" width="1" height="1" fill="#E53935"></rect><rect x="19" y="9" width="1" height="1" fill="#FFD43B"></rect><rect x="20" y="9" width="2" height="1" fill="#1E63D6"></rect><rect x="18" y="10" width="2" height="1" fill="#E53935"></rect><rect x="20" y="10" width="1" height="1" fill="#FFD43B"></rect><rect x="21" y="10" width="1" height="1" fill="#1E63D6"></rect><rect x="18" y="11" width="1" height="1" fill="#E53935"></rect><rect x="19" y="11" width="2" height="1" fill="#FFD43B"></rect><rect x="21" y="11" width="1" height="1" fill="#1E63D6"></rect><rect x="18" y="12" width="2" height="1" fill="#E53935"></rect><rect x="20" y="12" width="2" height="1" fill="#1E63D6"></rect><rect x="19" y="13" width="2" height="1" fill="#C9D3DD"></rect></g><g class="d3"><rect x="21" y="6" width="1" height="1" fill="#F06292"></rect><rect x="21" y="7" width="1" height="1" fill="#F06292"></rect><rect x="20" y="8" width="1" height="1" fill="#F06292"></rect><rect x="18" y="9" width="5" height="1" fill="#E8F4FA"></rect><rect x="19" y="10" width="3" height="1" fill="#D8B48F"></rect><rect x="19" y="11" width="3" height="1" fill="#D8B48F"></rect><rect x="19" y="12" width="1" height="1" fill="#2B2B2B"></rect><rect x="20" y="12" width="1" height="1" fill="#D8B48F"></rect><rect x="21" y="12" width="1" height="1" fill="#2B2B2B"></rect><rect x="19" y="13" width="3" height="1" fill="#2B2B2B"></rect></g><g class="d4"><rect x="18" y="9" width="4" height="1" fill="#DDEFF7"></rect><rect x="18" y="10" width="1" height="1" fill="#DDEFF7"></rect><rect x="19" y="10" width="3" height="1" fill="#B5651D"></rect><rect x="22" y="10" width="2" height="1" fill="#DDEFF7"></rect><rect x="18" y="11" width="1" height="1" fill="#DDEFF7"></rect><rect x="19" y="11" width="3" height="1" fill="#B5651D"></rect><rect x="22" y="11" width="1" height="1" fill="#DDEFF7"></rect><rect x="24" y="11" width="1" height="1" fill="#DDEFF7"></rect><rect x="18" y="12" width="1" height="1" fill="#DDEFF7"></rect><rect x="19" y="12" width="3" height="1" fill="#B5651D"></rect><rect x="22" y="12" width="2" height="1" fill="#DDEFF7"></rect><rect x="19" y="13" width="3" height="1" fill="#DDEFF7"></rect></g></svg>'

_TIPS = ['<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>OR Flow ใช้ AI ทำนายเวลาการใช้ห้องผ่าตัด ตั้งแต่ผู้ป่วยเข้าห้อง (wheel-in) จนออกจากห้อง (wheel-out)', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>Turnover time คือ ช่วงเวลาตั้งแต่ผู้ป่วยเคสก่อนออกจากห้อง จนผู้ป่วยเคสถัดไปเข้าห้องเดียวกัน (นับเฉพาะช่วง 1 ถึง 90 นาที)', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>Utilization คือ ร้อยละการใช้ห้องผ่าตัดในเวลาราชการ คำนวณจาก เวลาที่ผู้ป่วยอยู่ในห้องช่วง 08:00 ถึง 16:00 ÷ (จำนวนห้องที่ใช้ × 480 นาที) × 100', '<span style="font-weight: 700; color: #1658B8">วิธีใช้ 1/5 : </span>ตอนเช้า อัปโหลดตารางผ่าตัดจาก HIS ที่ปุ่ม ⋯ มุมขวาบน', '<span style="font-weight: 700; color: #1658B8">วิธีใช้ 2/5 : </span>ผู้ป่วยมาถึงห้องรับ-ส่ง กด รับเข้า', '<span style="font-weight: 700; color: #1658B8">วิธีใช้ 3/5 : </span>ผู้ป่วยเข้าห้องผ่าตัด กด เข้าห้อง', '<span style="font-weight: 700; color: #1658B8">วิธีใช้ 4/5 : </span>ผ่าตัดเสร็จ กด เสร็จ แล้วเลือก ไปห้องรับ-ส่ง หรือ ไปห้องพักฟื้น', '<span style="font-weight: 700; color: #1658B8">วิธีใช้ 5/5 : </span>ผู้ป่วยกลับตึกหรือกลับบ้าน กด จำหน่าย', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>หน้าจออัปเดตเองทุก 30 วินาที ไม่ต้องกด F5', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>อยากเห็นข้อมูลล่าสุดทันที กดปุ่ม 🔄 รีเฟรช มุมขวาบนได้เลย', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>กดพลาดไม่ต้องตกใจ กด ✏️ ท้ายแถว แล้วเลือก เลิกทำ ย้อนกลับได้หนึ่งขั้น', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>ห้องที่ยังมีเคสผ่าตัดอยู่ จะกดเข้าห้องเคสถัดไปไม่ได้ จนกว่าเคสก่อนหน้าจะออกจากห้อง', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>เวลาที่ AI ทำนายเป็นค่าประมาณ พยาบาลกด ✏️ ปรับเองได้เสมอ', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>ระบบเก็บทั้งเวลาที่ AI ทำนายและเวลาที่พยาบาลปรับ ไว้เทียบกันในงานวิจัย', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>"จาก N เคส" ใต้ค่าทำนาย ยิ่งเลขมาก ยิ่งน่าเชื่อถือ', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>ช่วงเวลาที่ทำนายยิ่งกว้าง แปลว่าเคสนั้นเวลาแกว่งได้มาก ควรเผื่อเวลาไว้', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>แถบคิวถัดไปบอกเวลาที่ควรไปตามผู้ป่วยมารอ ผู้ป่วยจะได้ไม่ต้องรอหน้าห้องเกิน 1 ชั่วโมง', '<span style="font-weight: 700; color: #0B7A6C">รู้หรือไม่ : </span>ถ้าในห้องกดกระดิ่ง 🔔 แถบจะเป็นสีเขียวพร้อมเสียงติ๊ง ไปตามผู้ป่วยได้ทันที']

_CSS = '.orl-panel{background:#10263D;color:#FFFFFF;border-radius:20px;padding:36px 36px 28px;display:flex;flex-direction:column;gap:20px;margin-top:24px}.orl-brand{display:flex;align-items:center;gap:12px;font-size:22px;font-weight:700}.orl-logo{width:44px;height:44px;border-radius:12px;background:rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center}.orl-h1{font-size:34px;font-weight:700;line-height:1.35;margin-top:8px}.orl-sub{font-size:17px;line-height:1.7;color:#C9D6E3}.orl-box{display:flex;flex-direction:column;gap:16px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:20px 20px 0;overflow:hidden}.orl-boxh{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;font-size:15px}.orl-boxh span{font-size:13px;color:#A9BBCC}.orl-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.orl-cell{display:flex;flex-direction:column;gap:4px;background:rgba(255,255,255,.06);border-radius:12px;padding:12px}.orl-cl{display:flex;align-items:center;gap:6px;font-size:13px;color:#DCE7F2}.orl-cl span{width:8px;height:8px;border-radius:4px;display:inline-block}.orl-num{font-size:32px;font-weight:700;line-height:1.2}.orl-stage{position:relative;height:210px;margin:0 -20px;border-top:1px dashed rgba(255,255,255,.14);background:rgba(255,255,255,.03)}.orl-bubble{position:absolute;left:20px;right:20px;top:14px;background:#FFFFFF;border:2px solid #0B1A29;border-radius:4px;padding:10px 14px;box-shadow:4px 4px 0 rgba(0,0,0,.25)}.orl-tips{display:grid;font-size:14px;line-height:1.55;color:#12212E}.orl-tail{position:absolute;left:26px;bottom:-7px;width:10px;height:10px;background:#FFFFFF;border-right:2px solid #0B1A29;border-bottom:2px solid #0B1A29;transform:rotate(45deg)}.orl-floor{position:absolute;left:0;right:0;bottom:14px;height:2px;background:rgba(255,255,255,.16)}.orl-foot{font-size:13px;line-height:1.6;color:#A9BBCC}.orl-fh{margin:8px 0 6px}.orl-fh1{font-size:28px;font-weight:700;color:#12212E}.orl-fh2{font-size:15px;color:#5B6B7B;margin-top:4px}@media (max-width:640px){.orl-h1{font-size:26px}.orl-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.orl-panel{padding:24px}}.walker{position:absolute;left:0;bottom:14px;width:100px;height:100px;animation:orfMove 14s linear infinite alternate}.flip{width:100px;height:100px;animation:orfFlip 28s steps(1,end) infinite}.fa{opacity:1;animation:orfFa .6s steps(1,end) infinite}.fb{opacity:0;animation:orfFb .6s steps(1,end) infinite}.fc{opacity:0;animation:orfFc .6s steps(1,end) infinite}.bob{animation:orfBob .3s steps(1,end) infinite}@keyframes orfMove{from{left:0}to{left:calc(100% - 100px)}}@keyframes orfFlip{0%{transform:scaleX(1)}50%{transform:scaleX(-1)}100%{transform:scaleX(-1)}}@keyframes orfFa{0%{opacity:1}25%{opacity:0}50%{opacity:1}75%{opacity:0}100%{opacity:0}}@keyframes orfFb{0%{opacity:0}25%{opacity:1}50%{opacity:0}100%{opacity:0}}@keyframes orfFc{0%{opacity:0}75%{opacity:1}100%{opacity:1}}@keyframes orfBob{0%{transform:translateY(0)}50%{transform:translateY(-1px)}100%{transform:translateY(-1px)}}.d1{opacity:1;animation:orfD1 56s steps(1,end) infinite}.d2,.d3,.d4{opacity:0}.d2{animation:orfD2 56s steps(1,end) infinite}.d3{animation:orfD3 56s steps(1,end) infinite}.d4{animation:orfD4 56s steps(1,end) infinite}.steam{animation:orfSteam 1.2s steps(1,end) infinite}@keyframes orfD1{0%{opacity:1}25%{opacity:0}100%{opacity:0}}@keyframes orfD2{0%{opacity:0}25%{opacity:1}50%{opacity:0}100%{opacity:0}}@keyframes orfD3{0%{opacity:0}50%{opacity:1}75%{opacity:0}100%{opacity:0}}@keyframes orfD4{0%{opacity:0}75%{opacity:1}100%{opacity:1}}@keyframes orfSteam{0%{transform:translateY(0);opacity:.9}50%{transform:translateY(-1px);opacity:.5}100%{opacity:.5}}.tip{grid-area:1/1;opacity:0;animation:orfTip 144s steps(1,end) infinite}@keyframes orfTip{0%{opacity:1}5.556%{opacity:0}100%{opacity:0}}@media (prefers-reduced-motion: reduce){.tip{animation:none}.tip0{opacity:1}.walker,.flip,.fa,.fb,.fc,.bob,.d1,.d2,.d3,.d4,.steam{animation:none}}'

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
