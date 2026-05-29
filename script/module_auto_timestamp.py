import os
import re
import sys
import datetime
from logging import getLogger
from urllib.parse import urlparse

import nest_asyncio  # pyright: ignore[reportMissingImports]
from playwright.sync_api import sync_playwright
from playwright.sync_api._generated import *


import const
from const import ConstRestTimePattern, ConstPersonHour

# pip install re time nest_asyncio dotenv playwright

nest_asyncio.apply()

TIMEOUT_DEFAULT = const.TIMEOUT_DEFAULT
TIMEOUT_LOADING = const.TIMEOUT_LOADING
TIMEOUT_LOGIN = const.TIMEOUT_LOGIN
START_REST_TIME_DEFAULT = "12:00"
END_REST_TIME_DEFAULT = "13:00"
ID_OFFLINE_AND_REMOTE_WORK = "a25A70000000iuAIAQ"  #  出社+テレワーク

logger = getLogger(__name__)
logger.setLevel("INFO")


def _win32_bring_to_front() -> None:
    """Win32 API でChromiumウィンドウをOSレベルで前面に出す。"""
    try:
        import psutil
        import win32con
        import win32gui
        import win32process

        chromium_pids: set[int] = set()
        for child in psutil.Process().children(recursive=True):
            n = child.name().lower()
            if "chrome" in n or "chromium" in n:
                chromium_pids.add(child.pid)

        def _cb(hwnd: int, _: object) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid not in chromium_pids:
                return
            if win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE) & win32con.WS_CAPTION:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)

        win32gui.EnumWindows(_cb, None)
    except Exception as e:
        logger.warning(f"Win32 foreground attempt failed (non-fatal): {e}")


def _chromium_bring_window_on_screen(page: Page) -> None:
    """Bring the window back on-screen for interactive Google login (CDP windowState normal)."""
    try:
        client = page.context.new_cdp_session(page)
        windows = client.send("Browser.getWindowForTarget")
        window_id = windows["windowId"]
        client.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "left": 100,
                    "top": 100,
                    "width": 1920,
                    "height": 1280,
                    "windowState": "normal",
                },
            },
        )
    except Exception as e:
        logger.warning(f"Could not move window on-screen for login (non-fatal): {e}")
    page.bring_to_front()
    _win32_bring_to_front()


def minimize_chromium_window_to_taskbar(page: Page) -> None:
    """Move the window off the primary display (one CDP setWindowBounds). Call before a slow goto to limit maximized flash during load."""
    try:
        client = page.context.new_cdp_session(page)
        windows = client.send("Browser.getWindowForTarget")
        window_id = windows["windowId"]
        client.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "left": 3000,
                    "top": 3000,
                    "width": 1200,
                    "height": 800,
                    "windowState": "normal",
                },
            },
        )
    except Exception as e:
        logger.warning(f"Could not move Chromium window off-screen (non-fatal): {e}")


def tuck_chromium_window_before_goto(page: Page) -> None:
    """Short wait for the native window, then park off-screen before page.goto()."""
    page.wait_for_timeout(200)
    minimize_chromium_window_to_taskbar(page)


def _chromium_move_window_off_screen(page: Page) -> None:
    """After login completes, move the window off-screen again (same as minimize_chromium_window_to_taskbar)."""
    minimize_chromium_window_to_taskbar(page)


