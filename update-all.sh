#!/bin/bash
# ==============================================================
# update-all.sh — Atualização completa do patch PT-BR
# ==============================================================
# Executa o fluxo inteiro passo a passo:
#
#   1  Verificações          deps, containers, caminho do projeto
#   2  Limpeza               remove lixo/código de pending + translations
#   3  Análise               cobertura atual (DB + web + arquivos)
#   4  Backup                copia arquivos com chinês antes de tocar
#   5  Patch de fonte        translator.py → .py .yaml .json .sh …
#   6  Patch de Markdown     translate_md.py → .md
#   7  Patch do banco        patch_database.py → MySQL via Docker
#   8  Patch dos assets web  patch_web_assets.py → JS via Docker
#   9  Pendentes via API     translate_pending.py → MyMemory / Google
#  10  Validação             revert_broken.py → rollback de .py quebrados
#  11  Resumo                totais do banco de traduções
#
# Uso:
#   ./update-all.sh                          # fluxo completo
#   ./update-all.sh --dry-run                # preview sem alterar nada
#   ./update-all.sh --no-api                 # sem chamadas externas
#   ./update-all.sh --skip-docker            # pula etapas que precisam de Docker
#   ./update-all.sh --project /outro/caminho # projeto em outro lugar
# ==============================================================

# ─── Caminhos base ────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Padrão: pasta irmã da translation_patch
DEFAULT_PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)/xiaozhi-esp32-server"

TRANSLATIONS="$SCRIPT_DIR/translations/translations.json"
PENDING="$SCRIPT_DIR/translations/pending.json"
BACKUPS="$SCRIPT_DIR/backups"
LOGS="$SCRIPT_DIR/logs"
LOG_FILE="$LOGS/update-all-$(date '+%Y%m%d_%H%M%S').log"

# ─── Cores ────────────────────────────────────────────────────
R='\033[0;31m'  # vermelho
G='\033[0;32m'  # verde
Y='\033[1;33m'  # amarelo
B='\033[0;34m'  # azul
C='\033[0;36m'  # cyan
N='\033[0m'     # reset

# ─── Flags ────────────────────────────────────────────────────
DRY_RUN=false
NO_API=false
SKIP_DOCKER=false
PROJECT_DIR="$DEFAULT_PROJECT"

# ─── Parse ────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)     DRY_RUN=true;     shift ;;
        --no-api)      NO_API=true;      shift ;;
        --skip-docker) SKIP_DOCKER=true; shift ;;
        --project)     PROJECT_DIR="$2"; shift 2 ;;
        --help|-h)
            echo "Uso: $0 [--dry-run] [--no-api] [--skip-docker] [--project DIR]"
            echo ""
            echo "  --dry-run        Preview de tudo sem alterar nada"
            echo "  --no-api         Sem chamadas externas de API"
            echo "  --skip-docker    Pula etapas que precisam de containers"
            echo "  --project DIR    Caminho do projeto xiaozhi-esp32-server"
            exit 0
            ;;
        *)
            echo -e "${R}Opção desconhecida: $1${N}"
            echo "Use --help para ver as opções."
            exit 1
            ;;
    esac
done

# ─── Logger ───────────────────────────────────────────────────
mkdir -p "$LOGS"
log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG_FILE"; }

# ─── Helpers de exibição ──────────────────────────────────────
CURRENT_STEP=0
TOTAL_STEPS=11

step() {
    ((CURRENT_STEP++))
    echo ""
    echo -e "${B}┌─────────────────────────────────────────────────────────┐${N}"
    echo -e "${B}│  Etapa $CURRENT_STEP / $TOTAL_STEPS — $*"
    echo -e "${B}└─────────────────────────────────────────────────────────┘${N}"
    log "=== Etapa $CURRENT_STEP: $* ==="
}

ok()   { echo -e "  ${G}✓${N} $*";  log "[OK]   $*"; }
warn() { echo -e "  ${Y}!${N} $*";  log "[WARN] $*"; }
err()  { echo -e "  ${R}✗${N} $*";  log "[ERR]  $*"; }
info() { echo -e "  ${C}→${N} $*";  log "[INFO] $*"; }
skip() { echo -e "  ${Y}○${N} $*";  log "[SKIP] $*"; }

container_up() {
    docker inspect --format '{{.State.Running}}' "$1" 2>/dev/null | grep -q "true"
}

# ─── Banner ───────────────────────────────────────────────────
echo ""
echo -e "${B}╔═════════════════════════════════════════════════════════════╗${N}"
echo -e "${B}║        ATUALIZAÇÃO COMPLETA — patch PT-BR xiaozhi          ║${N}"
echo -e "${B}╚═════════════════════════════════════════════════════════════╝${N}"
echo ""
echo -e "  Modo        : $([ "$DRY_RUN" = true ] && echo -e "${Y}DRY-RUN (preview)${N}" || echo -e "${G}APLICAR${N}")"
echo -e "  API externa : $([ "$NO_API" = true ] && echo -e "${Y}desabilitada${N}" || echo "habilitada")"
echo -e "  Docker      : $([ "$SKIP_DOCKER" = true ] && echo -e "${Y}pulado${N}" || echo "incluído")"
echo -e "  Projeto     : $PROJECT_DIR"
echo -e "  Log         : $LOG_FILE"
log "Iniciou — DRY_RUN=$DRY_RUN NO_API=$NO_API SKIP_DOCKER=$SKIP_DOCKER PROJECT=$PROJECT_DIR"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. VERIFICAÇÕES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Verificações"

