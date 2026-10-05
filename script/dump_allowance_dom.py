"""Debug-only: dump DOM around the new "手当" (allowance) column of the attendance sheet.

Nothing is registered. Dialogs opened here are closed with Cancel/Escape.
Output: log/allowance_dom_<YYYY-MM-DD>.html (+ _frame.html with the whole iframe content)
"""

import re
import sys
import json
import datetime
import argparse
from html import escape
from logging import StreamHandler, basicConfig, getLogger
from pathlib import Path

import nest_asyncio
from playwright.sync_api import sync_playwright
from playwright.sync_api._generated import *

import const
import module_auto_timestamp as modat

nest_asyncio.apply()

parser = argparse.ArgumentParser()
parser.add_argument("-D", "--date", help="Target date in YYYY-MM-DD format (default: today)")
parser.add_argument("-L", "--last_month", action="store_true", help="open the attendance sheet for last month")
args = parser.parse_args()

TIMEOUT_DEFAULT = const.TIMEOUT_DEFAULT
TIMEOUT_LOGIN = const.TIMEOUT_LOGIN
TIMEOUT_LOADING = const.TIMEOUT_LOADING
ALLOWANCE_CHAR = "手当"
LOG_DIR = Path(__file__).parent / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = getLogger(__name__)
logger.setLevel("DEBUG")

# JS: elements that look like a dialog and are currently visible
JS_VISIBLE_DIALOGS = """
() => {
  const sel = '[role=dialog], .dijitDialog, [id*="dialog"], [id*="Dialog"], [class*="dialog"], [class*="Dialog"], [class*="popup"], [class*="Popup"]';
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  return Array.from(document.querySelectorAll(sel)).filter(vis).map(el => el.outerHTML);
}
"""

# JS: visible checkboxes and their closest dialog-like ancestor
JS_VISIBLE_CHECKBOXES = """
() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  return Array.from(document.querySelectorAll('input[type=checkbox]')).filter(vis).map(cb => {
    const box = cb.closest('[role=dialog], .dijitDialog, [id*="dialog"], [id*="Dialog"], table') || cb.parentElement;
    return { checkbox: cb.outerHTML, label: (cb.closest('label') || cb.parentElement).innerText, container: box.outerHTML };
  });
}
"""

# JS: elements whose own text is exactly "手当" (header cell candidates)
JS_ALLOWANCE_HEADERS = """
(word) => Array.from(document.querySelectorAll('th, td, div, span')).filter(el =>
    el.innerText && el.innerText.trim() === word).map(el => {
  const cell = el.closest('th, td');
  const row = el.closest('tr');
  return { el: el.outerHTML, cellIndex: cell ? cell.cellIndex : -1, row: row ? row.outerHTML : '' };
})
"""


def section(title: str, body: str) -> str:
    return f"<h2>{escape(title)}</h2>\n<pre>{escape(body)}</pre>\n"


