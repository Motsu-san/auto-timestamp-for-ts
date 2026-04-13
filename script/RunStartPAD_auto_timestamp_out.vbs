' ウィンドウを表示せずに StartPAD_auto_timestamp_out.bat を実行
CreateObject("WScript.Shell").Run "cmd /c """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\StartPAD_auto_timestamp_out.bat""", 0, False
