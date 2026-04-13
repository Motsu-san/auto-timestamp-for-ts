' ウィンドウを表示せずに StartPAD_auto_timestamp_in.bat を実行
CreateObject("WScript.Shell").Run "cmd /c """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\StartPAD_auto_timestamp_in.bat""", 0, False
