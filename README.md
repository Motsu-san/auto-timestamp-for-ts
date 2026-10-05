# auto-timestamp-for-ts
Team spiritの勤怠打刻をPCのログインやショートカットで自動で実施するためのスクリプト寄せ集めです。


A collection of scripts to automate Team spirit attendance input via PC login or shortcut.

# Environments
OS: windows

Python: 3.12.0

Requirements: See requirements.txt

# Instruction [WIP]

python仮想環境を準備して、
タスクスケジューラを使ってbatを実行する。

## PCイベントの記録
`StartPAD_auto_timestamp_in.bat` 実行時に `record_pc_events.py` が前日までの未記録日の
スリープ・蓋閉じ・画面オフ・休止・シャットダウン・起動・画面ロックの時刻を `log/auto_timestamp_inout.log` に記録する。
画面ロックはイベントログ(Security)が管理者権限なしでは読めないため、
`task_xml_example/trigger_record_session_lock.xml` をタスクスケジューラに登録してロック時に記録する。

# Reference
休日判定: [日本の祝日を判定するBATファイルを書いた件](https://qiita.com/hiro0156/items/26660191ed9ec3e1044f)
