import json

open_json = open("const_pri.json")
const_pri_dict = json.load(open_json)

# CONST parameter
TIMEOUT_DEFAULT = 1000.0
TIMEOUT_LOADING = 15000.0
TIMEOUT_LOGIN = 120000.0
PATH_WORKDAY = "WORKDAY"
PATH_TIMESTAMP_IN = "TIMESTAMPED_IN"
PATH_TIMESTAMP_OUT = "TIMESTAMPED_OUT"
PATH_WAITING = "WAITING"

TIME_DURATION_DISCREPANCY = 1800.0
PATH_REASON_INPUT = "REASON_INPUT"
MAX_RETRY_COUNT_CLICK = 3

# private CONST parameter
ACCOUNT_ADDRESS = const_pri_dict["ACCOUNT_ADDRESS"]
TS_PAGE_URL = const_pri_dict["TS_PAGE_URL"]
TS_ATTENDANCE_SHEET_PAGE_URL = const_pri_dict["TS_ATTENDANCE_SHEET_PAGE_URL"]
START_TIME_STAMP = const_pri_dict["START_TIME_STAMP"]
START_REST_TIME_DEFAULT = const_pri_dict["START_REST_TIME_DEFAULT"]
END_REST_TIME_DEFAULT = const_pri_dict["END_REST_TIME_DEFAULT"]
OFFICE_DAYS = const_pri_dict["OFFICE_DAYS"]


class ConstRestTimePattern:
    def __init__(self, arg):
        pattern = "Office_day" if arg == "Office_day" else "Other"
        rest_time_data = const_pri_dict["REST_TIME_PATTERNS"][pattern]
        self.START_REST_TIME2 = rest_time_data["START_REST_TIME2"]
        self.END_REST_TIME2 = rest_time_data["END_REST_TIME2"]
        self.START_REST_TIME3 = rest_time_data["START_REST_TIME3"]
        self.END_REST_TIME3 = rest_time_data["END_REST_TIME3"]


class ConstPersonHour:
    def __init__(self):
        person_hour_data = const_pri_dict["PERSON_HOUR"]
        self.RD1_NOT_GI = person_hour_data["RD1_NOT_GI"]
        self.IN_HOUSE_MEETING = person_hour_data["IN_HOUSE_MEETING"]
        self.ATTENDANCE_RELATED = person_hour_data["ATTENDANCE_RELATED"]