def login(page: Page, gmail_address: str):
    logger.info("Start login")
    page.bring_to_front()

    # Check if already at TeamSpirit page (already logged in).
    # Use hostname only — Google SAML redirect URLs embed the TeamSpirit domain
    # as a query parameter, so a plain substring match on the full URL gives a false positive.
    _host = urlparse(page.url).hostname or ""
    if _host.endswith("lightning.force.com") or "teamspiritapp" in _host:
        logger.info(f"Already at TeamSpirit page - skipping login. Current URL: {page.url}")
        return

    _chromium_bring_window_on_screen(page)

    # Google may show several "Next" steps; advance until the password field is visible
    MAX_NEXT_CLICKS = 5
    password_visible = False
    for _ in range(MAX_NEXT_CLICKS):
        try:
            if page.locator('input[type="password"]').is_visible():
                password_visible = True
                break
            logger.debug("Clicking 'Next' button")
            page.click('button[type="button"]:has-text("次へ")', timeout=TIMEOUT_LOADING)
            page.wait_for_timeout(500)
        except TimeoutError:
            # No "Next" or already on the password step
            if page.locator('input[type="password"]').is_visible():
                password_visible = True
                break
            logger.error(
                f"Timeout waiting for 'Next' button or password field (timeout: {TIMEOUT_LOADING}ms). URL: {page.url}"
            )
            raise
        except Exception as e:
            if page.locator('input[type="password"]').is_visible():
                password_visible = True
                break
            logger.error(f"Error clicking 'Next' button: {e}. URL: {page.url}")
            raise

    if not password_visible:
        try:
            page.wait_for_selector(
                'input[type="password"]', state="visible", timeout=TIMEOUT_LOADING
            )
        except TimeoutError:
            logger.error(f"Timeout waiting for password input field (timeout: {TIMEOUT_LOADING}ms). URL: {page.url}")
            raise
        except Exception as e:
            logger.error(f"Error waiting for password input field: {e}. URL: {page.url}")
            raise

    # Wait for navigation after password entry (manual entry by user)
    try:
        with page.expect_navigation(timeout=TIMEOUT_LOGIN):
            # Inform the user to enter the password manually
            logger.info("Please enter your password in the browser.")
            # Wait for a specific element that appears after login
            page.get_by_title("TeamSpirit").wait_for(state="visible", timeout=TIMEOUT_LOGIN)
    except TimeoutError:
        logger.error(
            f"Timeout waiting for login completion (timeout: {TIMEOUT_LOGIN}ms). Please check if login was successful."
        )
        raise
    except Exception as e:
        logger.error(f"Error during login navigation: {e}")
        raise

    _chromium_move_window_off_screen(page)

    page.evaluate("window.blur()")
    logger.debug("Login completed successfully")

def does_selector_exist(frame: Frame, selector: str, timeout=TIMEOUT_DEFAULT):
    try:
        frame.wait_for_selector(selector, state="attached", timeout=timeout)
        return True
    except:
        return False


def does_selector_exist_by_text(page: Page, text: str):
    try:
        page.get_by_text(text).is_visible()
        return True
    except:
        return False


def is_text_box_input(frame: Frame, selector: str, timeout=TIMEOUT_DEFAULT):
    value = frame.input_value(selector, timeout=timeout)
    if value:
        return True
    else:
        return False


def string_to_datetime(string):
    return datetime.datetime.strptime(string, "%H:%M")


def is_holiday(tds: list[ElementHandle], workday_char: str = "出勤日") -> bool:
    """
    Checks if the provided day is a holiday.

    Args:
    tds (list[ElementHandle]): A list of ElementHandle objects representing the table cells for a specific row.

    Returns:
    bool: True if the day is a holiday, False otherwise.
    """
    td_work_status = tds[2]
    work_status_title = td_work_status.get_attribute("title")
    logger.debug(f"work_status_title={work_status_title}")
    if workday_char not in work_status_title:
        logger.info("the day is a holiday. skipping ...")
        return True
    return False


def _normalize_narrow_for_date_parse(text: str) -> str:
    # 画面によっては全角数字＋U+3000
    t = (text or "").replace("\u3000", " ")
    for a, b in zip("０１２３４５６７８９", "0123456789"):
        t = t.replace(a, b)
    return t