if __name__ == "__main__":
    basicConfig(handlers=[StreamHandler()])

    if args.date is None:
        target_date = datetime.date.today().strftime("%Y-%m-%d")
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        target_date = args.date
    else:
        logger.error("Please check if the target date format is in YYYY-MM-DD.")
        sys.exit()
    out_path = LOG_DIR / f"allowance_dom_{target_date}.html"
    out_frame_path = LOG_DIR / f"allowance_dom_{target_date}_frame.html"
    sections: list[str] = []

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch_persistent_context(
        headless=False,
        user_data_dir=Path("working_time"),
        viewport=ViewportSize(width=1920, height=1280),
        no_viewport=False,
        args=const.CHROMIUM_PERSISTENT_LAUNCH_ARGS,
    )
    browser.set_default_timeout(TIMEOUT_DEFAULT)
    page = browser.pages[0]

    page.goto(const.TS_ATTENDANCE_SHEET_PAGE_URL, timeout=TIMEOUT_LOGIN)
    page.wait_for_timeout(TIMEOUT_DEFAULT)
    if "accounts.google.com" in page.url:
        logger.info("Google account login page detected")
        modat.login(page, const.ACCOUNT_ADDRESS)
    page.wait_for_url(const.TS_ATTENDANCE_SHEET_PAGE_URL, timeout=TIMEOUT_LOGIN)

    frame = modat.get_attendance_frame(page)
    if frame is None:
        logger.error("Attendance frame not found")
        sys.exit()

    info_panel_selector = 'span[data-dojo-attach-point="closeButtonNode"]'
    if modat.does_selector_exist(frame, info_panel_selector, TIMEOUT_DEFAULT):
        frame.wait_for_selector(info_panel_selector).click()
    frame.wait_for_selector("#dialogInfo_underlay", state="hidden", timeout=TIMEOUT_LOADING)

    if args.last_month:
        frame.wait_for_selector("#prevMonthButton", state="visible", timeout=TIMEOUT_LOADING)
        frame.click("#prevMonthButton")
        frame.wait_for_selector("#shim", state="hidden")

    # 1. Header cells containing "手当"
    headers = frame.evaluate(JS_ALLOWANCE_HEADERS, ALLOWANCE_CHAR)
    sections.append(section(f"1. Header candidates for '{ALLOWANCE_CHAR}'", json.dumps(headers, ensure_ascii=False, indent=2)))
    allowance_idx = next((h["cellIndex"] for h in headers if h["cellIndex"] >= 0), -1)
    logger.info(f"allowance column index: {allowance_idx}")

    # 2. Target date row
    date_row = frame.query_selector(f'tr[id*="dateRow{target_date}"]')
    if date_row is None:
        # Fallback: row containing ttvTimeSt cell of the date
        cell = frame.query_selector(f"td#ttvTimeSt{target_date}")
        date_row = cell.evaluate_handle("el => el.closest('tr')").as_element() if cell else None
    if date_row is None:
        logger.error(f"Date row for {target_date} not found")
        out_path.write_text("".join(sections), encoding="utf-8")
        sys.exit()
    sections.append(section("2. Date row outerHTML", date_row.evaluate("el => el.outerHTML")))
    tds_info = date_row.evaluate(
        "el => Array.from(el.cells).map(td => ({i: td.cellIndex, id: td.id, cls: td.className, "
        "text: td.innerText.trim(), html: td.innerHTML.slice(0, 500)}))"
    )
    sections.append(section("2b. Date row cells", json.dumps(tds_info, ensure_ascii=False, indent=2)))

    # 3. Work location options in the time-input dialog
    ttv_selector = f"td#ttvTimeSt{target_date}"
    if frame.locator(ttv_selector).is_visible():
        try:
            frame.click(ttv_selector)
            frame.wait_for_selector("#workLocationId", state="visible", timeout=TIMEOUT_LOADING)
            options = frame.evaluate(
                "() => ({selected: document.querySelector('#workLocationId').value, "
                "options: Array.from(document.querySelectorAll('#workLocationId option'))"
                ".map(o => ({value: o.value, label: o.textContent.trim()}))})"
            )
            sections.append(section("3. #workLocationId options", json.dumps(options, ensure_ascii=False, indent=2)))
        except Exception as e:
            sections.append(section("3. #workLocationId options", f"failed: {e}"))
        finally:
            if modat.does_selector_exist(frame, "#dlgInpTimeCancel", 1000):
                frame.click("#dlgInpTimeCancel")
                frame.wait_for_selector("#dlgInpTimeCancel", state="hidden", timeout=TIMEOUT_LOADING)
    else:
        sections.append(section("3. #workLocationId options", "ttvTimeSt cell not visible (approved?)"))

    # 4. Click "+" in the allowance cell and dump the popup
    plus = None
    if allowance_idx >= 0:
        tds = date_row.query_selector_all("td")
        if allowance_idx < len(tds):
            plus = tds[allowance_idx].query_selector("input[type=button], button, img, a, [class*='plus'], [class*='btn']")
    if plus is None:
        plus = date_row.query_selector(
            f"[title*='{ALLOWANCE_CHAR}'], [alt*='{ALLOWANCE_CHAR}'], [value*='{ALLOWANCE_CHAR}']"
        )
    if plus is None:
        logger.warning("'+' button in the allowance cell not found. Check section 2b and tell the selector.")
        sections.append(section("4. '+' button", "not found"))
    else:
        sections.append(section("4. '+' button outerHTML", plus.evaluate("el => el.outerHTML")))
        dialogs_before = set(frame.evaluate(JS_VISIBLE_DIALOGS))
        plus.click()
        page.wait_for_timeout(3000)
        dialogs_after = [d for d in frame.evaluate(JS_VISIBLE_DIALOGS) if d not in dialogs_before]
        sections.append(section("4b. New visible dialogs after click", "\n\n----\n\n".join(dialogs_after) or "none"))
        sections.append(section(
            "4c. Visible checkboxes",
            json.dumps(frame.evaluate(JS_VISIBLE_CHECKBOXES), ensure_ascii=False, indent=2),
        ))
        out_frame_path.write_text(frame.content(), encoding="utf-8")
        # Close without registering
        try:
            frame.click("#dialogAllowanceInputCancel", timeout=3000)
        except Exception:
            page.keyboard.press("Escape")

    out_path.write_text(
        f"<meta charset='utf-8'><h1>allowance DOM dump {target_date}</h1>\n" + "".join(sections),
        encoding="utf-8",
    )
    logger.info(f"Saved: {out_path}")
    if out_frame_path.exists():
        logger.info(f"Saved: {out_frame_path}")
    browser.close()
    playwright.stop()