# python3
if command -v python3 >/dev/null 2>&1; then
    ok "python3 encontrado"
else
    err "python3 não encontrado — instale com: sudo apt install python3"
    exit 1
fi

# jq
if command -v jq >/dev/null 2>&1; then
    ok "jq encontrado"
else
    err "jq não encontrado — instale com: sudo apt install jq"
    exit 1
fi

# projeto
if [ -d "$PROJECT_DIR" ]; then
    ok "Projeto encontrado"
else
    warn "Projeto não encontrado em $PROJECT_DIR"
    warn "Etapas de fonte, markdown e validação serão puladas"
    PROJECT_DIR=""
fi

# docker + containers
DOCKER_DB=false
DOCKER_WEB=false

if [ "$SKIP_DOCKER" = true ]; then
    skip "Docker pulado por --skip-docker"
elif ! command -v docker >/dev/null 2>&1; then
    warn "docker não instalado — etapas Docker serão puladas"
    SKIP_DOCKER=true
else
    if container_up "xiaozhi-esp32-server-db"; then
        ok "Container DB rodando"
        DOCKER_DB=true
    else
        warn "Container DB não está rodando"
    fi

    if container_up "xiaozhi-esp32-server-web"; then
        ok "Container Web rodando"
        DOCKER_WEB=true
    else
        warn "Container Web não está rodando"
    fi

    if [ "$DOCKER_DB" = false ] && [ "$DOCKER_WEB" = false ]; then
        warn "Nenhum container rodando — inicie com:"
        info "docker compose -f docker-compose_all.yml up -d"
    fi
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. LIMPEZA DO BANCO DE TRADUÇÕES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Limpeza do banco de traduções"

cd "$SCRIPT_DIR"

if [ "$DRY_RUN" = true ]; then
    skip "Limpeza pulada no modo DRY-RUN"
else
    info "Removendo padrões de código de pending.json …"
    python3 scripts/clean_pending_list.py 2>&1 | while read -r line; do echo "    $line"; done
    log "clean_pending_list.py concluído"

    info "Auditoria de qualidade em translations.json …"
    python3 clean_translations.py 2>&1 | while read -r line; do echo "    $line"; done
    log "clean_translations.py concluído"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. ANÁLISE DE COBERTURA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Análise de cobertura"

cd "$SCRIPT_DIR"

if [ "$DOCKER_DB" = true ] || [ "$DOCKER_WEB" = true ]; then
    info "Escaneando containers …"
    python3 scripts/extract_docker.py --save 2>&1 | while read -r line; do echo "    $line"; done
    log "extract_docker.py concluído"
else
    skip "Containers indisponíveis — análise Docker pulada"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. BACKUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Backup automático"

if [ -z "$PROJECT_DIR" ]; then
    skip "Sem projeto — backup pulado"
elif [ "$DRY_RUN" = true ]; then
    skip "DRY-RUN — backup pulado"
else
    BACKUP_NAME="backup_$(date '+%Y%m%d_%H%M%S')"
    BACKUP_PATH="$BACKUPS/$BACKUP_NAME"
    mkdir -p "$BACKUP_PATH"

    COUNT=0
    find "$PROJECT_DIR" \
        \( -name "*.py" -o -name "*.yaml" -o -name "*.yml" \
           -o -name "*.json" -o -name "*.sh" -o -name "*.md" -o -name "*.txt" \) \
        -type f 2>/dev/null | \
    while read -r file; do
        # Verifica chinês com python (regex Unicode confiável)
        if python3 -c "
import re, sys
with open(sys.argv[1], errors='ignore') as f:
    sys.exit(0 if re.search(r'[\u4e00-\u9fff]', f.read()) else 1)
" "$file" 2>/dev/null; then
            rel="${file#$PROJECT_DIR/}"
            mkdir -p "$(dirname "$BACKUP_PATH/$rel")"
            cp "$file" "$BACKUP_PATH/$rel"
        fi
    done

    COUNT=$(find "$BACKUP_PATH" -type f 2>/dev/null | wc -l)
    ok "Backup criado: backups/$BACKUP_NAME ($COUNT arquivos)"
    log "Backup: $BACKUP_PATH — $COUNT arquivos"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. PATCH DE ARQUIVOS FONTE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Patch de arquivos fonte (.py .yaml .json .sh …)"

if [ -z "$PROJECT_DIR" ]; then
    skip "Sem projeto — etapa pulada"
