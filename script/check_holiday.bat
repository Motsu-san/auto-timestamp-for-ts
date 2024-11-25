@if not "%~0"=="%~dp0.\%~nx0" start /min cmd /c,"%~dp0.\%~nx0" %* & goto :eof
@echo off
:: ###############################################################
:: #   本邦休日判定スクリプト
:: #   @param       Check date in yyyy/mm/dd. If omitted, today is assumed.
:: #   @return      0       ... 確実に祝日
:: #                1       ... おそらく平日
:: #                9       ... error
:: #   @usage       check_holiday.bat || ”平日に必ず実行させるジョブ”
:: ###############################################################

:: 引数チェック
if "%1"=="" (
    set CHECK_DATE=%DATE%
) else (
    :: エラーチェックは(面倒なので)省略...
    set CHECK_DATE="%1"
)

:: 内閣府提供の祝日ファイルをキャッシュするディレクトリ
set CACHE_PATH=%~dp0

:: 祝日登録ファイル名
set HOLIDAY_FILE=%CACHE_PATH%holiday.csv
echo %HOLIDAY_FILE%

:: Download Holidays File
:: In bat files, date processing (especially addition and subtraction) is troublesome, so judgment of old updates, etc. is omitted → reacquisition is manual
if not exist %HOLIDAY_FILE% (
    echo "There is not a holiday file."
    powershell -Command "(New-Object Net.WebClient).DownloadFile('https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv', '%HOLIDAY_FILE%')"
)

if exist %HOLIDAY_FILE% (
    echo "Got a holiday file"
    del LOST_HOLIDAY_FILE
) else (
    echo "Lost a holiday file" > LOST_HOLIDAY_FILE
    exit /b 9
)
:: By the way, the file modification date and time can be taken from the following.
:: Someone please implement the periodic re-retrieval process...
:: for %%i in ( "%HOLIDAY_FILE%" ) do echo 祝日ファイル更新日時: %%~ti

:: If it's Saturday or Sunday, return 0 and exit.
call :set_week %CHECK_DATE%
if %WEEK% equ 0 (
    echo "weekend"
    exit /b 0
)

:: set_weekで操作した日付表現をcsvに合わせる.
set TODAY_FORMATED=%y%/%m%/%d%

:: CSVに祝日として登録されていれば 0 を返却して終了.
findstr %TODAY_FORMATED%, %HOLIDAY_FILE%
if "%ERRORLEVEL%"=="0" (
    echo "national holiday"
    exit /b 0
)

:: 年末年始（12月31日～1月3日）なら 0 を返却して終了.
:: 月日を2桁に固定するため、既定の桁数に削り(右から2桁)、出力.
set d=0%d%
set m=0%m%
set TUKIHI=%m:~-2%%d:~-2%

:: 都合に合わせて休日を自由に調整可能(祝日に関わらず毎年固定の休日)
set TRUE_FALSE=FALSE
IF %TUKIHI% equ 1229 set TRUE_FALSE=TRUE
IF %TUKIHI% equ 1230 set TRUE_FALSE=TRUE
IF %TUKIHI% equ 1231 set TRUE_FALSE=TRUE
IF %TUKIHI% equ 0101 set TRUE_FALSE=TRUE
IF %TUKIHI% equ 0102 set TRUE_FALSE=TRUE
IF %TUKIHI% equ 0103 set TRUE_FALSE=TRUE
IF %TRUE_FALSE%==TRUE (
    echo "business holiday"
    exit /b 0
)

:: 上記いずれでもなければ平日として終了.
echo WORKDAY > WORKDAY
exit /b 1


:: ===========================================
:: 以下、batで曜日を判定するためのサブルーチン.
:: 引用と感謝 -> https://casualdevelopers.com/tech-tips/how-to-calc-week-day-with-bat/
:: 引数は，「2024/04/08」 の0埋め書式対応.
:: ===========================================

:set_week
set TODAY=%1
echo %TODAY%

:: 日付の分解.
set h=%TODAY:~0,2%
set y=%TODAY:~2,2%
set m=%TODAY:~5,2%
set d=%TODAY:~8,2%

:: remove 0
if "%h:~0,1%"=="0" (set h=%h:~1%)
if "%y:~0,1%"=="0" (set y=%y:~1%)
if "%m:~0,1%"=="0" (set m=%m:~1%)
if "%d:~0,1%"=="0" (set d=%d:~1%)

:: 1月と2月は13月と14月に変換.
if %m%==1 ( set /a y-=1&set /a m+=12 )
if %m%==2 ( set /a y-=1&set /a m+=12 )

:: ツェラーの公式.
:: 出力は土曜日が0で土日月火水木金と順番に0~6で表される。.
for /f %%i in ('powershell -Command "$d=%d%; $m=%m%; $y=%y%; $h=%h%; [Math]::Floor(( $d + 13*($m+1)/5 + $y + $y/4 - 2*$h + $h/4 ) %% 7)"') do set /a week_value=%%i

:: 休日とする曜日の設定.
if %week_value%==0 set WEEK=0
if %week_value%==1 set WEEK=0
if %week_value%==2 set WEEK=1
if %week_value%==3 set WEEK=1
if %week_value%==4 set WEEK=1
if %week_value%==5 set WEEK=1
if %week_value%==6 set WEEK=1
exit /b
