# Patch de Traducao PT-BR para xiaozhi-esp32-server

Sistema de patch para traducao automatica de Chines/Ingles para Portugues do Brasil do projeto [xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server).

## Caracteristicas

- **Traducao incremental**: Traduz apenas strings novas, preservando traducoes anteriores
- **Nao quebra o codigo**: Validacao automatica de sintaxe apos aplicar o patch
- **Backup automatico**: Cria backup antes de modificar qualquer arquivo
- **Rollback facil**: Restaura o estado anterior com um comando
- **Multiplos backends**: Suporte a Google Translate, MyMemory API, e traducao manual
- **Banco de traducoes**: Armazena traducoes para reutilizacao e versionamento

## Instalacao Rapida

```bash
# 1. Clone este repositorio de patch
git clone https://github.com/marvinmvns/patchxia.git
cd patchxia

# 2. Clone o projeto original (em outro diretorio)
git clone https://github.com/xinnan-tech/xiaozhi-esp32-server.git ../xiaozhi-esp32-server

# 3. Aplique o patch
chmod +x *.sh
./apply-patch.sh ../xiaozhi-esp32-server

# ou — atualiza tudo de uma vez (fonte + banco + web + pendentes)
./update-all.sh

# ou — pipeline completo (inicia Docker + traduz + testa + finaliza)
./full-pipeline.sh
```

## Pipeline Completo (full-pipeline.sh)

Script que executa **todo o ciclo de vida** do patch: inicia containers Docker, traduz, testa e finaliza. Ideal para automação e CI/CD.

```bash
./full-pipeline.sh                        # fluxo interativo completo
./full-pipeline.sh --auto                 # modo automático (sem confirmações)
./full-pipeline.sh --auto --stop-after    # CI/CD: automático e para containers ao final
./full-pipeline.sh --dry-run              # preview sem alterar nada
./full-pipeline.sh --no-api               # sem chamadas externas de API
./full-pipeline.sh --keep-containers      # não pergunta para parar ao final
./full-pipeline.sh --skip-clone           # não clona/atualiza projeto
./full-pipeline.sh --project /outro/path  # projeto em outro lugar
```

### Fases do Pipeline

| Fase | Etapas | Descrição |
|------|--------|-----------|
| **1. Preparação** | 1-4 | Verifica dependências, clone/update projeto, inicia Docker, aguarda containers |
| **2. Tradução** | 5-13 | Executa `update-all.sh` (limpeza → backup → patch fonte/DB/web → pendentes) |
| **3. Teste & Fim** | 14-16 | Testes de sanidade, relatório final, para containers (opcional) |

### Detalhamento das Etapas

| # | Etapa | O que faz |
|---|-------|-----------|
| 1 | Verificar dependências | Confirma python3, jq, docker, git |
| 2 | Clone/atualização | Clona repositório ou faz git pull |
| 3 | Iniciar containers | `docker compose up -d` no docker-compose_all.yml |
| 4 | Aguardar health | Espera DB, Redis, Web ficarem saudáveis |
| 5-13 | Tradução | Executa update-all.sh (veja abaixo) |
| 14 | Testes de sanidade | Verifica sintaxe Python, JSON, conexão MySQL |
| 15 | Relatório final | Exibe estatísticas e tempo de execução |
| 16 | Gerenciar containers | Pergunta se deve parar ou manter |

---

## Atualização Completa (update-all.sh)

Script que executa o fluxo de tradução na ordem certa, pulando graciosamente o que não estiver disponível (ex: containers parados).

```bash
./update-all.sh                          # fluxo completo
./update-all.sh --dry-run                # preview sem alterar nada
./update-all.sh --no-api                 # sem chamadas externas de API
./update-all.sh --skip-docker            # só arquivos fonte + markdown
./update-all.sh --project /outro/caminho # projeto em outro lugar
```

### Etapas que são executadas

| # | Etapa | O que faz |
|---|-------|-----------|
| 1 | Verificações | Confirma python3, jq, projeto e containers |
| 2 | Limpeza | Remove lixo e código de `pending.json` e `translations.json` |
| 3 | Análise | Cobertura atual via `extract_docker.py` (DB + web) |
| 4 | Backup | Copia todos os arquivos com chinês antes de modificar |
| 5 | Patch de fonte | Aplica traduções em `.py`, `.yaml`, `.json`, `.sh` … |
| 6 | Patch de Markdown | Aplica traduções nos arquivos `.md` |
| 7 | Patch do banco | UPDATEs no MySQL via `patch_database.py` |
| 8 | Patch dos assets web | Substitui strings nos bundles JS compilados |
| 9 | Pendentes via API | Traduz strings novas via MyMemory / Google |
| 10 | Validação | Reverte `.py` com erro de sintaxe via `revert_broken.py` |
| 11 | Resumo | Exibe totais do banco e caminho do log |

