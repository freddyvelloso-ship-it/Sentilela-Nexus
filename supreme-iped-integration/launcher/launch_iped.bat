@echo off
REM =============================================================================
REM launch_iped.bat — Lança o IPED patched com integração SUPREME V4
REM
REM Uso:
REM   launch_iped.bat [argumentos do IPED]
REM
REM Variáveis configuráveis (defina antes de rodar ou edite aqui):
REM   IPED_HOME         Pasta raiz do IPED (onde estão todos os JARs)
REM   SUPREME_HOME      Pasta raiz do SUPREME V4
REM   SUPREME_USER_ID   ID funcional do perito (sem nome/CPF)
REM   SUPREME_SALT      Salt offline (definir via variável de ambiente segura)
REM   SUPREME_API_URL   URL do backend SUPREME
REM =============================================================================

setlocal enabledelayedexpansion

REM ── Detectar localização do IPED ─────────────────────────────────────────────
REM !!! Ajustar para o caminho real do IPED em producao
if "%IPED_HOME%"=="" set IPED_HOME=C:\IPED

REM !!! Ajustar para o JAR patched correto (vX.Y.Z da versao em producao)
if "%IPED_PATCHED_JAR%"=="" set IPED_PATCHED_JAR=%IPED_HOME%\iped-app.jar

REM ── Localização do SUPREME ────────────────────────────────────────────────────
REM Detecta automaticamente a partir do local deste .bat
if "%SUPREME_HOME%"=="" set SUPREME_HOME=%~dp0..

set WATCHER_SCRIPT=%SUPREME_HOME%\supreme-watcher\watcher.py

REM ── Configurações SUPREME ─────────────────────────────────────────────────────
if "%SUPREME_API_URL%"==""    set SUPREME_API_URL=http://localhost:8000
if "%SUPREME_AUDIT_LOG%"==""  set SUPREME_AUDIT_LOG=%USERPROFILE%\supreme_audit.ndjson
if "%WATCHER_POLL_SECS%"==""  set WATCHER_POLL_SECS=15

if "%SUPREME_SALT%"=="" (
    echo.
    echo [AVISO] SUPREME_SALT nao definido. Pseudonimizacao insegura.
    echo         Em producao: defina SUPREME_SALT como variavel de ambiente
    echo         com valor gerado offline e armazenado em midia segura.
    echo.
    set SUPREME_SALT=dev-salt-local-troque-em-producao
)

REM ── Coleta do ID funcional ────────────────────────────────────────────────────
echo ============================================================
echo   SUPREME V4 - Telemetria de Exposicao Ocupacional
echo ============================================================
echo.
echo  AVISO: Esta sessao sera monitorada para fins de pesquisa.
echo  Dados sao pseudonimizados conforme protocolo CEP aprovado.
echo.

:ask_user
set /p SUPREME_USER_ID=ID funcional (ex: perito_021):
if "%SUPREME_USER_ID%"=="" (
    echo ID nao pode ser vazio.
    goto ask_user
)
echo.
echo  Sessao: %SUPREME_USER_ID% [sera pseudonimizado antes de armazenar]
echo.

REM ── Iniciar supreme-watcher em background ─────────────────────────────────────
echo [1/2] Iniciando supreme-watcher...
set WATCHER_LOG=%USERPROFILE%\supreme_watcher.log
start "supreme-watcher" /MIN python "%WATCHER_SCRIPT%"
timeout /t 2 /nobreak >nul
echo       Watcher ativo. Log: %WATCHER_LOG%
echo.

REM ── Lançar IPED ───────────────────────────────────────────────────────────────
echo [2/2] Iniciando IPED (patched)...
echo.

REM Verifica se o JAR patched existe
if not exist "%IPED_PATCHED_JAR%" (
    echo [ERRO] JAR patched nao encontrado em: %IPED_PATCHED_JAR%
    echo        Execute primeiro: cd C:\iped-source\iped-app ^&^& mvn clean package -DskipTests
    pause
    exit /b 1
)

REM Montar classpath: JAR patched + todos os JARs de dependencia do IPED
REM Em producao, o JAR patched substitui o original na pasta do IPED
set IPED_LIB=%IPED_HOME%\lib
set IPED_CP=%IPED_PATCHED_JAR%

REM Adicionar dependencias se pasta existir
if exist "%IPED_LIB%" (
    for %%f in ("%IPED_LIB%\*.jar") do (
        set IPED_CP=!IPED_CP!;%%f
    )
)

java ^
    -Xmx4g ^
    -cp "!IPED_CP!" ^
    iped.app.bootstrap.BootstrapUI ^
    %*

REM ── Encerramento ──────────────────────────────────────────────────────────────
echo.
echo  IPED encerrado. Aguardando envio dos ultimos eventos...
timeout /t %WATCHER_POLL_SECS% /nobreak >nul

echo  Encerrando watcher...
taskkill /FI "WINDOWTITLE eq supreme-watcher" /F >nul 2>&1

echo.
echo  Sessao SUPREME encerrada para: %SUPREME_USER_ID