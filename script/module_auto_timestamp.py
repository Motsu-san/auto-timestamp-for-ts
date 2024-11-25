import os
import sys
import datetime
from logging import getLogger

import nest_asyncio
from playwright.sync_api import sync_playwright
from playwright.sync_api._generated import *


import const
from const import ConstRestTimePattern, ConstPersonHour

# pip install re time nest_asyncio dotenv playwright

nest_asyncio.apply()

TIMEOUT_DEFAULT = const.TIMEOUT_DEFAULT
START_REST_TIME_DEFAULT = "12:00"
END_REST_TIME_DEFAULT = "13:00"
ID_OFFLINE_AND_REMOTE_WORK = "a25A70000000iuAIAQ"  #  出社+テレワーク

logger = getLogger(__name__)
logger.setLevel("DEBUG")


def login(page: Page, gmail_address: str):
    page.click('button[type="button"]:has-text("次へ")')
    page.wait_for_selector('input[type="password"]', state="visible")
    # page.wait_for_navigation()
    # with page.expect_navigation():
    #     if identifier_box := page.query_selector('input[name="identifier"]'):
    #         logger.info("Needed to input my mail")
    #         identifier_box.fill(gmail_address)
    #         identifier_box.press("Enter")
    #     elif identifier_box := page.query_selector(
    #         f'div[data-identifier="{gmail_address}"]'
    #     ):
    #         logger.info("There is my account")
    #         page.query_selector(f'div[data-identifier="{gmail_address}"]').click()
    #     else:
    #         logger.info("There is no account")
    #         page.query_selector("#identifierNext").click()

    with page.expect_navigation():
        # Inform the user to enter the password manually
        logger.info("Please enter your password in the browser.")
        # Wait for a specific element that appears after login
        page.wait_for_selector("ts-top-logo")
    # Wait for two-phase authentication
    # with page.expect_navigation():
    #     pass

    # <div class="VfPpkd-RLmnJb"></div>


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
    value = frame.input_value(selector)
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
    logger.info(f"work_status_title={work_status_title}")
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

    logger.info(f"start_time={start_time}")
    logger.info(f"end_time={end_time}")

    return start_time, end_time


def input_non_work_time(
    frame: Frame, td_start: str, td_end: str, const: ConstRestTimePattern
):

    # startRest2
    td_start_time = string_to_datetime(td_start)
    td_end_time = string_to_datetime(td_end)
    # Check if rest time input is needed
    is_needed_rest2_input = td_start_time < string_to_datetime(const.START_REST_TIME2)
    is_needed_rest3_input = string_to_datetime(const.END_REST_TIME3) <= td_end_time
    # Check if the day is a am/pm paid holiday
    is_ampm_paid_holiday = (
        string_to_datetime(START_REST_TIME_DEFAULT) <= td_start_time
    ) or (td_end_time <= string_to_datetime(END_REST_TIME_DEFAULT))

    # Get the flag if my rest time is input
    if is_ampm_paid_holiday:
        is_start_rest_input = is_text_box_input(
            frame, "#startRest1", timeout=TIMEOUT_DEFAULT
        )
    else:
        is_start_rest_input = is_text_box_input(
            frame, "#startRest2", timeout=TIMEOUT_DEFAULT
        )
    logger.info(f"{is_start_rest_input=}")

    button_selector = 'input.pb_btn_plusL[type="button"][title="休憩時間入力行追加"]'
    # Skip if my rest time is input
    if not is_start_rest_input:
        if is_needed_rest2_input:
            logger.info(f"{is_needed_rest2_input=}")
            frame.wait_for_selector("#startRest2", timeout=TIMEOUT_DEFAULT).fill(
                const.START_REST_TIME2
            )
            frame.wait_for_selector("#endRest2", timeout=TIMEOUT_DEFAULT).fill(
                const.END_REST_TIME2
            )
        if is_needed_rest3_input:
            logger.info(f"{is_needed_rest3_input=}")
            frame.wait_for_selector(button_selector, state="visible")
            frame.click(button_selector)
            frame.wait_for_selector("#startRest3", timeout=TIMEOUT_DEFAULT).fill(
                const.START_REST_TIME3
            )
            frame.wait_for_selector("#endRest3", timeout=TIMEOUT_DEFAULT).fill(
                const.END_REST_TIME3
            )
        frame.wait_for_selector("#dlgInpTimeOk", timeout=TIMEOUT_DEFAULT).click()
        frame.wait_for_selector("#dlgInpTimeOk", state="hidden")
    else:
        logger.info(f"{"Working time has been already input. skipping"}")
        frame.wait_for_selector("#dlgInpTimeCancel", timeout=TIMEOUT_DEFAULT).click()
        frame.wait_for_selector("#dlgInpTimeCancel", state="hidden")


