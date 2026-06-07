# criar_atalho_sentinela.ps1
# Execute este script UMA VEZ para criar o atalho na área de trabalho.

$LauncherPs1 = "C:\Users\nunas\OneDrive\Documentos\Claude\Projects\SUPREME V4 - IPED (1)\sentinela\launcher\launch_sentinela.ps1"
$Desktop     = [Environment]::GetFolderPath("Desktop")
$Shortcut    = "$Desktop\SENTINELA.lnk"

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($Shortcut)
$sc.TargetPath       = "powershell.exe"
$sc.Arguments        = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$LauncherPs1`""
$sc.WorkingDirectory = Split-Path $LauncherPs1
$sc.Description      = "SENTINELA - Dashboard de Pesquisa SUPREME V4"
$sc.IconLocation     = "%SystemRoot%\System32\shell32.dll,23"   # ícone de rede/monitor
$sc.Save()

Write-Host "Atalho criado em: $Shortcut" -ForegroundColor Green
