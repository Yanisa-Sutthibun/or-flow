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
READY_TEXT = "AI:"      # ชิปแบบจำลองที่ขึ้นทุกจอเมื่อโหลดเสร็จ


def _mask(url: str) -> str:
    """ซ่อน token ใน log"""
    return url.split("?")[0] + ("?..." if "?" in url else "")


def wake(page, url: str) -> bool:
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    deadline = time.time() + WAIT_SEC
    while time.time() < deadline:
        try:
            body = page.inner_text("body")
        except Exception:
            body = ""
        if READY_TEXT in body:
            return True
        if "เชื่อมต่อฐานข้อมูลไม่สำเร็จ" in body:
            print("  ✗ แอปขึ้น แต่ต่อ Supabase ไม่ได้ (โปรเจกต์หลับ?)")
            return False
        # ปุ่ม "Yes, get this app back up!" ของ Streamlit ตอนหลับลึก
        try:
            btn = page.get_by_role("button", name="Yes, get this app back up!")
            if btn.count() > 0:
                btn.first.click()
                print("  กดปุ่มปลุกของ Streamlit")
        except Exception:
            pass
        time.sleep(5)
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
            page = browser.new_page()
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