## Uso

### Aplicar traducao incremental (padrao)

```bash
./apply-patch.sh /caminho/para/xiaozhi-esp32-server
```

### Simular traducao (dry-run)

```bash
./apply-patch.sh /caminho/para/xiaozhi-esp32-server --dry-run
```

### Usar traducao automatica para strings novas

```bash
./apply-patch.sh /caminho/para/xiaozhi-esp32-server --use-llm
```

### Restaurar backup

```bash
./apply-patch.sh /caminho/para/xiaozhi-esp32-server --rollback
```

### Apenas validar codigo

```bash
./apply-patch.sh /caminho/para/xiaozhi-esp32-server --validate
```

## Opcoes Disponiveis

| Opcao | Descricao |
|-------|-----------|
| `--incremental` | Traduz apenas strings novas (padrao) |
| `--full` | Retraduz todas as strings |
| `--dry-run` | Mostra o que seria traduzido sem aplicar |
| `--rollback` | Restaura o backup mais recente |
| `--use-llm` | Usa servicos de traducao para strings novas |
| `--validate` | Apenas valida o codigo apos patch |
| `--docker` | Aplica patch em containers Docker (fonte + DB + web) |
| `--extract` | Apenas analisa o que precisa de traducao (sem escrever) |
| `--help` | Mostra ajuda |

## Estrutura do Projeto

```
patchxia/
├── full-pipeline.sh               # Pipeline completo (Docker + traduz + testa + finaliza)
├── update-all.sh                  # Atualização completa (11 etapas em um comando)
├── apply-patch.sh                 # CLI principal (backup -> traduz -> valida)
├── patch-db.sh                    # Patch isolado do banco MySQL (preview -> aplica -> pendentes)
├── clean_translations.py          # Auditoria de qualidade em translations.json
├── revert_broken.py               # Reverte arquivos com erro de sintaxe (git checkout)
├── scripts/
│   ├── translator.py              # Motor de traducao (extração, substituição, APIs)
│   ├── translate_pending.py       # Traduz pending.json via APIs (4 workers)
│   ├── translate_pending_group.py # Traduz pending.json (single-thread)
│   ├── translate_md.py            # Traducao de arquivos Markdown
│   ├── clean_pending_list.py      # Remove padroes de codigo de pending.json
│   ├── extract_docker.py          # Escana containers para strings nao traduzidas
│   ├── patch_database.py          # Aplica patch nas tabelas MySQL via docker exec
│   └── patch_web_assets.py        # Aplica patch nos bundles JS do container web
├── translations/
│   ├── translations.json          # Banco de traducoes verificadas
│   └── pending.json               # Strings pendentes de traducao
├── backups/                       # Backups automaticos (timestamp)
├── tests/
│   └── test_translation.sh        # Script de teste (projeto isolado)
├── config/                        # Configuracoes
└── logs/                          # Logs de execucao
```

## Fluxo de Trabalho Recomendado

### Primeira vez

1. Clone o projeto original
2. Aplique o patch com `--dry-run` para ver o que sera traduzido
3. Aplique o patch com `--use-llm` para traduzir automaticamente
4. Revise as traducoes em `translations/pending.json`
5. Mova traducoes aprovadas para `translations/translations.json`

### Atualizacoes

1. Faca pull do projeto original
2. Rode `./update-all.sh` — executa limpeza, backup, patch de fonte + banco + web e traduz pendentes automaticamente
3. Novas strings que não tiverem tradução ficam em `pending.json`
4. Revise e aprove as novas traducoes (ou exporte para CSV com `--export`)

## Gerenciar Strings Pendentes

Strings não encontradas no banco geram entradas em `pending.json`. Para processá-las:

```bash
# Traduz pendentes via APIs (MyMemory / Google)
python3 scripts/translate_pending.py

# Exporta pendentes para CSV (revisao manual)
python3 scripts/translate_pending.py --export-csv

# Importa CSV revisado de volta ao pending.json
python3 scripts/translate_pending.py --import-csv pending_translated.csv
```

## Alterar o Banco de Dados (MySQL)

Requer o container `xiaozhi-esp32-server-db` rodando. Os comandos abaixo conectam via `docker exec` e executam UPDATEs nas tabelas que contêm texto em chinês.

### Comando tudo-em-um

O script `patch-db.sh` faz todo o fluxo numa chamada: verifica o container, mostra preview, aplica e processa pendentes.

```bash
./patch-db.sh            # fluxo completo (preview → aplica → pendentes via API)
./patch-db.sh --dry-run  # apenas preview, sem alterar nada
./patch-db.sh --no-api   # aplica sem chamadas externas de API
```

### Comandos individuais (patch_database.py)

Se preferir controlar cada etapa separadamente:

