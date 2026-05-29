import re
import os
import sys
import datetime
import argparse
from logging import StreamHandler, basicConfig, getLogger, handlers
from pathlib import Path

import nest_asyncio
from playwright.sync_api import sync_playwright
from playwright.sync_api._generated import *

import const
from const import ConstRestTimePattern, ConstPersonHour
import module_auto_timestamp as modat

nest_asyncio.apply()

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--debug", action="store_true", help="output logs with debug messages")
parser.add_argument(
    "-D",
    "--date",
    help="Target date in YYYY-MM-DD format. If not specified, today's date will be used.",
)
parser.add_argument(
    "-L", "--last_month", action="store_true", help="run on the attendance sheet for last month"
)
args = parser.parse_args()

# CONST parameter
TIMEOUT_DEFAULT = const.TIMEOUT_DEFAULT
TIMEOUT_LOGIN = const.TIMEOUT_LOGIN
ACCOUNT_ADDRESS = const.ACCOUNT_ADDRESS
WORKDAY_CHAR = "出勤日"
LOG_FILE_PATH = str(Path(__file__).parent / "log" / "auto_input_non_working_time_and_work_place.log")
Path(LOG_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)
TS_ATTENDANCE_SHEET_PAGE_URL = const.TS_ATTENDANCE_SHEET_PAGE_URL
PATH_REASON_INPUT = const.PATH_REASON_INPUT
OFFICE_DAYS = const.OFFICE_DAYS

date_pattern = r"^(\d{4}-\d{2}-\d{2})$"  # YYYY-MM-DDの形式と完全一致するかチェック

current_time = datetime.datetime.now()
logger = getLogger(__name__)
logger.setLevel("DEBUG")
rotatingfilehandler = handlers.RotatingFileHandler(
    LOG_FILE_PATH,
    encoding="utf-8",
    maxBytes=100 * 1024,
    backupCount=20,
)

