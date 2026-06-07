@echo off
echo ============================================================
echo  SUPREME V4 — Inicializando stack local
echo ============================================================

cd /d "%~dp0"

echo.
echo [1/3] Construindo imagens e subindo containers...
docker compose up --build -d

if %ERRORLEVEL% NEQ 0 (
    echo ERRO: Falha ao subir containers. Verifique o Docker Desktop.
    pause
    exit /b 1
)

echo.
echo [2/3] Aguardando banco de dados ficar pronto...
timeout /t 10 /nobreak >nul

echo.
echo [3/3] Verificando saude da API...
timeout /t 5 /nobreak >nul
curl -s http://localhost:8000/v1/health

echo.
echo ============================================================
echo  Stack rodando:
echo    API:          http://localhost:8000
echo    Docs:         http://localhost:8000/docs
echo    RQ Dashboard: http://localhost:9181
echo    PostgreSQL:   localhost:5432  (supreme/supreme_secret)
echo    Redis:        localhost:6379
echo ============================================================
echo.
echo Para parar: docker compose down
echo Para ver logs: docker compose logs -f
pause
