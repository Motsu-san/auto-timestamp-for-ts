#     5.前項に基づき、半日単位で取得した場合の始業および終業時刻は次の通りとする。
# 午前休暇 午後2時~午後6時
# 午後休暇 午前9時~午後1時
# https://drive.google.com/file/d/1g7ivADu5etyI7_V3a2aq7oPjpRfpdaKV/view
import json

open_json = open('const_pri.json')
const_pri_dict = json.load(open_json)

# CONST parameter
TIMEOUT_DEFAULT = 1000.0
ACCOUNT_ADDRESS = const_pri_dict['ACCOUNT_ADDRESS']
TIMEOUT_LOGIN = 120000.0
PATH_WORKDAY = "WORKDAY"
PATH_TIMESTAMP_IN = "TIMESTAMPED_IN"
PATH_TIMESTAMP_OUT = "TIMESTAMPED_OUT"
PATH_WAITING = "WAITING"
START_TIME_STAMP = "06:00"
TS_PAGE_URL = const_pri_dict['TS_PAGE_URL']
TS_ATTENDANCE_SHEET_PAGE_URL = const_pri_dict['TS_ATTENDANCE_SHEET_PAGE_URL']

START_REST_TIME_DEFAULT = "12:00"
END_REST_TIME_DEFAULT = "13:00"
TIME_DURATION_DISCREPANCY = 1800.0
DISCREPANCY_REASON = "①"

class ConstRestTimePattern:
    # def __init__(self):
    #     self.START_REST_TIME2 = "07:15"
    #     self.END_REST_TIME2 = "08:45"
    #     self.START_REST_TIME3 = "18:00"
    #     self.END_REST_TIME3 = "20:00"

    def __init__(self, arg):
        if arg == "Friday":
            self.START_REST_TIME2 = "06:45"
            self.END_REST_TIME2 = "09:30"
            self.START_REST_TIME3 = "17:15"
            self.END_REST_TIME3 = "20:15"
        else:
            self.START_REST_TIME2 = "06:30"
            self.END_REST_TIME2 = "08:15"
            self.START_REST_TIME3 = "18:15"
            self.END_REST_TIME3 = "20:15"


class ConstPersonHour:
    def __init__(self):
        self.RD1_NOT_GI = "01:00"
        self.IN_HOUSE_MEETING = "01:30"
        self.ATTENDANCE_RELATED = "01:00"
