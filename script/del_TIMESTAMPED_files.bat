@if not "%~0"=="%~dp0.\%~nx0" start /min cmd /c,"%~dp0.\%~nx0" %* & goto :eof
@echo off
setlocal enabledelayedexpansion

cd /d %~dp0

:: Check date
set CHECK_DATE=%DATE%
set YYYYMMDD_TODAY=%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%
echo %YYYYMMDD_TODAY%

if exist WORKDAY (
    echo There is WORKDAY file.
    :: Check file date
    for %%i in (WORKDAY) do set FILE_DATE=%%~ti
    echo !FILE_DATE!
    set YYYY=!FILE_DATE:~0,4!
    set MM=!FILE_DATE:~5,2!
    set DD=!FILE_DATE:~8,2!
    set YYYYMMDD_FILE=!YYYY!!MM!!DD!
    echo !YYYYMMDD_FILE!

    if !YYYYMMDD_TODAY! gtr !YYYYMMDD_FILE! (
        del TIMESTAMPED_IN
        del TIMESTAMPED_OUT
        del WORKDAY
        call check_holiday.bat
    )
) else (
    echo There is not WORKDAY file.
    del TIMESTAMPED_IN
    del TIMESTAMPED_OUT
    call check_holiday.bat
)
