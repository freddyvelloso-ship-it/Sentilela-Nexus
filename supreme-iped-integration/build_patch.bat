@echo off
REM =============================================================================
REM build_patch.bat — Compila o patch SUPREME e prepara o IPED para lançamento
REM
REM Execute UMA VEZ após clonar o IPED e instalar JDK + Maven.
REM Após isso, use launch_iped.bat para lançar o IPED com o patch ativo.
REM =============================================================================

setlocal

set IPED_SOURCE=C:\iped-source
set IPED_APP=%IPED_SOURCE%\iped-app

echo ============================================================
echo  SUPREME V4 — Build do patch IPED
echo ============================================================
echo.

REM ── Passo 1: Copiar SupremeAuditLogger.java ──────────────────────────────────
echo [1/4] Copiando SupremeAuditLogger.java...
set "SRC=%~dp0iped-patch\src\main\java\iped\app\ui\SupremeAuditLogger.java"
set "DST=%IPED_APP%\src\main\java\iped\app\ui\SupremeAuditLogger.java"

if not exist "%SRC%" (
    echo [ERRO] SupremeAuditLogger.java nao encontrado em: %SRC%
    pause & exit /b 1
)
copy /Y "%SRC%" "%DST%" >nul
echo  ✓ Copiado.

REM ── Passo 2: Aplicar edição no ResultTableListener.java ─────────────────────
echo.
echo [2/4] ACAO MANUAL NECESSARIA:
echo  Abra o arquivo abaixo e insira o patch SUPREME conforme ResultTableListener.patch:
echo.
echo  %IPED_APP%\src\main\java\iped\app\ui\ResultTableListener.java
echo.
echo  Busque por: lastTableDoc = docId;
echo  Insira o bloco SUPREME antes dessa linha (veja ResultTableListener.patch).
echo.
set /p DONE=Ja aplicou o patch manualmente? (s/n):
if /i not "%DONE%"=="s" (
    echo Abortando. Aplique o patch e rode novamente.
    exit /b 0
)

REM ── Passo 3: Recompilar iped-app ─────────────────────────────────────────────
echo.
echo [3/4] Compilando iped-app (pode demorar ~1 min)...
cd /d "%IPED_APP%"
call mvn clean package -DskipTests -q
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Compilacao falhou. Verifique os erros acima.
    pause & exit /b 1
)
echo  ✓ iped-app compilado.

REM ── Passo 4: Copiar dependencias para classpath ───────────────────────────────
echo.
echo [4/4] Copiando dependencias para target\dependency...
call mvn dependency:copy-dependencies -DoutputDirectory=target\dependency -q
if %ERRORLEVEL% NEQ 0 (
    echo [AVISO] Falha ao copiar dependencias. launch_iped.bat pode nao funcionar.
) else (
    echo  ✓ Dependencias prontas.
)

echo.
echo ============================================================
echo  Patch aplicado com sucesso!
echo.
echo  Para testar a integracao sem IPED real:
echo    cd supreme-iped-integration
echo    python test_integration.py
echo.
echo  Para lançar o IPED patched:
echo    supreme-iped-integration\launcher\launch_iped.bat
echo ============================================================
echo.
endlocal
pause