def _parse_day_of_month_from_date_cell_text(text: str) -> str | None:
    # 「4/23」「23 木」等（スラッシュなし＋曜日）から日付だけ取る。/ 必須の旧条件だと 23 木 行は無視されていた
    if not text:
        return None
    first_line = (text.splitlines() or [""])[0].strip() if text else ""
    if not first_line:
        return None
    t = _normalize_narrow_for_date_parse(first_line)
    if "/" in t:
        idx = t.find("/")
        if idx == -1:
            return None
        after = t[idx + 1 :]
        parts = re.split("[月火水木金土日]", after, maxsplit=1)
        if not parts or not parts[0].strip():
            return None
        return parts[0].strip().zfill(2)
    m = re.match(r"^(\d{1,2})\s*[月火水木金土日]", t)
    if m:
        return m.group(1).zfill(2)
    return None


def _td_work_time_text(td: ElementHandle) -> str:
    # 時刻が input の value のみのとき、text_content では空になりがち
    for sel in ("input", "textarea"):
        inp = td.query_selector(sel)
        if inp is not None:
            val = None
            try:
                val = inp.input_value()
            except Exception:
                pass
            if val and str(val).strip():
                return str(val).strip()
            a = inp.get_attribute("value")
            if a and a.strip():
                return a.strip()
    raw = (td.text_content() or "").strip()
    if raw:
        return raw
    return (td.inner_text() or "").strip()


def get_work_times(tds: list[ElementHandle]):
    """
    Gets the start and end times of working from the provided table row data.

    Args:
    tds (list[ElementHandle]): A list of ElementHandle objects representing the table cells for a specific row.

    Returns:
    tuple[str, str] | None: A tuple of start and end times as strings if they are both present, otherwise None.
    """
    td_start = tds[4]
    td_end = tds[5]
    start_time = _td_work_time_text(td_start)
    end_time = _td_work_time_text(td_end)

    logger.debug(f"start_time={start_time}")
    logger.debug(f"end_time={end_time}")

    return start_time, end_time


def input_non_work_time(frame: Frame, td_start: str, td_end: str, const: ConstRestTimePattern):

    # startRest2
    td_start_time = string_to_datetime(td_start)
    td_end_time = string_to_datetime(td_end)
    # Check if rest time input is needed
    is_needed_rest2_input = td_start_time < string_to_datetime(const.START_REST_TIME2)
    is_needed_rest3_input = string_to_datetime(const.END_REST_TIME3) < td_end_time
    # Check if the day is a am/pm paid holiday
    is_ampm_paid_holiday = (string_to_datetime(START_REST_TIME_DEFAULT) <= td_start_time) or (
        td_end_time <= string_to_datetime(END_REST_TIME_DEFAULT)
    )

    # Get the flag if my rest time is input
    if is_ampm_paid_holiday:
        is_start_rest_input = is_text_box_input(frame, "#startRest1")
    else:
        is_start_rest_input = is_text_box_input(frame, "#startRest2")
    logger.debug(f"{is_start_rest_input=}")

    button_selector = 'input.pb_btn_plusL[type="button"][title="休憩時間入力行追加"]'
    # Skip if my rest time is input
    if not is_start_rest_input:
        if is_needed_rest2_input:
            logger.debug(f"{is_needed_rest2_input=}")
            frame.wait_for_selector("#startRest2").fill(
                const.START_REST_TIME2
            )
            frame.wait_for_selector("#endRest2").fill(const.END_REST_TIME2)
        if is_needed_rest3_input:
            logger.debug(f"{is_needed_rest3_input=}")
            frame.wait_for_selector(button_selector, state="visible")
            frame.click(button_selector)
            frame.wait_for_selector("#startRest3").fill(
                const.START_REST_TIME3
            )
            frame.wait_for_selector("#endRest3").fill(const.END_REST_TIME3)
        frame.wait_for_selector("#dlgInpTimeOk").click()
        frame.wait_for_selector("#dlgInpTimeOk", state="hidden", timeout=TIMEOUT_LOADING)
    else:
        logger.info(f"{"Working time has been already input. skipping"}")
        frame.wait_for_selector("#dlgInpTimeCancel").click()
        frame.wait_for_selector("#dlgInpTimeCancel", state="hidden", timeout=TIMEOUT_LOADING)


