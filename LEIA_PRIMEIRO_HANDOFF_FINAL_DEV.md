# LEIA PRIMEIRO — SUPREME V5 handoff final

O arquivo principal para o desenvolvedor é:

```text
docs/HANDOFF_FINAL_PRODUCAO_DEV.md
```

Ele contém todas as melhorias aplicadas, correções feitas durante instalação local, pendências de produção e critérios de aceite para testar o sistema real com IPED -> SUPREME -> SENTINELA.

Correções locais incorporadas nesta versão:

- SENTINELA front usa `const API = '/sentinela';`.
- NGINX está conectado à rede backend.
- Prometheus não usa mais `--config.expand-env=true`.
- Adicionado `docker-compose.local.yml` validado para Windows/Docker Desktop.
- Adicionado `scripts/windows_local_setup_validado.ps1` para gerar segredos e arquivos `.env` sem depender de Python no Windows.

Antes de produção real, rotacione todos os segredos e corrija o Loki.