if __name__ == "__main__":
    handler = StreamHandler()
    if args.debug:
        handler.setLevel("DEBUG")
    else:
        handler.setLevel("INFO")

    if args.last_month:
        is_last_month = True
    else:
        is_last_month = False

    basicConfig(handlers=[handler, rotatingfilehandler])
    logger.info("================ " + current_time.strftime("%Y/%m/%d %H:%M:%S.%f"))

    if args.date is None:
        is_today_only = False
        today = ""
    elif bool(re.search(date_pattern, args.date)):
        is_today_only = True
        today = args.date
    else:
        logger.error("Please check if the target date format is in YYYY-MM-DD.")
        sys.exit()

    is_needed_reason_input = os.path.isfile(PATH_REASON_INPUT) and is_today_only

    playwright = sync_playwright().start()

    user_data_dir = Path("working_time")

    browser = playwright.chromium.launch_persistent_context(
        headless=False,
        user_data_dir=user_data_dir,
        viewport=ViewportSize(width=1920, height=1280),
        no_viewport=False,
        args=const.CHROMIUM_PERSISTENT_LAUNCH_ARGS,
    )
    browser.set_default_timeout(TIMEOUT_DEFAULT)
    page = browser.pages[0]
    modat.tuck_chromium_window_before_goto(page)

    try:
        logger.debug(f"Navigating to {TS_ATTENDANCE_SHEET_PAGE_URL}")
        page.goto(TS_ATTENDANCE_SHEET_PAGE_URL, timeout=TIMEOUT_LOGIN)
        logger.debug("Page navigation completed")
    except TimeoutError:
        logger.error(f"Timeout navigating to {TS_ATTENDANCE_SHEET_PAGE_URL} (timeout: {TIMEOUT_LOGIN}ms)")
        sys.exit()
    except Exception as e:
        logger.error(f"Error navigating to page: {e}")
        sys.exit()

    page.wait_for_timeout(TIMEOUT_DEFAULT)
    page_url = page.url
    if "accounts.google.com" not in page_url:
        modat.minimize_chromium_window_to_taskbar(page)

    logger.debug(f"Current page URL: {page_url}")
    if "accounts.google.com" in page_url:
        logger.info("Google account login page detected")
        logger.debug(f"Navigation chain: {page_url}")
        modat.login(page, ACCOUNT_ADDRESS)
    else:
        logger.info(f"Direct page load without Google login - Current URL: {page_url}")

    try:
        page.wait_for_url(TS_ATTENDANCE_SHEET_PAGE_URL, timeout=TIMEOUT_LOGIN)
        logger.debug("login")
    except TimeoutError:
        logger.error("Could not transition to the specified page. Time has expired.")
        sys.exit()

    frame = page.wait_for_selector("iframe").content_frame()

    info_panel_selector = 'span[data-dojo-attach-point="closeButtonNode"]'
    if modat.does_selector_exist(frame, info_panel_selector, TIMEOUT_DEFAULT):
        logger.info("info_panel_appeared")
        frame.wait_for_selector(info_panel_selector).click()
    else:
        logger.info("No_panel")

    # Move to previous month
    if is_last_month:
        frame.click("#prevMonthButton")
        # Wait for finishing loading the data
        frame.wait_for_selector("#shim", state="hidden")
        logger.info("input last month")
    else:
        logger.info("input this month")

    # Initialize cnt and flags
    cnt_tuesday = 0
    # Get values of this year and month
    year_month = frame.wait_for_selector("#yearMonthList", timeout=5000).input_value()
    logger.debug(f"{year_month=}")
    if not year_month:
        logger.error("No year_month found in the frame")
    year = year_month[:4]
    month = year_month[4:6]
    # Input data in every date row
    frame.wait_for_selector('tr[id*="dateRow"]', timeout=5000)
    date_rows = frame.query_selector_all('tr[id*="dateRow"]')
    logger.debug(f"Found {len(date_rows)} date rows")

    # 要素が見つからない場合のハンドリング
    if not date_rows:
        logger.error("No date rows found in the frame")

    for date_row in frame.query_selector_all('tr[id*="dateRow"]'):
        # Get a value of day
        logger.debug(f"{date_row.text_content()=}")
        date_row_text = str(date_row.text_content())
        idx = date_row_text.find("/")
        if idx == -1:
            is_first_workday = False
        else:
            date_row_text = date_row_text[idx + len("/") :]
            is_first_workday = True
        l = re.split("[月火水木金土日]", date_row_text)
        day = l[0].zfill(2)
        year_month_day = year + "-" + month + "-" + day
        # Skip if not today
        if is_today_only and not (today == year_month_day):
            logger.debug("Skipped, it's not today")
            continue
        # Set selectors
        daily_work_cell_selector = "td#dailyWorkCell" + year_month_day
        logger.info("================ " + f"{daily_work_cell_selector=}")
        ttv_time_st_selector = "td#ttvTimeSt" + year_month_day
        logger.debug(f"{ttv_time_st_selector=}")
        is_visible_ttv_time_st = frame.locator(ttv_time_st_selector).is_visible()
        if not is_visible_ttv_time_st:
            logger.info("The page might be approved or still not completed inputting. skipping ...")
            continue

        # Get cells
        tds = date_row.query_selector_all("td")
        # Get the day of the week
        td_week = tds[1]
        td_week_status = td_week.text_content()
        logger.debug(f"{td_week_status=}")
        # TIER IV all hands meeting is held on the 2nd and 4th Tuesday in a month
        if "火" in td_week_status:
            cnt_tuesday += 1
            is_tier4_all_hands = (cnt_tuesday == 2) or (cnt_tuesday == 4)
        else:
            is_tier4_all_hands = False

        if any(day in td_week_status for day in OFFICE_DAYS):
            is_work_in_office = True
        else:
            is_work_in_office = False

        # Get start and end of working time
        start_time, end_time = modat.get_work_times(tds)
        if not start_time or not end_time:
            logger.info("Work time is not input. skipping ...")
            continue

        if not modat.is_holiday(tds, WORKDAY_CHAR):
            # Start controlling "勤怠情報入力" on browser
            # startRest2
            td_start_time = modat.string_to_datetime(start_time)
            td_end_time = modat.string_to_datetime(end_time)
            if is_work_in_office:
                # Check if rest time input is needed
                is_needed_rest2_input = td_start_time < modat.string_to_datetime(
                    ConstRestTimePattern("Office_day").START_REST_TIME2
                )
                is_needed_rest3_input = (
                    modat.string_to_datetime(ConstRestTimePattern("Office_day").END_REST_TIME3)
                    <= td_end_time
                )
                if is_needed_rest2_input or is_needed_rest3_input:
                    frame.click(ttv_time_st_selector)
                    modat.input_non_work_time(
                        frame, start_time, end_time, ConstRestTimePattern("Office_day")
                    )
                else:
                    logger.info(f"{"Non working time is not needed to be input. skipping"}")
                if is_today_only:
                    logger.debug("work in office on Office day")
                    frame.click(ttv_time_st_selector)
                    modat.input_work_place(frame)
                    frame.wait_for_selector("#dlgInpTimeOk").click()
                    frame.wait_for_selector("#dlgInpTimeOk", state="hidden")
            else:
                # Check if rest time input is needed
                is_needed_rest2_input = td_start_time < modat.string_to_datetime(
                    ConstRestTimePattern("").START_REST_TIME2
                )
                is_needed_rest3_input = (
                    modat.string_to_datetime(ConstRestTimePattern("").END_REST_TIME3) <= td_end_time
                )
                if is_needed_rest2_input or is_needed_rest3_input:
                    frame.click(ttv_time_st_selector)
                    modat.input_non_work_time(frame, start_time, end_time, ConstRestTimePattern(""))
                else:
                    logger.info(f"{"Non working time is not needed to be input. skipping"}")

            # Input a reason for discrepancy when it is alerted
            td_discrepancy_alert = tds[7]
            selector_discrepancy_alert = "div.pp_base.pp_acc_02"
            if modat.does_selector_exist(td_discrepancy_alert, selector_discrepancy_alert, 100):
                logger.debug("start inputting a reason for discrepancy")
                frame.click(selector_discrepancy_alert)
                # Select option from the discrepancy reason dropdown
                frame.locator("//table[1]/tbody/tr/td[2]/div[1]/select").click()
                frame.locator("//table[1]/tbody/tr/td[2]/div[1]/select").select_option(index=7)
                frame.locator("//table[2]/tbody/tr/td[2]/div[1]/select").click()
                frame.locator("//table[2]/tbody/tr/td[2]/div[1]/select").select_option(index=7)
                frame.locator("//table[2]/tbody/tr/td[2]/div[1]").click()
                frame.get_by_role("button", name="登録").click()
            else:
                logger.debug("No discrepancy alert")

            # Input person-hour when it is not consisted with actual working time
            td_person_hour = tds[8]
            td_person_hour_text = td_person_hour.text_content()
            logger.debug(f"{td_person_hour_text=}")
            excl_selector = "div.workng.pp_base.pp_exclamatio2"
            if modat.does_selector_exist(td_person_hour, excl_selector, 100):
                logger.debug("start inputting person hour")
                # Start controlling "工数実績入力" on browser
                frame.click(daily_work_cell_selector)
                modat.input_person_hour(
                    frame, is_tier4_all_hands, is_first_workday, ConstPersonHour()
                )
            else:
                logger.debug("person hour has already been input")

            # Input a reason for discrepancy when a reason file exists
            if is_needed_reason_input:
                # Set selector
                daily_access_selector = "td#dailyAccsCell" + year_month_day
                logger.debug(f"{daily_access_selector=}")
                frame.click(daily_access_selector)
                # Select option from the discrepancy reason dropdown
                frame.locator("//table[1]/tbody/tr/td[2]/div[1]/select").click()
                frame.locator("//table[1]/tbody/tr/td[2]/div[1]/select").select_option(index=7)
                frame.locator("//table[2]/tbody/tr/td[2]/div[1]").click()
                frame.get_by_role("button", name="登録").click()
                logger.debug("The discrepancy reason has been input")
            else:
                logger.debug("Not input the discrepancy reason")
