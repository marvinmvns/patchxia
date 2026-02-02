# Manual Completo - Sistema de Patch de Traducao PT-BR

## Indice

1. [Visao Geral](#visao-geral)
2. [Instalacao](#instalacao)
3. [Uso Basico](#uso-basico)
4. [Traducao Automatica](#traducao-automatica)
5. [Gerenciamento do Banco](#gerenciamento-do-banco)
6. [Fluxo de Trabalho](#fluxo-de-trabalho)
7. [Estrutura de Arquivos](#estrutura-de-arquivos)
8. [Referencia de Comandos](#referencia-de-comandos)
9. [Solucao de Problemas](#solucao-de-problemas)

---

## Visao Geral

Este sistema de patch traduz automaticamente o projeto **xiaozhi-esp32-server** de Chines/Ingles para Portugues do Brasil, sem modificar permanentemente o codigo fonte original.

### Caracteristicas

- **Nao invasivo**: O codigo original permanece intacto no repositorio
- **Incremental**: Traduz apenas strings novas a cada execucao
- **Automatico**: Usa APIs gratuitas (MyMemory, Google Translate)
- **Versionavel**: Banco de traducoes pode ser versionado no Git
- **Seguro**: Cria backup antes de modificar e valida sintaxe apos

### Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    FLUXO DE TRADUCAO                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │ Codigo       │     │ Extrator de  │     │ Banco de    │ │
│  │ Original     │────▶│ Strings      │────▶│ Traducoes   │ │
│  │ (Chines)     │     │ (translator) │     │ (JSON)      │ │
│  └──────────────┘     └──────────────┘     └─────────────┘ │
│                              │                     │        │
│                              ▼                     ▼        │
│                       ┌──────────────┐     ┌─────────────┐ │
│                       │ API Traducao │     │ Codigo      │ │
│                       │ (MyMemory/   │────▶│ Traduzido   │ │
│                       │  Google)     │     │ (PT-BR)     │ │
│                       └──────────────┘     └─────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Instalacao

### Pre-requisitos

- Python 3.6 ou superior
- Git
- jq (opcional, para manipulacao JSON no bash)
- Conexao com internet (para traducao automatica)

### Instalacao no Ubuntu/Debian

```bash
# Instalar dependencias
sudo apt-get update
sudo apt-get install python3 python3-pip jq git

# Clonar o repositorio de patch
git clone https://github.com/marvinmvns/patchxia.git
cd patchxia

# Dar permissao de execucao
chmod +x apply-patch.sh
chmod +x tests/test_translation.sh
```

### Instalacao no macOS

```bash
# Instalar dependencias via Homebrew
brew install python3 jq git

# Clonar e configurar
git clone https://github.com/marvinmvns/patchxia.git
cd patchxia
chmod +x apply-patch.sh
```

### Instalacao no Windows (WSL)

```bash
# No WSL (Ubuntu)
sudo apt-get install python3 jq git
git clone https://github.com/marvinmvns/patchxia.git
cd patchxia
chmod +x apply-patch.sh
```

---

## Uso Basico

### 1. Baixar o Projeto Original

```bash
# Clonar o projeto xiaozhi-esp32-server
git clone https://github.com/xinnan-tech/xiaozhi-esp32-server.git

# Verificar estrutura
ls xiaozhi-esp32-server/
```

### 2. Simular Traducao (Dry-Run)

Antes de aplicar, sempre simule para ver o que sera traduzido:

```bash
./apply-patch.sh ./xiaozhi-esp32-server --dry-run
```

Saida esperada:
```
╔═══════════════════════════════════════════════════════════════════╗
║     XIAOZHI ESP32 SERVER - Patch de Tradução PT-BR v1.0.0        ║
╚═══════════════════════════════════════════════════════════════════╝

[INFO] Verificando dependências...
[INFO] Verificando projeto...
[INFO] Projeto verificado com sucesso

======================================================================
SISTEMA DE TRADUÇÃO PT-BR v2.0
======================================================================
Projeto: ./xiaozhi-esp32-server
Dry Run: Sim
Traduções no banco: 136
======================================================================

Processando: main/server.py
  -> 15 traduções encontradas (dry-run)
...
```

### 3. Aplicar Traducao

```bash
# Aplicar traducao (cria backup automatico)
./apply-patch.sh ./xiaozhi-esp32-server
```

### 4. Verificar Resultado

```bash
# Ver arquivos modificados
git -C ./xiaozhi-esp32-server status

# Verificar conteudo traduzido
head -50 ./xiaozhi-esp32-server/main/server.py
```

### 5. Restaurar Backup (se necessario)

```bash
./apply-patch.sh ./xiaozhi-esp32-server --rollback
```

---

## Traducao Automatica

O sistema usa APIs gratuitas para traduzir automaticamente strings nao encontradas no banco.

### Traduzir Strings Pendentes

Apos aplicar o patch, strings novas ficam em `translations/pending.json`:

```bash
# Ver estatisticas
python3 scripts/translate_pending.py --stats

# Traduzir todas as pendentes automaticamente
python3 scripts/translate_pending.py

# Traduzir apenas 10 (para testar)
python3 scripts/translate_pending.py --limit 10

# Modo interativo (revisar cada traducao)
python3 scripts/translate_pending.py --review
```

### APIs de Traducao Suportadas

| API | Limite | Qualidade | Velocidade |
|-----|--------|-----------|------------|
| MyMemory | 1000 palavras/dia | Alta | Rapida |
| Google Translate | Ilimitado* | Media | Rapida |

*Google pode bloquear apos muitas requisicoes

### Exportar para Revisao Manual

Para traducoes mais precisas, exporte para CSV:

```bash
# Exportar pendentes para CSV
python3 scripts/translate_pending.py --export

# Editar o arquivo CSV
# translations/pending_review.csv

# Importar traducoes revisadas
python3 scripts/translate_pending.py --import-csv
```

---

## Gerenciamento do Banco

### Estrutura do Banco de Traducoes

O arquivo `translations/translations.json` contem todas as traducoes:

```json
{
  "version": "2.0.0",
  "total_translations": 136,
  "translations": {
    "hash_md5": {
      "original": "文本原文",
      "translated": "Texto traduzido",
      "source_lang": "zh",
      "translator": "manual|mymemory|google",
      "verified": true|false,
      "date_added": "2026-02-02T00:00:00"
    }
  }
}
```

### Adicionar Traducao Manual

1. Calcule o hash MD5 da string original (primeiros 12 caracteres):

```bash
echo -n "文本原文" | md5sum | cut -c1-12
```

2. Adicione ao arquivo `translations/translations.json`:

```json
{
  "translations": {
    "seu_hash_aqui": {
      "original": "文本原文",
      "translated": "Sua traducao aqui",
      "source_lang": "zh",
      "translator": "manual",
      "verified": true,
      "date_added": "2026-02-02T00:00:00"
    }
  }
}
```

### Verificar Traducao Especifica

```bash
# Buscar traducao por texto
grep -A5 '"original": "开始"' translations/translations.json
```

### Estatisticas do Banco

```bash
python3 scripts/translate_pending.py --stats
```

---

## Fluxo de Trabalho

### Fluxo Recomendado (Primeira Vez)

```
1. Clonar patch         → git clone .../patchxia.git
2. Clonar projeto       → git clone .../xiaozhi-esp32-server.git
3. Simular traducao     → ./apply-patch.sh ./projeto --dry-run
4. Aplicar traducao     → ./apply-patch.sh ./projeto
5. Traduzir pendentes   → python3 scripts/translate_pending.py
6. Revisar traducoes    → Editar translations/translations.json
7. Reaplicar patch      → ./apply-patch.sh ./projeto
```

### Fluxo para Atualizacoes

Quando o projeto original for atualizado:

```bash
# 1. Atualizar projeto original
cd xiaozhi-esp32-server
git pull origin main
cd ..

# 2. Aplicar patch novamente (modo incremental)
./apply-patch.sh ./xiaozhi-esp32-server

# 3. Traduzir novas strings
python3 scripts/translate_pending.py

# 4. Versionar banco atualizado
cd patchxia
git add translations/
git commit -m "Atualizar traducoes"
git push
```

### Fluxo para Contribuir

```bash
# 1. Fork o repositorio patchxia
# 2. Clone seu fork
git clone https://github.com/SEU_USUARIO/patchxia.git

# 3. Adicione traducoes
# Edite translations/translations.json

# 4. Teste
./tests/test_translation.sh --full

# 5. Commit e PR
git add translations/
git commit -m "Adicionar traducoes para XYZ"
git push
# Abra Pull Request no GitHub
```

---

## Estrutura de Arquivos

```
patchxia/
├── apply-patch.sh              # Script principal
├── README.md                   # Documentacao basica
├── MANUAL.md                   # Este manual
│
├── scripts/
│   ├── translator.py           # Motor de traducao
│   └── translate_pending.py    # Utilitario para pendentes
│
├── translations/
│   ├── translations.json       # Banco de traducoes (136+)
│   ├── pending.json            # Strings pendentes
│   └── pending_review.csv      # Export para revisao manual
│
├── backups/                    # Backups automaticos
│   └── backup_YYYYMMDD_HHMMSS/
│
├── tests/
│   ├── test_translation.sh     # Script de teste
│   └── test_project/           # Projeto de teste (gerado)
│
├── config/                     # Configuracoes (futuro)
└── logs/                       # Logs de execucao
    └── patch-YYYYMMDD.log
```

---

## Referencia de Comandos

### apply-patch.sh

```bash
./apply-patch.sh <caminho-projeto> [opcoes]

Opcoes:
  --incremental    Traduz apenas strings novas (padrao)
  --full           Retraduz todas as strings
  --dry-run        Simula sem modificar arquivos
  --rollback       Restaura backup anterior
  --use-llm        Usa API para strings novas
  --validate       Apenas valida sintaxe
  --help           Mostra ajuda
```

### translate_pending.py

```bash
python3 scripts/translate_pending.py [opcoes]

Opcoes:
  --limit N        Traduzir apenas N strings
  --review         Modo revisao interativo
  --export         Exportar para CSV
  --import-csv     Importar de CSV
  --stats          Mostrar estatisticas
```

### test_translation.sh

```bash
./tests/test_translation.sh [opcoes]

Opcoes:
  --dry-run        Teste simulado
  --real           Aplicar traducao real
  --validate       Apenas validar
  --full           Teste completo
  --clean          Limpar ambiente
```

---

## Solucao de Problemas

### Erro: "Dependencias faltando"

```bash
# Instalar dependencias
sudo apt-get install python3 jq
```

### Erro: "Projeto nao encontrado"

```bash
# Verificar caminho
ls ./xiaozhi-esp32-server/
# Deve mostrar: main/, docs/, Dockerfile, etc.
```

### Erro: "Sintaxe Python invalida"

O patch pode ter quebrado algum arquivo:

```bash
# Verificar sintaxe
python3 -m py_compile ./xiaozhi-esp32-server/main/server.py

# Restaurar backup
./apply-patch.sh ./xiaozhi-esp32-server --rollback
```

### Traducao incorreta

1. Encontre a traducao no banco:
```bash
grep -B2 -A8 '"Traducao errada"' translations/translations.json
```

2. Edite o arquivo e corrija a traducao
3. Marque como `"verified": true`
4. Reaplique o patch

### API nao responde

```bash
# Verificar conexao
curl -s "https://api.mymemory.translated.net/get?q=test&langpair=en|pt"

# Se falhar, usar modo offline (apenas banco local)
./apply-patch.sh ./projeto  # Sem --use-llm
```

### Muitas strings pendentes

```bash
# Traduzir em lotes
python3 scripts/translate_pending.py --limit 50
# Aguardar 1 minuto (rate limit)
python3 scripts/translate_pending.py --limit 50
```

---

## Contato e Contribuicao

- **Repositorio**: https://github.com/marvinmvns/patchxia
- **Projeto Original**: https://github.com/xinnan-tech/xiaozhi-esp32-server
- **Issues**: Abra uma issue no GitHub

### Como Contribuir

1. Adicione traducoes ao banco
2. Melhore traducoes existentes (marque `verified: true`)
3. Reporte bugs ou problemas
4. Sugira melhorias

---

*Manual versao 1.0 - Fevereiro 2026*
