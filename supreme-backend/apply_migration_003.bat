@echo off
echo Aplicando migration 003 — modulo psicomtrico...
docker exec -i supreme-db psql -U supreme -d supreme < supabase\migrations\003_psychometric_module.sql
if %ERRORLEVEL% EQU 0 (
    echo OK — migration 003 aplicada com sucesso.
) else (
    echo ERRO ao aplicar migration. Verifique se o container supreme-db esta rodando.
)
pause
