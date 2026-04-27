import os
import sys
import time
import datetime
import math
import re
import argparse
from logging import StreamHandler, basicConfig, getLogger, handlers
from pathlib import Path

import nest_asyncio  # type: ignore
from playwright.sync_api import sync_playwright
from playwright.sync_api._generated import *

import module_auto_timestamp as modat
import const

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--punch_in", action="store_true", help="run in punch-in mode")
parser.add_argument("-o", "--punch_out", action="store_true", help="run in punch-out mode")
parser.add_argument("-d", "--debug", action="store_true", help="output logs with debug messages")
args = parser.parse_args()

nest_asyncio.apply()

TIMEOUT_DEFAULT = const.TIMEOUT_DEFAULT
TIMEOUT_LOADING = const.TIMEOUT_LOADING
ACCOUNT_ADDRESS = const.ACCOUNT_ADDRESS
TIMEOUT_LOGIN = const.TIMEOUT_LOGIN
PATH_WORKDAY = const.PATH_WORKDAY
PATH_TIMESTAMP_IN = const.PATH_TIMESTAMP_IN
PATH_TIMESTAMP_OUT = const.PATH_TIMESTAMP_OUT
START_TIME_STAMP = const.START_TIME_STAMP
TS_PAGE_URL = const.TS_PAGE_URL
TIME_DURATION_DISCREPANCY = const.TIME_DURATION_DISCREPANCY
TS_ATTENDANCE_SHEET_PAGE_URL = const.TS_ATTENDANCE_SHEET_PAGE_URL
PATH_WAITING = const.PATH_WAITING
PATH_REASON_INPUT = const.PATH_REASON_INPUT
LOG_FILE_PATH = str(Path("log").absolute()) + r"\auto_timestamp_inout.log"
MAX_RETRY_COUNT_CLICK = const.MAX_RETRY_COUNT_CLICK


def _wait_for_ts_page_frame(page):
    # iframe 出現後、中の表（td）まで TIMEOUT_LOADING（ms）で待つ
    try:
        handle = page.wait_for_selector("iframe", timeout=TIMEOUT_LOADING)
    except TimeoutError:
        logger.error(
            f"Timeout waiting for iframe (timeout: {TIMEOUT_LOADING}ms). URL: {page.url}"
        )
        sys.exit(1)
    frame = handle.content_frame()
    if frame is None:
        logger.error(
            f"iframe has no content frame (not ready or wrong page). URL: {page.url}"
        )
        sys.exit(1)
    try:
        frame.wait_for_selector("td", timeout=TIMEOUT_LOADING)
        logger.debug("Page content loaded successfully - ready to check for timestamp button")
    except TimeoutError:
        logger.error(
            f"Timeout waiting for page content to load (timeout: {TIMEOUT_LOADING}ms). Page may not have loaded correctly."
        )
        sys.exit(1)
    return frame


current_time = datetime.datetime.now()
logger = getLogger(__name__)
if args.debug:
    logger.setLevel("DEBUG")
