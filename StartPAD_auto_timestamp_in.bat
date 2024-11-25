@if not "%~0"=="%~dp0.\%~nx0" start /min cmd /c,"%~dp0.\%~nx0" %* & goto :eof
@echo off
setlocal

cd /d %~dp0

call "C:\Users\masahiro.sakamoto\venv\venv_script\Scripts\activate"
python "C:\Users\masahiro.sakamoto\script\auto_timestamp_inout.py"
