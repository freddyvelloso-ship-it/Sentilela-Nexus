\# Auditoria de Prontidão para Produção — SUPREME V4 / SENTINELA / IPED



\## Status atual



O stack local foi validado com sucesso após correções de bootstrap, CI, Loki, NGINX e documentação.



\## Itens já validados



\- SUPREME API responde `/health`

\- SENTINELA responde `/health`

\- NGINX sobe nas portas 80 e 443

\- Rota raiz redireciona para `/sentinela/`

\- IPED proxy sobe na porta 8081

\- Redis saudável

\- SUPREME DB saudável

\- SENTINELA DB saudável

\- Workers sobem

\- Loki sobe em modo local

\- Grafana sobe

\- Prometheus sobe

\- Scripts locais geram arquivos `.env`

\- Scripts locais geram certificados self-signed

\- Documentação de teste local criada



\## Pendências antes de produção real



\### 1. Secrets e variáveis de ambiente



\- Revisar `.env.production.example`

\- Revisar `supreme-backend/.env.production.example`

\- Revisar `sentinela/.env.production.example`

\- Garantir que não existam secrets reais versionados

\- Garantir que `.env`, `.env.production` e `certs/\*.pem` estejam protegidos no `.gitignore`



\### 2. TLS e certificados



\- Certificados self-signed são apenas para teste local

\- Produção deve usar certificado institucional ou Let’s Encrypt

\- Chave privada nunca deve ser commitada



\### 3. Observabilidade



\- Prometheus ainda pode receber 403 em `/metrics`

\- Definir se `/metrics` será:

&#x20; - liberado apenas na rede interna Docker

&#x20; - protegido por autenticação

&#x20; - exposto por rota separada



\### 4. NGINX



\- Rota `/` já redireciona para `/sentinela/`

\- Revisar headers de segurança

\- Revisar limite de upload

\- Revisar rate limit em rotas sensíveis



\### 5. Banco de dados



\- Confirmar migrations

\- Confirmar política de backup

\- Confirmar retenção de dados

\- Confirmar separação entre ambiente local, homologação e produção



\### 6. IPED



\- Validar fluxo real:

&#x20; - IPED gera `audit.ndjson`

&#x20; - watcher lê arquivo

&#x20; - proxy/API recebem eventos

&#x20; - pipeline processa eventos

&#x20; - SENTINELA exibe dados



\### 7. Segurança operacional



\- Não registrar conteúdo sensível

\- Não capturar mídia

\- Não armazenar material pericial

\- Registrar apenas metadados necessários

\- Revisar logs para evitar vazamento de identificadores sensíveis



\## Critério de aprovação para produção



O sistema só deve ser considerado pronto para produção após:



\- CI verde

\- Stack de homologação validado

\- Secrets reais provisionados fora do Git

\- Certificado TLS válido configurado

\- `/metrics` resolvido

\- fluxo IPED real testado

\- backup validado

\- documentação de deploy atualizada

\- `scripts/production_readiness_check.ps1` passando sem falhas no servidor alvo



\## Gate automatizado adicionado



Foi adicionado um gate operacional em `scripts/production_readiness_check.ps1` para validar, antes do go-live, a presenca e consistencia de:



\- arquivos reais de ambiente fora do Git

\- secrets fortes sem placeholders

\- certificados TLS reais fora do Git

\- token local do Prometheus alinhado a `API_SECRET_KEY`

\- chave compartilhada SUPREME/SENTINELA

\- `BOOTSTRAP_TOKEN` removido apos bootstrap

\- ausencia de arquivos sensiveis versionados

