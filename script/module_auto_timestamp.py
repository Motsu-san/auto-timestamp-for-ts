import os
import sys
import datetime
from logging import getLogger

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


def login(page: Page, gmail_address: str):
    logger.info("Start login")
    # ログイン中はCDPでウィンドウを動かさない（本人確認画面等でsetWindowBoundsするとクラッシュすることがある）
    page.bring_to_front()  # ログイン時にウィンドウを前面に表示

    # Check if already at TeamSpirit page (already logged in)
    if "lightning.force.com" in page.url or "teamspiritapp" in page.url:
        logger.info(f"Already at TeamSpirit page - skipping login. Current URL: {page.url}")
        return

    # 本人確認など複数「次へ」がある場合に対応: パスワード欄が出るまで「次へ」を押す
    MAX_NEXT_CLICKS = 5
    password_visible = False
    for _ in range(MAX_NEXT_CLICKS):
        try:
            if page.locator('input[type="password"]').is_visible():
                password_visible = True
                break
            logger.debug("Clicking 'Next' button")
            page.click('button[type="button"]:has-text("次へ")', timeout=TIMEOUT_LOADING)
            page.wait_for_timeout(500)  # 遷移の安定化
        except TimeoutError:
            # 「次へ」がない、または既にパスワード画面の可能性
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

    # パスワード入力画面になったらウィンドウを画面内に表示（起動時は --window-position=3000,3000 で画面外のため）
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
                },
            },
        )
        page.bring_to_front()
    except Exception as e:
        logger.warning(f"Could not move window to foreground for password input (non-fatal): {e}")
        page.bring_to_front()

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

    # ログイン完了後にのみCDPでウィンドウを画面外へ移動（認証中にCDPを触るとクラッシュしやすいため）
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
                    "width": 1920,
                    "height": 1280,
                },
            },
        )
    except Exception as e:
        logger.warning(f"Could not move window off-screen via CDP (non-fatal): {e}")

    page.evaluate("window.blur()")  # フォーカスを外す
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
    start_time = td_start.text_content().strip()
    end_time = td_end.text_content().strip()

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
    import re

    try:
        # Wait for iframe
        frame = page.wait_for_selector("iframe", timeout=timeout).content_frame()

        # Get today's date
        today = datetime.datetime.now()
        year = str(today.year)
        month = str(today.month).zfill(2)
        day = str(today.day).zfill(2)
        today_str = year + "-" + month + "-" + day

        logger.info(f"Checking timestamp for today: {today_str}")

        # Get year and month
        year_month = frame.input_value("#yearMonthList")
        year_from_page = year_month[:4]
        month_from_page = year_month[4:6]

        # Loop through date rows to find today's row
        for date_row in frame.query_selector_all('tr[id*="dateRow"]'):
            date_row_text = str(date_row.text_content())
            idx = date_row_text.find("/")
            if idx == -1:
                continue
            date_row_text = date_row_text[idx + len("/") :]
            l = re.split("[月火水木金土日]", date_row_text)
            if len(l) == 0:
                continue
            day_from_page = l[0].zfill(2)
            year_month_day = year_from_page + "-" + month_from_page + "-" + day_from_page

            # Check if it's today's row
            if today_str == year_month_day:
                # Get cells
                tds = date_row.query_selector_all("td")
                if len(tds) < 6:
                    logger.info("Not enough cells in the row")
                    return False

                # Get start and end times
                start_time, end_time = get_work_times(tds)

                if is_punch_in:
                    # Check punch-in (start time)
                    if start_time and start_time.strip():
                        logger.info(f"Punch-in timestamp found: {start_time}")
                        return True
                    else:
                        logger.info("Punch-in timestamp not found")
                        return False
                else:
                    # Check punch-out (end time)
                    if end_time and end_time.strip():
                        logger.info(f"Punch-out timestamp found: {end_time}")
                        return True
                    else:
                        logger.info("Punch-out timestamp not found")
                        return False

        logger.info("Today's row not found")
        return False

    except Exception as e:
        logger.error(f"Error checking timestamp: {e}")
        return False