else
    cd "$SCRIPT_DIR"
    ARGS="--project $PROJECT_DIR --translations $TRANSLATIONS --pending $PENDING --incremental"
    [ "$DRY_RUN" = true ] && ARGS="$ARGS --dry-run"
    [ "$NO_API" = false ] && ARGS="$ARGS --use-llm"

    info "python3 scripts/translator.py $ARGS"
    python3 scripts/translator.py $ARGS
    log "translator.py concluído"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. PATCH DE MARKDOWN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Patch de arquivos Markdown (.md)"

if [ -z "$PROJECT_DIR" ]; then
    skip "Sem projeto — etapa pulada"
else
    cd "$SCRIPT_DIR"
    MD_ARGS="--project $PROJECT_DIR"
    [ "$DRY_RUN" = true ] && MD_ARGS="$MD_ARGS --dry-run"
    [ "$NO_API" = true ]  && MD_ARGS="$MD_ARGS --no-api"

    info "python3 scripts/translate_md.py $MD_ARGS"
    python3 scripts/translate_md.py $MD_ARGS
    log "translate_md.py concluído"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. PATCH DO BANCO MySQL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Patch do banco MySQL"

if [ "$DOCKER_DB" = false ]; then
    skip "Container DB indisponível — etapa pulada"
else
    cd "$SCRIPT_DIR"
    DB_ARGS=""
    [ "$DRY_RUN" = true ] && DB_ARGS="$DB_ARGS --dry-run"
    [ "$NO_API" = true ]  && DB_ARGS="$DB_ARGS --no-api"

    info "python3 scripts/patch_database.py $DB_ARGS"
    python3 scripts/patch_database.py $DB_ARGS
    log "patch_database.py concluído"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. PATCH DOS ASSETS WEB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Patch dos assets web (JS compilados)"

if [ "$DOCKER_WEB" = false ]; then
    skip "Container Web indisponível — etapa pulada"
else
    cd "$SCRIPT_DIR"
    WEB_ARGS=""
    [ "$DRY_RUN" = true ] && WEB_ARGS="$WEB_ARGS --dry-run"
    [ "$NO_API" = true ]  && WEB_ARGS="$WEB_ARGS --no-api"

    info "python3 scripts/patch_web_assets.py $WEB_ARGS"
    python3 scripts/patch_web_assets.py $WEB_ARGS
    log "patch_web_assets.py concluído"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. TRADUÇÃO DE PENDENTES VIA API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Tradução de strings pendentes"

cd "$SCRIPT_DIR"

if [ "$DRY_RUN" = true ]; then
    skip "DRY-RUN — tradução de pendentes pulada"
    info "Estatísticas atuais:"
    python3 scripts/translate_pending.py --stats
elif [ "$NO_API" = true ]; then
    skip "Sem API — pendentes não serão traduzidas automaticamente"
    info "Para traduzir depois: python3 scripts/translate_pending.py"
else
    info "Iniciando tradução automática de pendentes …"
    python3 scripts/translate_pending.py
    log "translate_pending.py concluído"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. VALIDAÇÃO DE SINTAXE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Validação + rollback de arquivos quebrados"

if [ -z "$PROJECT_DIR" ]; then
    skip "Sem projeto — validação pulada"
elif [ "$DRY_RUN" = true ]; then
    skip "DRY-RUN — validação pulada"
else
    cd "$SCRIPT_DIR"
    info "Verificando sintaxe dos .py no projeto …"
    python3 revert_broken.py
    log "revert_broken.py concluído"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. RESUMO FINAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step "Resumo"

cd "$SCRIPT_DIR"
TOTAL_TR=$(python3 -c "import json; print(len(json.load(open('translations/translations.json')).get('translations',{})))" 2>/dev/null || echo "?")
TOTAL_PD=$(python3 -c "import json; print(len(json.load(open('translations/pending.json')).get('pending',{})))" 2>/dev/null || echo "?")

echo ""
echo -e "${B}┌─────────────────────────────────────────────────────────┐${N}"
echo -e "${B}│  Banco de traduções                                     │${N}"
echo -e "${B}├─────────────────────────────────────────────────────────┤${N}"
echo -e "${B}│${N}  Traduções no banco : ${G}${TOTAL_TR}${N}"
echo -e "${B}│${N}  Pendentes          : ${Y}${TOTAL_PD}${N}"
echo -e "${B}│${N}  Log                : $LOG_FILE"
echo -e "${B}└─────────────────────────────────────────────────────────┘${N}"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo -e "  ${Y}Modo DRY-RUN — nada foi alterado no projeto.${N}"
else
    echo -e "  ${G}Patch completo finalizado com sucesso.${N}"

    if [ "$TOTAL_PD" != "0" ] && [ "$TOTAL_PD" != "?" ]; then
        echo ""
        echo -e "  ${Y}Ainda há $TOTAL_PD strings pendentes.${N}"
        echo -e "  Para traduzir manualmente:"
        echo -e "    python3 scripts/translate_pending.py --export"
        echo -e "    # edite translations/pending_review.csv"
        echo -e "    python3 scripts/translate_pending.py --import-csv"
    fi
fi

log "Finalizado — TR=$TOTAL_TR PD=$TOTAL_PD"
echo ""
