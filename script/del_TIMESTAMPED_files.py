import os
import argparse
import datetime
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


def get_file_date(filepath):
    """Get the last modified date of a file in YYYYMMDD format."""
    try:
        timestamp = os.path.getmtime(filepath)
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y%m%d")
    except FileNotFoundError:
        return None


def main():
    current_date = datetime.datetime.today().strftime("%Y%m%d")
    logger.debug(f"Today's date: {current_date}")

    workday_file = const.PATH_WORKDAY
    # WORKDAY file management is handled by check_holiday.py
    timestamped_files = ["TIMESTAMPED_IN", "TIMESTAMPED_OUT", "REASON_INPUT"]
    check_holiday_script = "check_holiday.py"

    if os.path.exists(workday_file):
        logger.info("There is a WORKDAY file.")
        file_date = get_file_date(workday_file)
        logger.debug(f"WORKDAY file date: {file_date}")

        if file_date and current_date > file_date:
            logger.info("WORKDAY file is older than today's date.")
            # Delete timestamped files (WORKDAY is managed by check_holiday.py)
            for file in timestamped_files:
                if os.path.exists(file):
                    os.remove(file)
                    logger.info(f"Deleted: {file}")

            # Update WORKDAY file status (create or delete based on today's date)
            if os.path.exists(check_holiday_script):
                os.system(f"python {check_holiday_script}")
                logger.info("Updated WORKDAY file status.")
        else:
            logger.info("WORKDAY file is up to date. No files deleted.")
    else:
        logger.info("There is no WORKDAY file.")
        # Delete timestamped files
        for file in ["TIMESTAMPED_IN", "TIMESTAMPED_OUT"]:
            if os.path.exists(file):
                os.remove(file)
                logger.info(f"Deleted: {file}")

        # Update WORKDAY file status (create or delete based on today's date)
        if os.path.exists(check_holiday_script):
            os.system(f"python {check_holiday_script}")
            logger.info("Updated WORKDAY file status.")


if __name__ == "__main__":
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description="Check and delete TIMESTAMPED files")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable DEBUG log level")
    args = parser.parse_args()

    # ログレベルの設定
    log_level = "DEBUG" if args.debug else "INFO"

    # ロガーとハンドラーのレベルを設定
    logger.setLevel(log_level)
    handler = StreamHandler()
    handler.setLevel(log_level)
    rotatingfilehandler.setLevel(log_level)

    basicConfig(handlers=[handler, rotatingfilehandler])
    logger.info("=== CHECK TIMESTAMPED FILES === " + current_time.strftime("%Y/%m/%d %H:%M:%S.%f"))

    main()
