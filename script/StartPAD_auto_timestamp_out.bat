@if not "%~0"=="%~dp0.\%~nx0" start /min cmd /c,"%~dp0.\%~nx0" %* & goto :eof
@echo off
setlocal

cd /d %~dp0

@REM Check date
set CHECK_DATE=%date%
set YYYY=%date:~0,4%
set MM=%date:~5,2%
set DD=%date:~8,2%
set YYYYMMDD_TODAY=%YYYY%-%MM%-%DD%
echo %YYYYMMDD_TODAY%

call "..\..\venv\venv_script\Scripts\activate"
start /min python "auto_timestamp_inout.py" -o
start /min python "auto_input_non_working_time_and_work_place.py" -D %YYYYMMDD_TODAY%