def input_work_place(frame: Frame):
    value = frame.input_value("#workLocationId")
    if not value == ID_OFFLINE_AND_REMOTE_WORK:
        logger.info(f"{"work location is not updated"}")
        frame.select_option("#workLocationId", value=ID_OFFLINE_AND_REMOTE_WORK)
        frame.wait_for_selector("#dlgInpTimeOk", timeout=TIMEOUT_DEFAULT).click()
        frame.wait_for_selector("#dlgInpTimeOk", state="hidden")
    else:
        logger.info(f"{"Work location is updated"}")
        frame.wait_for_selector("#dlgInpTimeCancel", timeout=TIMEOUT_DEFAULT).click()
        frame.wait_for_selector("#dlgInpTimeCancel", state="hidden")


def input_person_hour(
    frame: Frame,
    is_tier4_all_hands: bool,
    is_first_workday: bool,
    const: ConstPersonHour,
):
    # Get actual working time
    logger.info(f"{frame.wait_for_selector('#empWorkRealTime').text_content()=}")
    actual_working_time_message = frame.wait_for_selector(
        "#empWorkRealTime"
    ).text_content()
    target = "："  # 「：」より後ろ（時刻）を抽出したい
    idx = actual_working_time_message.find(target)
    actual_working_time = actual_working_time_message[idx + len(target) :]
    logger.info(f"{actual_working_time=}")
    # initialize RD1_GI time
    frame.wait_for_selector("#empInputTime0", timeout=TIMEOUT_DEFAULT).fill("")
    # Input RD1_NOT_GI time
    frame.wait_for_selector("#empInputTime1", timeout=TIMEOUT_DEFAULT).fill(
        const.RD1_NOT_GI
    )
    # Input IN_HOUSE_MEETING time if needed
    if is_tier4_all_hands:
        logger.info(f"{"TIER IV all hands held"}")
        frame.wait_for_selector("#empInputTime2", timeout=TIMEOUT_DEFAULT).fill(
            const.IN_HOUSE_MEETING
        )
    if is_first_workday:
        logger.info(f"{"Added Attendance related time"}")
        frame.wait_for_selector("#empInputTime4", timeout=TIMEOUT_DEFAULT).fill(
            const.ATTENDANCE_RELATED
        )
    # Get total input working time
    frame.wait_for_selector(
        "#empWorkRealTime", timeout=TIMEOUT_DEFAULT
    ).click()  # needed to update empWorkTotalTime
    total_input_working_time = frame.wait_for_selector(
        "#empWorkTotalTime"
    ).text_content()
    logger.info(f"{total_input_working_time=}")
    # Get RD1_GI time
    rd1_gi_working_timedelta = str(
        string_to_datetime(actual_working_time)
        - string_to_datetime(total_input_working_time)
    )
    logger.info(f"{rd1_gi_working_timedelta=}")
    rd1_gi_working_time = rd1_gi_working_timedelta[
        :-3
    ]  # In [HH:MM:SS], ":SS" is deleted
    logger.info(f"{rd1_gi_working_time=}")
    frame.wait_for_selector("#empInputTime0", timeout=TIMEOUT_DEFAULT).fill(
        rd1_gi_working_time
    )
    frame.wait_for_selector("#empWorkOk", timeout=TIMEOUT_DEFAULT).click()
    frame.wait_for_selector("#empWorkOk", state="hidden")