```bash
# Preview — mostra o que seria alterado sem tocar no banco
python3 scripts/patch_database.py --dry-run

# Aplica as traduções (usa banco local + APIs MyMemory/Google para strings novas)
python3 scripts/patch_database.py

# Aplica usando apenas o banco de traduções local (sem chamadas de API)
python3 scripts/patch_database.py --no-api
```

### Tabelas e campos alterados

| Tabela | Campos traduzidos | Observação |
|--------|-------------------|------------|
| `sys_params` | `param_value`, `remark` | `exit_commands` e `wakeup_words` são arrays separados por `;` — cada item é traduzido individualmente. Parâmetros de chave/token/URL e os params `xiaozhi` e `system-web.menu` são ignorados. |
| `sys_dict_data` | `dict_label`, `remark` | Labels e remarks de dispositivos/firmware |
| `ai_model_provider` | `name`, `fields[].label` | `fields` é um JSON array — apenas os `label` internos são traduzidos |
| `ai_model_config` | `model_name`, `remark` | `remark` pode conter instruções de setup longas |
| `ai_agent_template` | `agent_name` | `system_prompt` é mantido em chinês intencionalmente (prompt do LLM) |

### Fluxo recomendado

1. Rode `--dry-run` para revisar o que será alterado.
2. Rode sem flags para aplicar (traduz via API automaticamente).
3. Se preferir revisar antes de aplicar, use `--no-api` e depois rode `python3 scripts/translate_pending.py` para traduzir as strings pendentes manualmente ou via API em lote.

> **Nota:** as alterações no MySQL são duráveis — não são perdidas com restart do container.

---

## Modo Docker

Aplica patch diretamente em containers em execucao (banco MySQL + JS compilados + fonte). Requer os 4 containers do xiaozhi rodando.

```bash
# Analise: o que ainda precisa de traducao
python3 scripts/extract_docker.py
python3 scripts/extract_docker.py --save       # salva em extractions/summary.json
python3 scripts/extract_docker.py --db-only    # apenas tabelas MySQL

# Patch no MySQL (sys_params, sys_dict_data, ai_model_provider, etc.)
python3 scripts/patch_database.py              # aplica + traduz via API
python3 scripts/patch_database.py --dry-run    # preview
python3 scripts/patch_database.py --no-api     # sem chamadas de API

# Patch nos bundles JS do container web
python3 scripts/patch_web_assets.py            # aplica + traduz via API
python3 scripts/patch_web_assets.py --dry-run  # preview
python3 scripts/patch_web_assets.py --no-api   # sem chamadas de API

# Tudo em um comando via apply-patch.sh
./apply-patch.sh --docker                      # fonte + DB + web
./apply-patch.sh --docker --use-llm            # com fallback LLM para fonte
./apply-patch.sh --docker --dry-run            # preview geral
./apply-patch.sh --extract                     # apenas analise
```

**Nota:** patches nos bundles JS são efêmeros — se o container web for recriado (ex: `docker pull` + restart) é necessário reexecutar `patch_web_assets.py`. Updates no MySQL são duráveis.

## Manutenção

```bash
# Remove padroes de codigo/lixo de pending.json
python3 scripts/clean_pending_list.py

# Auditoria de qualidade em translations.json
python3 clean_translations.py

# Reverte arquivos do xiaozhi que falharam na validacao de sintaxe
python3 revert_broken.py
```

## Adicionar Traducoes Manuais

Edite o arquivo `translations/translations.json`:

```json
{
  "translations": {
    "hash_unico": {
      "original": "文本原文",
      "translated": "Texto traduzido",
      "source_lang": "zh",
      "translator": "manual",
      "verified": true
    }
  }
}
```

## Executar Testes

```bash
# Teste basico (dry-run)
./tests/test_translation.sh

# Teste completo
./tests/test_translation.sh --full

# Limpar ambiente de teste
./tests/test_translation.sh --clean
```

## Dependencias

- Python 3.6+
- jq (para manipulacao JSON no bash)
- Conexao com internet (para traducao automatica)

### Instalar dependencias (Ubuntu/Debian)

```bash
sudo apt-get install python3 jq
```

## Servicos de Traducao Suportados

1. **MyMemory API** (gratuito, 1000 palavras/dia)
2. **Google Translate** (gratuito via API web)
3. **LibreTranslate** (auto-hospedavel)
4. **Traducao Manual** (via banco de traducoes)

## Contribuir

1. Faca fork deste repositorio
2. Adicione traducoes em `translations/translations.json`
3. Teste com `./tests/test_translation.sh --full`
4. Envie um Pull Request

## Licenca

MIT License - Sinta-se livre para usar e modificar.

## Links

- Projeto Original: https://github.com/xinnan-tech/xiaozhi-esp32-server
- Reportar Problemas: Abra uma issue neste repositorio