def input_work_place(frame: Frame):
    value = frame.input_value("#workLocationId")
    if not value == ID_OFFLINE_AND_REMOTE_WORK:
        logger.info(f"{"work location is not updated"}")
        frame.select_option("#workLocationId", value=ID_OFFLINE_AND_REMOTE_WORK)
        frame.wait_for_selector("#dlgInpTimeOk").click()
        frame.wait_for_selector("#dlgInpTimeOk", state="hidden", timeout=TIMEOUT_LOADING)
    else:
        logger.info(f"{"Work location is updated"}")
        frame.wait_for_selector("#dlgInpTimeCancel").click()
        frame.wait_for_selector("#dlgInpTimeCancel", state="hidden", timeout=TIMEOUT_LOADING)


def input_person_hour(
    frame: Frame,
    is_tier4_all_hands: bool,
    is_first_workday: bool,
    const: ConstPersonHour,
):
    # Get actual working time
    logger.debug(f"{frame.wait_for_selector('#empWorkRealTime').text_content()=}")
    actual_working_time_message = frame.wait_for_selector("#empWorkRealTime").text_content()
    target = "："  # 「：」より後ろ（時刻）を抽出したい
    idx = actual_working_time_message.find(target)
    actual_working_time = actual_working_time_message[idx + len(target) :]
    logger.debug(f"{actual_working_time=}")
    # initialize RD1_GI time
    frame.wait_for_selector("#empInputTime0").fill("")
    # Input RD1_NOT_GI time
    frame.wait_for_selector("#empInputTime1").fill(const.RD1_NOT_GI)
    # Input IN_HOUSE_MEETING time if needed
    if is_tier4_all_hands:
        logger.debug(f"{"TIER IV all hands held"}")
        frame.wait_for_selector("#empInputTime2").fill(
            const.IN_HOUSE_MEETING
        )
    if is_first_workday:
        logger.debug(f"{"Added Attendance related time"}")
        frame.wait_for_selector("#empInputTime4").fill(
            const.ATTENDANCE_RELATED
        )
    # Get total input working time
    frame.wait_for_selector("#empWorkRealTime").click()  # needed to update empWorkTotalTime
    total_input_working_time = frame.wait_for_selector("#empWorkTotalTime").text_content()
    logger.debug(f"{total_input_working_time=}")
    # Get RD1_GI time
    rd1_gi_working_timedelta = str(
        string_to_datetime(actual_working_time) - string_to_datetime(total_input_working_time)
    )
    logger.debug(f"{rd1_gi_working_timedelta=}")
    rd1_gi_working_time = rd1_gi_working_timedelta[:-3]  # In [HH:MM:SS], ":SS" is deleted
    logger.debug(f"{rd1_gi_working_time=}")
    frame.wait_for_selector("#empInputTime0").fill(rd1_gi_working_time)
    frame.wait_for_selector("#empWorkOk").click()
    frame.wait_for_selector("#empWorkOk", state="hidden", timeout=TIMEOUT_LOADING)


def get_attendance_frame(page, timeout: float = TIMEOUT_LOADING):
    """
    TeamSpirit 勤怠一覧は #yearMonthList を持つフレームにあり、Lightning では先頭 iframe ではない場合がある。
    どの子フレームにも該当がないとき、dateRow 検索は常に空になる。
    """
    to = max(100.0, float(timeout))
    n = 0
    max_loops = int(to / 100.0) + 2
    while n < max_loops:
        for fr in list(page.frames):
            try:
                if fr.query_selector("#yearMonthList") is not None:
                    return fr
            except Exception:
                pass
        try:
            page.wait_for_timeout(100)
        except Exception:
            break
        n += 1
    return None


