import os
import sys
import time
import datetime
import math
import re
from logging import StreamHandler, basicConfig, getLogger, handlers
from pathlib import Path

import nest_asyncio
from playwright.sync_api import sync_playwright
from playwright.sync_api._generated import *

import module_auto_timestamp as modat
import const

# pip install re time nest_asyncio dotenv playwright

args = sys.argv

nest_asyncio.apply()

TIMEOUT_DEFAULT = const.TIMEOUT_DEFAULT
GMAIL_ADDRESS = const.GMAIL_ADDRESS
TIMEOUT_LOGIN = const.TIMEOUT_LOGIN
PATH_WORKDAY = const.PATH_WORKDAY
PATH_TIMESTAMP_IN = const.PATH_TIMESTAMP_IN
PATH_TIMESTAMP_OUT = const.PATH_TIMESTAMP_OUT
START_TIME_STAMP = const.START_TIME_STAMP
TS_PAGE_URL = const.TS_PAGE_URL
TIME_DURATION_DISCREPANCY = const.TIME_DURATION_DISCREPANCY
TS_ATTENDANCE_SHEET_PAGE_URL = const.TS_ATTENDANCE_SHEET_PAGE_URL
DISCREPANCY_REASON = const.DISCREPANCY_REASON
PATH_WAITING = const.PATH_WAITING
LOG_FILE_PATH = const.LOG_DIR + "auto_timestamp_inout.log"

if len(args) < 2:
    is_punch_out = False
elif args[1] == "1":
    is_punch_out = True
else:
    is_punch_out = False

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

    is_workday = os.path.isfile(PATH_WORKDAY)
    is_timestamp_in = os.path.isfile(PATH_TIMESTAMP_IN)
    is_timestamp_out = os.path.isfile(PATH_TIMESTAMP_OUT)
    is_waiting = os.path.isfile(PATH_WAITING)
    is_needed_reason_input = False
    is_wait_for_sleep = False
    if is_waiting:
        logger.info("previous process existing, finish.")
        sys.exit()
    elif is_workday and not is_timestamp_in:
        btn_selector = "input#btnStInput"
        selector_type = "punch-in"
        make_file = PATH_TIMESTAMP_IN
        start_time_stamp = datetime.datetime(
            current_time.year, current_time.month, current_time.day, hour=6, minute=0
        )
        wait_time = start_time_stamp - current_time
        wait_second = math.ceil(wait_time.total_seconds())
        if wait_time.total_seconds() > 0:
            touch_file = Path(PATH_WAITING)
            touch_file.touch()
            time.sleep(wait_time.total_seconds())
        if wait_time.total_seconds() >= TIME_DURATION_DISCREPANCY:
            is_needed_reason_input = True
    elif is_workday and is_timestamp_in and not is_timestamp_out and is_punch_out:
        btn_selector = "input#btnEtInput"
        selector_type = "punch-out"
        make_file = PATH_TIMESTAMP_OUT
        is_wait_for_sleep = True
    else:
        logger.info("Not needed to punch in/out, finish.")
        sys.exit()

    playwright = sync_playwright().start()

    user_data_dir = Path("data")

    browser = playwright.chromium.launch_persistent_context(
        headless=False,
        user_data_dir=user_data_dir,
        viewport=ViewportSize(width=1920, height=1280),
    )
    page = browser.pages[0]

    page.goto(TS_PAGE_URL)

    # login when the account check page appears
    page_url = page.url
    if "accounts.google.com" in page_url:
        modat.login(page, GMAIL_ADDRESS)

    try:
        page.wait_for_url(TS_PAGE_URL, timeout=TIMEOUT_LOGIN)
        logger.info("login")

    except TimeoutError:
        logger.info("Could not transition to the specified page. Time has expired.")
        sys.exit()

    frame = page.wait_for_selector("iframe").content_frame()

    logger.info(f"{frame.wait_for_selector('td')=}")

    if modat.does_selector_exist(frame, btn_selector, TIMEOUT_DEFAULT):
        logger.info(selector_type + " selector exists")

        try:
            # frame.locator(btn_selector).click()
            frame.wait_for_selector(btn_selector, timeout=TIMEOUT_DEFAULT).click()
            time.sleep(3)
        except:
            logger.info("Could not click the selector. Time has expired.")
        # wait_selector = page.getBtText('打刻しています')
        # page.wait_for_selector(wait_selector, timeout=TIMEOUT_DEFAULT)
        # page.wait_for_selector(wait_selector, state="hidden")

        touch_file = Path(make_file)
        touch_file.touch()
    else:
        logger.info("The " + selector_type + " selector doesn't exist")

    try:
        os.remove(PATH_WAITING)
        logger.info("Removed WAIT file")
    except:
        logger.info("There is not WAIT file")

    logger.info(selector_type + " finished")

    #
    # if is_wat_for_sleep:
    #     time.sleep(TIME_DURATION_DISCREPANCY)
    #     is_needed_reason_input = True

    # Input reason of discrepancy
    if is_needed_reason_input:
        page.goto(TS_ATTENDANCE_SHEET_PAGE_URL)

        frame = page.wait_for_selector("iframe").content_frame()

        logger.info(f"{frame.wait_for_selector('td')=}")

        info_panel_selector = 'span[data-dojo-attach-point="closeButtonNode"]'
        if modat.does_selector_exist(frame, info_panel_selector, TIMEOUT_DEFAULT):
            logger.info("info_panel_appeared")
            frame.wait_for_selector(info_panel_selector).click()
        else:
            logger.info("No_panel")

        # Initialize cnt and flags
        cnt_tuesday = 0
        today = args[2]
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
            logger.info(f"{year_month_day=}")
            if not (today == year_month_day):
                logger.info("Skip if not today")
                continue
            # Set selector
            daily_note_selector = "td#dailyNoteIcon" + year_month_day
            logger.debug(f"{daily_note_selector=}")
            # input reason
            frame.click(daily_note_selector)
            frame.wait_for_selector(
                "textarea#dialogNoteText2", timeout=TIMEOUT_DEFAULT
            ).fill(DISCREPANCY_REASON)
            frame.click("button#dialogNoteOk")
            logger.info("The discrepancy reason has been input")
