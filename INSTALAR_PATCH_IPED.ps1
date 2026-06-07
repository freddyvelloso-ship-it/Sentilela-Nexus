# SUPREME V5 - Instalador do patch Java no IPED
# Compila SupremeAuditLogger.java e instala em plugins\ do IPED
# Execute: .\INSTALAR_PATCH_IPED.ps1

Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SUPREME V5 - Instalador do Patch Java" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar Java
Write-Host "[1/4] Verificando Java..." -ForegroundColor Yellow
$javac = $null
$javaHome = $null
$javaVersion = javac -version 2>&1
if ($LASTEXITCODE -eq 0) {
    $javac = "javac"
    $javaHome = Split-Path (Split-Path (Get-Command javac).Source)
    Write-Host "      OK: $javaVersion" -ForegroundColor Green
} else {
    foreach ($pattern in @("$env:ProgramFiles\Eclipse Adoptium\jdk*","$env:ProgramFiles\Java\jdk*","$env:ProgramFiles\Microsoft\jdk*","C:\jdk*")) {
        $found = Get-ChildItem $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found -and (Test-Path "$($found.FullName)\bin\javac.exe")) {
            $javac = "$($found.FullName)\bin\javac.exe"
            $javaHome = $found.FullName
            Write-Host "      JDK: $javac" -ForegroundColor Green
            break
        }
    }
    if (-not $javac) {
        Write-Host "ERRO: JDK nao encontrado. Instale em: https://adoptium.net/" -ForegroundColor Red
        exit 1
    }
}

# Derivar jar tool: se javac esta no PATH, jar tambem esta
$javacFull = (Get-Command javac -ErrorAction SilentlyContinue).Source
if ($javacFull) {
    $jarTool = Join-Path (Split-Path $javacFull) "jar.exe"
    if (-not (Test-Path $jarTool)) { $jarTool = "jar" }
} else {
    $jarTool = "jar"
}

# 2. Localizar IPED
Write-Host "[2/4] Localizando IPED..." -ForegroundColor Yellow

$IPED_HOME = $env:IPED_HOME
if (-not $IPED_HOME) {
    $candidates = @("C:\iped", "C:\IPED", "C:\iped-4.2", "C:\iped-4.1",
                    "$env:ProgramFiles\IPED", "$env:LOCALAPPDATA\IPED", "C:\iped-test-case")
    foreach ($c in $candidates) {
        $hasJar = Test-Path "$c\iped.jar"
        $hasExe = Test-Path "$c\IPED-SearchApp.exe"
        $hasJar2 = Test-Path "$c\iped-searchapp.jar"
        if ($hasJar -or $hasExe -or $hasJar2) { $IPED_HOME = $c; break }
    }
}

if (-not $IPED_HOME -or -not (Test-Path $IPED_HOME)) {
    $IPED_HOME = [Microsoft.VisualBasic.Interaction]::InputBox(
        "Informe o caminho completo da pasta do IPED (onde esta o iped.jar ou IPED-SearchApp.exe):",
        "SUPREME V5 - Caminho do IPED", "C:\iped")
}

if (-not (Test-Path $IPED_HOME)) {
    Write-Host "ERRO: Caminho nao encontrado: $IPED_HOME" -ForegroundColor Red
    exit 1
}
Write-Host "      IPED: $IPED_HOME" -ForegroundColor Green

# Coletar TODOS os JARs do IPED recursivamente (Lucene, iped-app, etc)
Write-Host "      Buscando JARs do IPED..." -ForegroundColor DarkGray
$allJars = Get-ChildItem $IPED_HOME -Recurse -Filter "*.jar" -ErrorAction SilentlyContinue
if ($allJars.Count -eq 0) {
    Write-Host "AVISO: Nenhum JAR encontrado em $IPED_HOME" -ForegroundColor Yellow
    Write-Host "       O IPED pode usar um launcher nativo (.exe). Verifique se ha uma pasta lib\ ou jars\." -ForegroundColor Yellow
} else {
    Write-Host "      $($allJars.Count) JARs encontrados." -ForegroundColor Green
    $luceneJar = $allJars | Where-Object { $_.Name -match "lucene-core" } | Select-Object -First 1
    if ($luceneJar) {
        Write-Host "      Lucene: $($luceneJar.FullName)" -ForegroundColor Green
    } else {
        Write-Host "AVISO: lucene-core nao encontrado. Buscando no Maven local..." -ForegroundColor Yellow
        # Tentar no cache Maven local
        $mavenCache = "$env:USERPROFILE\.m2\repository\org\apache\lucene\lucene-core"
        if (Test-Path $mavenCache) {
            $luceneJar = Get-ChildItem $mavenCache -Recurse -Filter "lucene-core-*.jar" -Exclude "*sources*","*javadoc*" | Select-Object -First 1
            if ($luceneJar) {
                Write-Host "      Lucene (Maven): $($luceneJar.FullName)" -ForegroundColor Green
            }
        }
    }
}

# Montar classpath: todos os JARs do IPED + Lucene Maven (se necessario)
$cpParts = @(".")
foreach ($jar in $allJars) { $cpParts += $jar.FullName }
if ($luceneJar -and ($cpParts -notcontains $luceneJar.FullName)) {
    $cpParts += $luceneJar.FullName
}
$classpath = $cpParts -join ";"
Write-Host "      Classpath: $($cpParts.Count) entradas" -ForegroundColor DarkGray

# 3. Compilar SupremeAuditLogger.java
Write-Host "[3/4] Compilando SupremeAuditLogger.java..." -ForegroundColor Yellow

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcFile   = "$scriptDir\supreme-iped-integration\iped-patch\src\main\java\iped\app\ui\SupremeAuditLogger.java"
$outDir    = "$scriptDir\_patch_build\out"
$patchJar  = "$scriptDir\_patch_build\supreme-audit-patch.jar"

if (-not (Test-Path $srcFile)) {
    Write-Host "ERRO: $srcFile nao encontrado." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Remove-Item "$outDir\*" -Recurse -Force -ErrorAction SilentlyContinue

$compileOut = & $javac -cp $classpath -d $outDir $srcFile 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO de compilacao:" -ForegroundColor Red
    $compileOut | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "O IPED usa launcher nativo (.exe)? Se sim, os JARs podem estar em subpastas." -ForegroundColor Yellow
    Write-Host "Rode: Get-ChildItem '$IPED_HOME' -Recurse -Filter '*.jar' | Select FullName" -ForegroundColor Yellow
    exit 1
}
Write-Host "      Compilado." -ForegroundColor Green

# Criar JAR
& $jarTool cf $patchJar -C $outDir . 2>&1 | Out-Null
if (-not (Test-Path $patchJar)) {
    Write-Host "ERRO: JAR nao gerado." -ForegroundColor Red
    exit 1
}
Write-Host "      JAR: $patchJar" -ForegroundColor Green

# 4. Instalar no IPED
Write-Host "[4/4] Instalando em $IPED_HOME\plugins\..." -ForegroundColor Yellow
$pluginsDir = "$IPED_HOME\plugins"
New-Item -ItemType Directory -Force -Path $pluginsDir | Out-Null
Copy-Item $patchJar "$pluginsDir\supreme-audit-patch.jar" -Force
Write-Host "      Instalado." -ForegroundColor Green

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PATCH INSTALADO COM SUCESSO" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Log de auditoria sera gerado em:" -ForegroundColor White
Write-Host "  $env:USERPROFILE\supreme_audit.ndjson" -ForegroundColor White
Write-Host ""
Write-Host "  Execute agora: .\LAUNCHER_IPED.ps1" -ForegroundColor Yellow
Write-Host ""
