# Teste Local do Stack SUPREME/SENTINELA/IPED

Este guia descreve o procedimento validado para subir o stack local do projeto Sentilela Nexus usando Docker Compose.

## Objetivo

Executar localmente os serviços principais do sistema:

- SUPREME API
- SENTINELA
- SUPREME DB
- SENTINELA DB
- Redis
- Worker
- IPED watcher
- IPED proxy
- NGINX
- Prometheus
- Grafana
- Loki

## Pré-requisitos

- Windows 10/11
- PowerShell
- Docker Desktop ativo
- Git instalado
- Repositório clonado localmente

## Branch validada

O procedimento foi validado após merge das correções de bootstrap local na branch `main`.

## 1. Entrar na pasta do projeto

```powershell
cd C:\Users\nunas\Downloads\Sentilela-Nexus
