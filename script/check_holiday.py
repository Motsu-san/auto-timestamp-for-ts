import os
import argparse
import datetime
import csv
import requests  # pyright: ignore
from logging import StreamHandler, basicConfig, getLogger, handlers
from pathlib import Path
import const

LOG_FILE_PATH = str(Path("log").absolute()) + r"\auto_timestamp_inout.log"

current_time = datetime.datetime.now()
logger = getLogger(__name__)
rotatingfilehandler = handlers.RotatingFileHandler(
    LOG_FILE_PATH,
    encoding="utf-8",
    maxBytes=100 * 1024,
    backupCount=20,
)


def download_holiday_file(file_path):
    """Download the Japanese holiday CSV file if it doesn't exist."""
    url = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(file_path, "wb") as file:
            file.write(response.content)
        logger.info("Holiday file downloaded successfully.")
    except requests.RequestException as e:
        logger.error(f"Error downloading holiday file: {e}")
        return False
    return True


def is_holiday(date_str, holiday_file):
    """Check if a given date is a public holiday."""
    if not os.path.exists(holiday_file):
        if not download_holiday_file(holiday_file):
            return 9  # Error code

    with open(holiday_file, newline="", encoding="shift_jis") as file:
        reader = csv.reader(file)
        next(reader)  # Skip header
        for row in reader:
            if row and row[0] == date_str:
                logger.info("National holiday or paid leave.")
                return 0  # Holiday

    return 1  # Not a holiday


def main(date_input=None):
    # Get current date if no input is provided
    if date_input is None:
        date = datetime.date.today()
    else:
        date = datetime.datetime.strptime(date_input, "%Y/%m/%d").date()

    logger.debug(f"Checking date: {date}")

    workday_file = const.PATH_WORKDAY
    is_holiday_today = False

    # Check if weekend
    if date.weekday() in [5, 6]:  # Saturday (5) or Sunday (6)
        logger.info("Weekend.")
        is_holiday_today = True
    else:
        # Check holiday CSV
        holiday_file = "holiday.csv"
        result = is_holiday(date.strftime("%Y/%m/%d"), holiday_file)
        if result == 0:
            is_holiday_today = True
        elif result == 9:
            # Error occurred, don't change WORKDAY file
            logger.error("Error checking holiday. WORKDAY file not modified.")
            return 9
        else:
            # Check fixed holidays (New Year's period)
            if date.strftime("%m%d") in ["1229", "1230", "1231", "0101", "0102", "0103"]:
                logger.info("Business holiday.")
                is_holiday_today = True

    # Delete WORKDAY file if it's a holiday
    if is_holiday_today:
        if os.path.exists(workday_file):
            os.remove(workday_file)
            logger.info("Deleted WORKDAY file (holiday).")
        return 0  # Holiday

    # Otherwise, mark as a workday
    with open(workday_file, "w") as file:
        file.write("WORKDAY\n")
    logger.info("Workday.")
    return 1  # Workday


if __name__ == "__main__":
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(
        description="Check if a date is a holiday and manage WORKDAY file"
    )
    parser.add_argument("-d", "--debug", action="store_true", help="Enable DEBUG log level")
    parser.add_argument(
        "date", nargs="?", help="Date to check in YYYY/MM/DD format (default: today)"
    )
    args = parser.parse_args()

    # ログレベルの設定
    log_level = "DEBUG" if args.debug else "INFO"

    # ロガーとハンドラーのレベルを設定
    logger.setLevel(log_level)
    handler = StreamHandler()
    handler.setLevel(log_level)
    rotatingfilehandler.setLevel(log_level)

    basicConfig(handlers=[handler, rotatingfilehandler])
    logger.info("=== CHECK HOLIDAY === " + current_time.strftime("%Y/%m/%d %H:%M:%S.%f"))

    exit(main(args.date))
