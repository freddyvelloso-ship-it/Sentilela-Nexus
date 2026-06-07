# SUPREME V5 - Recria atalhos na area de trabalho
# Execute: .\CRIAR_ATALHOS.ps1

$Desktop     = [Environment]::GetFolderPath("Desktop")
$ProjectDir  = Split-Path $MyInvocation.MyCommand.Path
$ws          = New-Object -ComObject WScript.Shell

# Atalho 1: Launcher IPED (fluxo completo)
$sc1 = $ws.CreateShortcut("$Desktop\SUPREME V5 - IPED.lnk")
$sc1.TargetPath       = "powershell.exe"
$sc1.Arguments        = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ProjectDir\LAUNCHER_IPED.ps1`""
$sc1.WorkingDirectory = $ProjectDir
$sc1.Description      = "SUPREME V5 - Iniciar sessao IPED com telemetria"
$sc1.IconLocation     = "C:\iped-test-case\IPED-SearchApp.exe,0"
$sc1.Save()
Write-Host "Atalho criado: SUPREME V5 - IPED.lnk" -ForegroundColor Green

# Atalho 2: Sentinela (abre direto no browser)
$sentinelaUrl = "https://localhost/sentinela/"
$sc2 = $ws.CreateShortcut("$Desktop\SENTINELA.lnk")
$sc2.TargetPath       = "powershell.exe"
$sc2.Arguments        = "-ExecutionPolicy Bypass -WindowStyle Hidden -Command `"Start-Process '$sentinelaUrl'`""
$sc2.WorkingDirectory = $ProjectDir
$sc2.Description      = "SENTINELA - Dashboard SUPREME V5"
$sc2.IconLocation     = "%SystemRoot%\System32\shell32.dll,23"
$sc2.Save()
Write-Host "Atalho criado: SENTINELA.lnk" -ForegroundColor Green

Write-Host ""
Write-Host "Pronto. Use 'SUPREME V5 - IPED' para iniciar uma sessao." -ForegroundColor Cyan
Write-Host "Use 'SENTINELA' para abrir o dashboard." -ForegroundColor Cyan
