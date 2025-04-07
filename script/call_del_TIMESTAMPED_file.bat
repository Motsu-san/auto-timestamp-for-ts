@if not "%~0"=="%~dp0.\%~nx0" start /min cmd /c,"%~dp0.\%~nx0" %* & goto :eof
@echo off
setlocal

cd /d %~dp0

call "..\..\venv\venv_script\Scripts\activate"
python "del_TIMESTAMPED_files.py"
