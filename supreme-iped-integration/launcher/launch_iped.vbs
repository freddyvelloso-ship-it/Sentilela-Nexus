' Lanca o launcher PowerShell sem janela de terminal
Dim ps, launcher
launcher = Replace(WScript.ScriptFullName, "launch_iped.vbs", "launch_iped.ps1")
ps = "powershell.exe -ExecutionPolicy Bypass -File """ & launcher & """"
CreateObject("WScript.Shell").Run ps, 0, False