def check_today_timestamp(page: Page, is_punch_in: bool, timeout=TIMEOUT_DEFAULT) -> bool:
    """
    Check if today's timestamp is recorded on the specified page

    Args:
        page: Page object
        is_punch_in: If True, check punch-in (start time), if False, check punch-out (end time)
        timeout: Timeout duration

    Returns:
        bool: True if timestamp is recorded, False otherwise
    """
    try:
        eff_to = max(float(timeout), float(TIMEOUT_LOADING))
        frame = get_attendance_frame(page, eff_to)
        if frame is None:
            logger.error("No frame with #yearMonthList; attendance grid may be in a non-default iframe")
            return False

        # Get today's date
        today = datetime.datetime.now()
        year = str(today.year)
        month = str(today.month).zfill(2)
        day = str(today.day).zfill(2)
        today_str = year + "-" + month + "-" + day

        logger.info(f"Checking timestamp for today: {today_str}")

        def _get_times_from_row_and_decide(row) -> bool:
            tds = row.query_selector_all("td")
            if len(tds) < 6:
                logger.info("Not enough cells in the row")
                return False
            st, en = get_work_times(tds)
            if is_punch_in:
                if st and st.strip():
                    logger.info(f"Punch-in timestamp found: {st}")
                    return True
                logger.info("Punch-in timestamp not found")
                return False
            if en and en.strip():
                logger.info(f"Punch-out timestamp found: {en}")
                return True
            logger.info("Punch-out timestamp not found")
            return False

        # 1) 勤怠一覧: td#ttvTimeStYYYY-MM-DD（勤怠入力スクリプトと同じ。列ズレに依存しない）
        full_ttv_id = f"ttvTimeSt{today_str}"
        date_row = None
        for sel in (
            f"tr:has(> td#ttvTimeSt{today_str})",
            f"tr:has(td#ttvTimeSt{today_str})",
            f"xpath=//tr[.//td[@id='{full_ttv_id}']]",
        ):
            date_row = frame.query_selector(sel)
            if date_row is not None:
                break
        if date_row is None and frame.query_selector(f"td[id='{full_ttv_id}']") is not None:
            date_row = frame.query_selector(f"xpath=//tr[.//td[@id='{full_ttv_id}']]")

        if date_row is not None:
            return _get_times_from_row_and_decide(date_row)

        # 2) 従来: テキスト解析。日付は1列目ではなく2列目等の可能性あり
        year_month = ""
        try:
            year_month = frame.input_value("#yearMonthList")
        except Exception:
            pass
        if not year_month or len(year_month) < 6:
            year_from_page = year
            month_from_page = month
            logger.info(f"yearMonthList missing or short ({year_month!r}); using system Y-M for text match")
        else:
            year_from_page = year_month[:4]
            month_from_page = year_month[4:6]

        for dr in frame.query_selector_all('tr[id*="dateRow"]'):
            for td in dr.query_selector_all("td")[:8]:
                dt = (td.text_content() or "")
                dnum = _parse_day_of_month_from_date_cell_text(dt)
                if not dnum:
                    continue
                ymd = f"{year_from_page}-{month_from_page}-{dnum}"
                if ymd == today_str:
                    if _get_times_from_row_and_decide(dr):
                        return True
                    return False
            drt = (dr.text_content() or "")
            dnum2 = _parse_day_of_month_from_date_cell_text(drt)
            if dnum2:
                ymd2 = f"{year_from_page}-{month_from_page}-{dnum2}"
                if ymd2 == today_str:
                    if _get_times_from_row_and_decide(dr):
                        return True
                    return False

        ym_dbg = ""
        try:
            ym_dbg = frame.input_value("#yearMonthList")
        except Exception:
            pass
        n_drows = len(frame.query_selector_all('tr[id*="dateRow"]'))
        logger.info(
            f"Today's row not found (yearMonthList={ym_dbg!r}, dateRow rows={n_drows},"
            f" ttvSt id={full_ttv_id!r}, frames={len(list(page.frames))})"
        )
        return False

    except Exception as e:
        logger.error(f"Error checking timestamp: {e}")
        return False
