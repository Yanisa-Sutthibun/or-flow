# -*- coding: utf-8 -*-
"""
keepalive.py : ปลุกแอป OR Flow บน Streamlit Community Cloud ไม่ให้หลับ
═══════════════════════════════════════════════════════════════════
รันโดย .github/workflows/keepalive.yml ทุก 4 ชม. (มุกกี้สั่ง 6 พ.ย. 2026)
เปิดเบราว์เซอร์จริงเข้าแต่ละลิงก์ใน env KEEPALIVE_URLS (คั่นด้วยจุลภาค)
รอจนเห็นชิป "AI:" (แปลว่าแอปโหลดเสร็จและต่อ Supabase ได้) ถ้าไม่เห็นภายในเวลา
ที่กำหนดถือว่าปลุกไม่สำเร็จ → exit 1 ให้ GitHub แจ้งเตือน
ไม่มี token ในไฟล์นี้ ลิงก์ทั้งหมดมาจาก Secrets เท่านั้น
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

WAIT_SEC = 180          # Streamlit ตื่นจากหลับใช้ราว 60-120 วิ
# ข้อความที่แปลว่าแอปโหลดเสร็จและต่อ Supabase ได้ (เจออันใดอันหนึ่งพอ)
READY_TEXTS = ("AI:", "รีเฟรช", "จอประจำห้อง", "คิวรอของ")
# UA ของ Chrome ปกติ กัน Streamlit/Cloudflare ปฏิบัติกับ HeadlessChrome ต่างออกไป
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")


def _mask(url: str) -> str:
    """ซ่อน token ใน log"""
    return url.split("?")[0] + ("?..." if "?" in url else "")


def _all_text(page) -> str:
    """รวมข้อความจากทุก frame : *.streamlit.app เป็นหน้าห่อที่ฝังตัวแอปใน iframe
    อ่านแค่ body ชั้นนอกจะได้ค่าว่าง (เจอจริง 6 พ.ย. 2026)"""
    parts = []
    for fr in page.frames:
        try:
            parts.append(fr.inner_text("body"))
        except Exception:
            pass
    return "\n".join(parts)


def wake(page, url: str) -> bool:
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    deadline = time.time() + WAIT_SEC
    body = ""
    while time.time() < deadline:
        body = _all_text(page)
        if any(t in body for t in READY_TEXTS):
            return True
        if "เชื่อมต่อฐานข้อมูลไม่สำเร็จ" in body:
            print("  ✗ แอปขึ้น แต่ต่อ Supabase ไม่ได้ (โปรเจกต์หลับ?)")
            return False
        # ปุ่ม "Yes, get this app back up!" ของ Streamlit ตอนหลับลึก
        for fr in page.frames:
            try:
                btn = fr.get_by_role("button", name="Yes, get this app back up!")
                if btn.count() > 0:
                    btn.first.click()
                    print("  กดปุ่มปลุกของ Streamlit")
            except Exception:
                pass
        time.sleep(5)
    # หมดเวลา: พิมพ์ข้อความบนหน้าช่วยวินิจฉัย (ไม่มี token ในเนื้อหา)
    print("  หน้าที่เห็นตอนหมดเวลา:", " ".join(body.split())[:300] or "(ว่าง)")
    return False


def main() -> int:
    raw = os.environ.get("KEEPALIVE_URLS", "").strip()
    urls = [u.strip() for u in raw.split(",") if u.strip()]
    if not urls:
        print("ไม่มี KEEPALIVE_URLS ใน Secrets")
        return 1
    failed = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for url in urls:
            print("เปิด", _mask(url))
            page = browser.new_page(user_agent=USER_AGENT,
                                    viewport={"width": 1280, "height": 900})
            ok = False
            try:
                ok = wake(page, url)
            except Exception as e:
                print("  ✗ error:", e)
            finally:
                page.close()
            print("  ✓ ตื่นแล้ว" if ok else "  ✗ ปลุกไม่สำเร็จ")
            if not ok:
                failed.append(_mask(url))
        browser.close()
    if failed:
        print("ปลุกไม่สำเร็จ:", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
