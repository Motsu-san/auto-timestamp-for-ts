import re
import sys
import datetime
from logging import StreamHandler, basicConfig, getLogger, handlers
from pathlib import Path

import nest_asyncio
from playwright.sync_api import sync_playwright
from playwright.sync_api._generated import *

import const
from const import ConstRestTimePattern, ConstPersonHour
import module_auto_timestamp as modat

nest_asyncio.apply()

args = sys.argv

# CONST parameter
TIMEOUT_DEFAULT = const.TIMEOUT_DEFAULT
ACCOUNT_ADDRESS = const.ACCOUNT_ADDRESS
WORKDAY_CHAR = "出勤日"
LOG_FILE_PATH = str(Path("log").absolute()) + r"\auto_input_non_working_time_and_work_place.log"
TS_ATTENDANCE_SHEET_PAGE_URL = const.TS_ATTENDANCE_SHEET_PAGE_URL

date_pattern = r'^(\d{4}-\d{2}-\d{2})$' # YYYY-MM-DDの形式と完全一致するかチェック
if len(args) < 2:
    is_last_month = False
    is_today_only = False
    today = ""
elif args[1] == "1":
    is_last_month = True
    is_today_only = False
    today = ""
elif bool(re.search(date_pattern, args[1])):
    is_last_month = False
    is_today_only = True
    today = args[1]
else:
    is_last_month = False
    is_today_only = False
    today = ""

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
    handler.setLevel("INFO")
    basicConfig(handlers=[handler, rotatingfilehandler])
    basicConfig(level="DEBUG")
    logger.info("================ " + current_time.strftime("%Y/%m/%d %H:%M:%S.%f"))

    playwright = sync_playwright().start()

    user_data_dir = Path("data")

    browser = playwright.chromium.launch_persistent_context(
        headless=False,
        user_data_dir=user_data_dir,
        viewport=ViewportSize(width=1920, height=1280),
    )
    page = browser.pages[0]

    page.goto(TS_ATTENDANCE_SHEET_PAGE_URL)

    # login when the account check page appears
    page_url = page.url
    if "accounts.google.com" in page_url:
        modat.login(page, ACCOUNT_ADDRESS)

    frame = page.wait_for_selector("iframe").content_frame()

    logger.info(f"{frame.wait_for_selector('td')=}")

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

    # Initialize cnt and flags
    cnt_tuesday = 0
    # Get values of this year and month
    year_month = frame.input_value("#yearMonthList")
    year = year_month[:4]
    month = year_month[4:6]
    # Input data in every date row
    for date_row in frame.query_selector_all('tr[id*="dateRow"]'):
        # Get a value of day
        logger.info(f"{date_row.text_content()=}")
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
            logger.info("Skipped, it's not today")
            continue
        # Set selectors
        daily_work_cell_selector = "td#dailyWorkCell" + year_month_day
        logger.debug(f"{daily_work_cell_selector=}")
        ttv_time_st_selector = "td#ttvTimeSt" + year_month_day
        logger.debug(f"{ttv_time_st_selector=}")
        is_visible_ttv_time_st = frame.locator(ttv_time_st_selector).is_visible()
        if not is_visible_ttv_time_st:
            logger.info(
                "The page might be approved or still completed inputting. skipping ..."
            )
            continue

        # Get cells
        tds = date_row.query_selector_all("td")
        # Get the day of the week
        td_week = tds[1]
        td_week_status = td_week.text_content()
        logger.info(f"{td_week_status=}")
        # TIER IV all hands meeting is held on the 2nd and 4th Tuesday in a month
        if "火" in td_week_status:
            cnt_tuesday += 1
            is_tier4_all_hands = (cnt_tuesday == 2) or (cnt_tuesday == 4)
        else:
            is_tier4_all_hands = False
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
            if "金" in td_week_status:
                # Check if rest time input is needed
                is_needed_rest2_input = td_start_time < modat.string_to_datetime(
                    ConstRestTimePattern("Friday").START_REST_TIME2
                )
                is_needed_rest3_input = (
                    modat.string_to_datetime(
                        ConstRestTimePattern("Friday").END_REST_TIME3
                    )
                    <= td_end_time
                )
                if is_needed_rest2_input or is_needed_rest3_input:
                    frame.click(ttv_time_st_selector)
                    modat.input_non_work_time(
                        frame, start_time, end_time, ConstRestTimePattern("Friday")
                    )
                else:
                    logger.info(
                        f"{"Non working time is not needed to be input. skipping"}"
                    )
                if is_today_only:
                    logger.info("work in office on Friday")
                    frame.click(ttv_time_st_selector)
                    modat.input_work_place(frame)
                    frame.wait_for_selector(
                        "#dlgInpTimeOk", timeout=TIMEOUT_DEFAULT
                    ).click()
                    frame.wait_for_selector("#dlgInpTimeOk", state="hidden")
            else:
                # Check if rest time input is needed
                is_needed_rest2_input = td_start_time < modat.string_to_datetime(
                    ConstRestTimePattern("").START_REST_TIME2
                )
                is_needed_rest3_input = (
                    modat.string_to_datetime(ConstRestTimePattern("").END_REST_TIME3)
                    <= td_end_time
                )
                if is_needed_rest2_input or is_needed_rest3_input:
                    frame.click(ttv_time_st_selector)
                    modat.input_non_work_time(
                        frame, start_time, end_time, ConstRestTimePattern("")
                    )
                else:
                    logger.info(
                        f"{"Non working time is not needed to be input. skipping"}"
                    )

            # Input person-hour when it is not consisted with actual working time
            td_person_hour = tds[8]
            td_person_hour_text = td_person_hour.text_content()
            logger.info(f"{td_person_hour_text=}")
            excl_selector = "div.workng.pp_base.pp_exclamatio2"
            if modat.does_selector_exist(td_person_hour, excl_selector, 100):
                logger.info("start inputting person hour")
                # Start controlling "工数実績入力" on browser
                frame.click(daily_work_cell_selector)
                modat.input_person_hour(
                    frame, is_tier4_all_hands, is_first_workday, ConstPersonHour()
                )
            else:
                logger.info("person hour has already been input")