else:
    logger.setLevel("INFO")
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
    basicConfig(handlers=[handler, rotatingfilehandler])
    # basicConfig(level="DEBUG")
    logger.info("=== AUTO TIMESTAMP INOUT === " + current_time.strftime("%Y/%m/%d %H:%M:%S.%f"))

    if args.punch_in and args.punch_out:
        logger.error("Please select either option '-i' or '-o'")
        sys.exit()
    elif args.punch_out:
        logger.info("Punch-out mode")
    else:
        logger.info("Punch-in mode")

    is_workday = os.path.isfile(PATH_WORKDAY)
    is_timestamp_in = os.path.isfile(PATH_TIMESTAMP_IN)
    is_timestamp_out = os.path.isfile(PATH_TIMESTAMP_OUT)
    is_waiting = os.path.isfile(PATH_WAITING)
    is_needed_reason_input = False
    is_wait_for_sleep = False
    waiting_file_created = False
    if is_waiting:
        logger.info("previous process existing, finish.")
        sys.exit()

    if not is_workday:
        logger.info("Not workday")
        sys.exit()

    if not args.punch_out:
        if not is_timestamp_in:
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
                waiting_file_created = True
                time.sleep(wait_time.total_seconds())
            if wait_time.total_seconds() >= TIME_DURATION_DISCREPANCY:
                # Input reason of discrepancy
                is_needed_reason_input = True
                touch_file = Path(PATH_REASON_INPUT)
                touch_file.touch()
        else:
            logger.info("Has already punch in")
            sys.exit()
    else:
        if is_timestamp_in and not is_timestamp_out:
            btn_selector = "input#btnEtInput"
            selector_type = "punch-out"
            make_file = PATH_TIMESTAMP_OUT
            is_wait_for_sleep = True
        elif is_timestamp_in and is_timestamp_out:
            logger.info("Has already punch out")
            sys.exit()
        else:
            logger.error("There is something wrong")
            logger.debug("===== inputs =====")
            logger.debug(f"{is_waiting=}")
            logger.debug(f"{is_workday=}")
            logger.debug(f"{args.punch_out=}")
            logger.debug(f"{is_timestamp_in=}")
            logger.debug(f"{is_timestamp_out=}")
            logger.debug("===== outputs =====")
            logger.debug(f"{os.path.isfile(PATH_WAITING)=}")
            logger.debug(f"{is_needed_reason_input=}")
            sys.exit()

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
        logger.debug(f"Navigating to {TS_PAGE_URL}")
        page.goto(TS_PAGE_URL, timeout=TIMEOUT_LOGIN)
        logger.debug("Page navigation completed")
    except TimeoutError:
        logger.error(f"Timeout navigating to {TS_PAGE_URL} (timeout: {TIMEOUT_LOGIN}ms)")
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
        page.wait_for_url(TS_PAGE_URL, timeout=TIMEOUT_LOGIN)
        logger.debug("login")

    except TimeoutError:
        logger.error("Could not transition to the specified page. Time has expired.")
        sys.exit()

    frame = _wait_for_ts_page_frame(page)

    retry_count = 0
    click_success = False
    timestamp_confirmed = False

    if modat.does_selector_exist(frame, btn_selector, TIMEOUT_LOADING):
        logger.info(selector_type + " selector exists")

        while retry_count < MAX_RETRY_COUNT_CLICK and not click_success and not timestamp_confirmed:
            try:
                frame.wait_for_selector(btn_selector).click()
                click_success = True
                logger.info("Successfully clicked the selector")
            except:
                logger.info("Could not click the selector. Time has expired.")
                click_success = False

                # If click failed, check on timestamp confirmation page
                logger.info("Checking timestamp on confirmation page...")
                try:
                    page.goto(
                        "https://tier4.lightning.force.com/lightning/n/teamspirit__AtkWorkTimeTab",
                        timeout=TIMEOUT_LOADING
                    )
                    frame = _wait_for_ts_page_frame(page)

                    is_punch_in = not args.punch_out
                    timestamp_confirmed = modat.check_today_timestamp(
                        page, is_punch_in
                    )

                    if timestamp_confirmed:
                        logger.info("Timestamp confirmed on the page. No retry needed.")
                    else:
                        retry_count += 1
                        logger.info(
                            f"Timestamp not found. Retrying... ({retry_count}/{MAX_RETRY_COUNT_CLICK})"
                        )

                        # Return to original page
                        if retry_count < MAX_RETRY_COUNT_CLICK:
                            page.goto(TS_PAGE_URL, timeout=TIMEOUT_LOADING)
                            frame = _wait_for_ts_page_frame(page)
                            # Check if selector exists again
                            if not modat.does_selector_exist(frame, btn_selector):
                                logger.info("Selector no longer exists. Stopping retry.")
                                break
                except Exception as e:
                    logger.error(f"Error checking timestamp: {e}")
                    retry_count += 1
                    if retry_count < MAX_RETRY_COUNT_CLICK:
                        # Return to original page
                        page.goto(TS_PAGE_URL, timeout=TIMEOUT_LOADING)
                        frame = _wait_for_ts_page_frame(page)

        # Create file only if click succeeded or timestamp confirmed
        if click_success or timestamp_confirmed:
            touch_file = Path(make_file)
            touch_file.touch()
            logger.info(f"Created {make_file} file")
        else:
            logger.warning(
                f"Failed to click and timestamp not confirmed after {MAX_RETRY_COUNT_CLICK} retries"
            )
    else:
        logger.error("The " + selector_type + " selector doesn't exist")

    try:
        os.remove(PATH_WAITING)
        logger.info("Removed WAIT file")
    except FileNotFoundError:
        if waiting_file_created:
            logger.warning(
                "WAIT file was created in this run but is missing at cleanup"
            )
        else:
            logger.info(
                "WAIT file was not created"
            )
    except OSError as e:
        logger.warning(f"Failed to remove WAIT file: {e}")

    logger.info(selector_type + " finished")
