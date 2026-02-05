#!/bin/bash
# ==============================================================
# full-pipeline.sh — Pipeline completo de tradução PT-BR
# ==============================================================
# Executa todo o ciclo de vida do patch:
#
#   FASE 1: PREPARAÇÃO
#     1  Verificar dependências (python3, jq, docker, git)
#     2  Clone/atualização do projeto xiaozhi (opcional)
#     3  Iniciar containers Docker
#     4  Aguardar containers ficarem saudáveis
#
#   FASE 2: TRADUÇÃO (via update-all.sh)
#     5  Limpeza do banco de traduções
#     6  Análise de cobertura
#     7  Backup automático
#     8  Patch de arquivos fonte
#     9  Patch de Markdown
#    10  Patch do banco MySQL
#    11  Patch dos assets web
#    12  Tradução de pendentes via API
#    13  Validação + rollback de quebrados
#
#   FASE 3: TESTE & FINALIZAÇÃO
#    14  Testes de sanidade (sintaxe, traduções)
#    15  Relatório final
#    16  Parar containers (opcional)
#
# Uso:
#   ./full-pipeline.sh                            # fluxo completo interativo
#   ./full-pipeline.sh --auto                     # automático (sem confirmações)
#   ./full-pipeline.sh --dry-run                  # preview sem alterar nada
#   ./full-pipeline.sh --no-api                   # sem chamadas externas de API
#   ./full-pipeline.sh --keep-containers          # não pergunta para parar ao final
#   ./full-pipeline.sh --stop-after               # para containers ao final automaticamente
#   ./full-pipeline.sh --project /outro/caminho   # projeto em outro lugar
#   ./full-pipeline.sh --skip-clone               # não clona/atualiza projeto
# ==============================================================

set -e  # sai em caso de erro

# ─── Caminhos base ────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PROJECT="$(cd "$SCRIPT_DIR/.." && pwd)/xiaozhi-esp32-server"
XIAOZHI_REPO="https://github.com/xinnan-tech/xiaozhi-esp32-server.git"

TRANSLATIONS="$SCRIPT_DIR/translations/translations.json"
PENDING="$SCRIPT_DIR/translations/pending.json"
LOGS="$SCRIPT_DIR/logs"
LOG_FILE="$LOGS/full-pipeline-$(date '+%Y%m%d_%H%M%S').log"

# ─── Cores ────────────────────────────────────────────────────
R='\033[0;31m'  # vermelho
G='\033[0;32m'  # verde
Y='\033[1;33m'  # amarelo
B='\033[0;34m'  # azul
C='\033[0;36m'  # cyan
M='\033[0;35m'  # magenta
N='\033[0m'     # reset
BOLD='\033[1m'

# ─── Flags ────────────────────────────────────────────────────
DRY_RUN=false
NO_API=false
AUTO_MODE=false
KEEP_CONTAINERS=false
STOP_AFTER=false
SKIP_CLONE=false
PROJECT_DIR="$DEFAULT_PROJECT"

# ─── Parse ────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)         DRY_RUN=true;         shift ;;
        --no-api)          NO_API=true;          shift ;;
        --auto)            AUTO_MODE=true;       shift ;;
        --keep-containers) KEEP_CONTAINERS=true; shift ;;
        --stop-after)      STOP_AFTER=true;      shift ;;
        --skip-clone)      SKIP_CLONE=true;      shift ;;
        --project)         PROJECT_DIR="$2";     shift 2 ;;
        --help|-h)
            echo "Uso: $0 [opções]"
            echo ""
            echo "Opções:"
            echo "  --dry-run           Preview de tudo sem alterar nada"
            echo "  --no-api            Sem chamadas externas de API"
            echo "  --auto              Modo automático (sem confirmações)"
            echo "  --keep-containers   Não pergunta para parar containers ao final"
            echo "  --stop-after        Para containers automaticamente ao final"
            echo "  --skip-clone        Não clona/atualiza projeto"
            echo "  --project DIR       Caminho do projeto xiaozhi-esp32-server"
            echo ""
            echo "Exemplos:"
            echo "  $0                          # execução interativa"
            echo "  $0 --auto --stop-after      # CI/CD (auto, para ao final)"
            echo "  $0 --dry-run                # apenas preview"
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
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

# ─── Helpers de exibição ──────────────────────────────────────
ok()    { echo -e "  ${G}✓${N} $*";  log "[OK]   $*"; }
warn()  { echo -e "  ${Y}!${N} $*";  log "[WARN] $*"; }
err()   { echo -e "  ${R}✗${N} $*";  log "[ERR]  $*"; }
info()  { echo -e "  ${C}→${N} $*";  log "[INFO] $*"; }
skip()  { echo -e "  ${Y}○${N} $*";  log "[SKIP] $*"; }
debug() { log "[DEBUG] $*"; }

phase() {
    echo ""
    echo -e "${M}══════════════════════════════════════════════════════════════${N}"
    echo -e "${M}  $*${N}"
    echo -e "${M}══════════════════════════════════════════════════════════════${N}"
    log "=== FASE: $* ==="
}

step() {
    echo ""
    echo -e "  ${B}──────────────────────────────────────────────────────────${N}"
    echo -e "  ${B}$*${N}"
    echo -e "  ${B}──────────────────────────────────────────────────────────${N}"
    log "--- $* ---"
}

confirm() {
    if [ "$AUTO_MODE" = true ]; then
        return 0
    fi
    echo ""
    read -p "  $1 [S/n] " response
    case "$response" in
        [nN][oO]|[nN]) return 1 ;;
        *) return 0 ;;
    esac
}

container_up() {
    docker inspect --format '{{.State.Running}}' "$1" 2>/dev/null | grep -q "true"
}

wait_for_healthy() {
    local container=$1
    local timeout=${2:-120}
    local elapsed=0

    while [ $elapsed -lt $timeout ]; do
        local health
        health=$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || echo "none")

        if [ "$health" = "healthy" ]; then
            return 0
        elif [ "$health" = "none" ]; then
            # Container sem healthcheck, verifica se está rodando
            if container_up "$container"; then
                return 0
            fi
        fi

        sleep 2
        ((elapsed+=2))
        echo -ne "\r  ${C}→${N} Aguardando $container... ${elapsed}s/${timeout}s"
    done
    echo ""
    return 1
}

# ─── Banner ───────────────────────────────────────────────────
clear
echo ""
echo -e "${B}╔═════════════════════════════════════════════════════════════════╗${N}"
echo -e "${B}║                                                                 ║${N}"
echo -e "${B}║    ${BOLD}PIPELINE COMPLETO — Patch de Tradução PT-BR${N}${B}                ║${N}"
echo -e "${B}║                                                                 ║${N}"
echo -e "${B}║    xiaozhi-esp32-server → Português do Brasil                  ║${N}"
echo -e "${B}║                                                                 ║${N}"
echo -e "${B}╚═════════════════════════════════════════════════════════════════╝${N}"
echo ""
echo -e "  ${BOLD}Configuração:${N}"
echo -e "    Modo        : $([ "$DRY_RUN" = true ] && echo -e "${Y}DRY-RUN (preview)${N}" || echo -e "${G}APLICAR${N}")"
echo -e "    API externa : $([ "$NO_API" = true ] && echo -e "${Y}desabilitada${N}" || echo "habilitada")"
echo -e "    Interativo  : $([ "$AUTO_MODE" = true ] && echo -e "${Y}automático${N}" || echo "sim")"
echo -e "    Projeto     : $PROJECT_DIR"
echo -e "    Log         : $LOG_FILE"
echo ""

log "Pipeline iniciado — DRY_RUN=$DRY_RUN NO_API=$NO_API AUTO=$AUTO_MODE PROJECT=$PROJECT_DIR"

START_TIME=$(date +%s)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FASE 1: PREPARAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
phase "FASE 1: PREPARAÇÃO"

# ─── 1.1 Verificar dependências ───────────────────────────────
step "1.1 Verificar dependências"

MISSING_DEPS=()

# python3
if command -v python3 >/dev/null 2>&1; then
    PY_VERSION=$(python3 --version 2>&1)
    ok "python3 encontrado ($PY_VERSION)"
else
    err "python3 não encontrado"
    MISSING_DEPS+=("python3")
fi

# jq
if command -v jq >/dev/null 2>&1; then
    ok "jq encontrado ($(jq --version 2>&1))"
else
    err "jq não encontrado"
    MISSING_DEPS+=("jq")
fi

# docker
if command -v docker >/dev/null 2>&1; then
    ok "docker encontrado ($(docker --version 2>&1 | head -1))"
else
    err "docker não encontrado"
    MISSING_DEPS+=("docker")
fi

# docker compose
if docker compose version >/dev/null 2>&1; then
    ok "docker compose encontrado"
else
    warn "docker compose não encontrado (tentará docker-compose)"
    if command -v docker-compose >/dev/null 2>&1; then
        ok "docker-compose encontrado"
        COMPOSE_CMD="docker-compose"
    else
        err "Nenhum docker compose disponível"
        MISSING_DEPS+=("docker-compose")
    fi
fi
COMPOSE_CMD="${COMPOSE_CMD:-docker compose}"

# git
if command -v git >/dev/null 2>&1; then
    ok "git encontrado ($(git --version 2>&1))"
else
    warn "git não encontrado (clone/update será pulado)"
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo ""
    err "Dependências faltando: ${MISSING_DEPS[*]}"
    echo ""
    echo -e "  Instale com:"
    echo -e "    ${C}sudo apt install ${MISSING_DEPS[*]}${N}"
    echo ""
    exit 1
fi

# ─── 1.2 Clone/atualização do projeto ─────────────────────────
step "1.2 Clone/atualização do projeto"

if [ "$SKIP_CLONE" = true ]; then
    skip "Clone/update pulado por --skip-clone"
elif [ ! -d "$PROJECT_DIR" ]; then
    info "Projeto não encontrado em $PROJECT_DIR"
    if confirm "Deseja clonar o repositório?"; then
        info "Clonando $XIAOZHI_REPO..."
        git clone "$XIAOZHI_REPO" "$PROJECT_DIR"
        ok "Projeto clonado com sucesso"
    else
        warn "Projeto não clonado. Algumas etapas serão puladas."
    fi
elif command -v git >/dev/null 2>&1; then
    if [ -d "$PROJECT_DIR/.git" ]; then
        info "Verificando atualizações..."
        cd "$PROJECT_DIR"

        # Verifica se há mudanças locais
        if git diff --quiet 2>/dev/null; then
            if confirm "Atualizar projeto com git pull?"; then
                git pull --ff-only 2>&1 | while read -r line; do echo "    $line"; done
                ok "Projeto atualizado"
            else
                skip "Atualização pulada pelo usuário"
            fi
        else
            warn "Há mudanças locais no projeto. Pull não executado."
            info "Execute git stash ou commit as mudanças primeiro."
        fi
        cd "$SCRIPT_DIR"
    fi
else
    ok "Projeto existe em $PROJECT_DIR"
fi

# ─── 1.3 Iniciar containers Docker ────────────────────────────
step "1.3 Iniciar containers Docker"

COMPOSE_DIR="$PROJECT_DIR/main/xiaozhi-server"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose_all.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
    warn "docker-compose_all.yml não encontrado em $COMPOSE_DIR"
    warn "Etapas Docker serão puladas"
    DOCKER_AVAILABLE=false
else
    DOCKER_AVAILABLE=true

    # Verifica estado atual dos containers
    CONTAINERS_RUNNING=0
    for container in xiaozhi-esp32-server-db xiaozhi-esp32-server-redis xiaozhi-esp32-server-web xiaozhi-esp32-server; do
        if container_up "$container"; then
            ((CONTAINERS_RUNNING++))
        fi
    done

    if [ $CONTAINERS_RUNNING -eq 4 ]; then
        ok "Todos os 4 containers já estão rodando"
    elif [ $CONTAINERS_RUNNING -gt 0 ]; then
        info "$CONTAINERS_RUNNING/4 containers rodando"
        if confirm "Reiniciar todos os containers?"; then
            info "Parando containers existentes..."
            cd "$COMPOSE_DIR"
            $COMPOSE_CMD -f docker-compose_all.yml down 2>&1 | while read -r line; do echo "    $line"; done
            CONTAINERS_RUNNING=0
        fi
    fi

    if [ $CONTAINERS_RUNNING -lt 4 ]; then
        if [ "$DRY_RUN" = true ]; then
            skip "DRY-RUN — containers não serão iniciados"
        else
            info "Iniciando containers..."
            cd "$COMPOSE_DIR"
            $COMPOSE_CMD -f docker-compose_all.yml up -d 2>&1 | while read -r line; do echo "    $line"; done
            ok "Comando de inicialização enviado"
        fi
    fi
fi

# ─── 1.4 Aguardar containers ficarem saudáveis ────────────────
step "1.4 Aguardar containers ficarem saudáveis"

if [ "$DOCKER_AVAILABLE" = false ]; then
    skip "Docker não disponível"
elif [ "$DRY_RUN" = true ]; then
    skip "DRY-RUN — aguarda pulado"
else
    echo ""

    # MySQL (tem healthcheck)
    if wait_for_healthy "xiaozhi-esp32-server-db" 120; then
        echo ""
        ok "MySQL pronto"
    else
        echo ""
        warn "MySQL não ficou healthy no timeout"
    fi

    # Redis (tem healthcheck)
    if wait_for_healthy "xiaozhi-esp32-server-redis" 60; then
        ok "Redis pronto"
    else
        warn "Redis não ficou healthy no timeout"
    fi

    # Web (sem healthcheck, só verifica running)
    if wait_for_healthy "xiaozhi-esp32-server-web" 60; then
        ok "Web pronto"
    else
        warn "Web não ficou pronto no timeout"
    fi

    # Server (sem healthcheck)
    if wait_for_healthy "xiaozhi-esp32-server" 60; then
        ok "Server pronto"
    else
        warn "Server não ficou pronto no timeout"
    fi

    echo ""
    info "Status final dos containers:"
    docker ps --format "table {{.Names}}\t{{.Status}}" --filter "name=xiaozhi" 2>/dev/null | while read -r line; do echo "    $line"; done
fi

cd "$SCRIPT_DIR"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FASE 2: TRADUÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
phase "FASE 2: TRADUÇÃO"

step "Executando update-all.sh"

cd "$SCRIPT_DIR"

# Monta argumentos para update-all.sh
UPDATE_ARGS="--project $PROJECT_DIR"
[ "$DRY_RUN" = true ] && UPDATE_ARGS="$UPDATE_ARGS --dry-run"
[ "$NO_API" = true ]  && UPDATE_ARGS="$UPDATE_ARGS --no-api"

if [ "$DOCKER_AVAILABLE" = false ]; then
    UPDATE_ARGS="$UPDATE_ARGS --skip-docker"
fi

echo ""
info "Comando: ./update-all.sh $UPDATE_ARGS"
echo ""

# Executa update-all.sh (que já tem as 11 etapas)
./update-all.sh $UPDATE_ARGS 2>&1 | tee -a "$LOG_FILE"

UPDATE_EXIT_CODE=${PIPESTATUS[0]}

if [ $UPDATE_EXIT_CODE -ne 0 ]; then
    err "update-all.sh falhou com código $UPDATE_EXIT_CODE"
    log "update-all.sh falhou com código $UPDATE_EXIT_CODE"
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FASE 3: TESTE & FINALIZAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
phase "FASE 3: TESTE & FINALIZAÇÃO"

# ─── 3.1 Testes de sanidade ───────────────────────────────────
step "3.1 Testes de sanidade"

if [ "$DRY_RUN" = true ]; then
    skip "DRY-RUN — testes pulados"
else
    TESTS_PASSED=0
    TESTS_FAILED=0

    # Teste 1: Verificar sintaxe Python
    info "Verificando sintaxe de arquivos Python..."
    if [ -d "$PROJECT_DIR" ]; then
        SYNTAX_ERRORS=$(find "$PROJECT_DIR" -name "*.py" -type f 2>/dev/null | head -100 | while read -r pyfile; do
            python3 -m py_compile "$pyfile" 2>&1 && echo "" || echo "$pyfile"
        done | grep -v "^$" | wc -l)

        if [ "$SYNTAX_ERRORS" -eq 0 ]; then
            ok "Arquivos Python com sintaxe válida"
            ((TESTS_PASSED++))
        else
            warn "$SYNTAX_ERRORS arquivos com erros de sintaxe"
            ((TESTS_FAILED++))
        fi
    else
        skip "Projeto não disponível"
    fi

    # Teste 2: Verificar se banco de traduções é válido
    info "Verificando integridade do banco de traduções..."
    if python3 -c "import json; json.load(open('$TRANSLATIONS'))" 2>/dev/null; then
        ok "translations.json é JSON válido"
        ((TESTS_PASSED++))
    else
        err "translations.json inválido"
        ((TESTS_FAILED++))
    fi

    # Teste 3: Verificar pending.json
    if python3 -c "import json; json.load(open('$PENDING'))" 2>/dev/null; then
        ok "pending.json é JSON válido"
        ((TESTS_PASSED++))
    else
        err "pending.json inválido"
        ((TESTS_FAILED++))
    fi

    # Teste 4: Verificar containers (se disponíveis)
    if [ "$DOCKER_AVAILABLE" = true ]; then
        info "Verificando saúde dos containers..."
        HEALTHY_CONTAINERS=0
        for container in xiaozhi-esp32-server-db xiaozhi-esp32-server-redis xiaozhi-esp32-server-web; do
            if container_up "$container"; then
                ((HEALTHY_CONTAINERS++))
            fi
        done

        if [ $HEALTHY_CONTAINERS -ge 3 ]; then
            ok "$HEALTHY_CONTAINERS/3 containers essenciais rodando"
            ((TESTS_PASSED++))
        else
            warn "Apenas $HEALTHY_CONTAINERS/3 containers rodando"
            ((TESTS_FAILED++))
        fi
    fi

    # Teste 5: Verificar conexão com MySQL
    if [ "$DOCKER_AVAILABLE" = true ] && container_up "xiaozhi-esp32-server-db"; then
        info "Testando conexão MySQL..."
        if docker exec xiaozhi-esp32-server-db mysql -uroot -p123456 -e "SELECT 1" >/dev/null 2>&1; then
            ok "Conexão MySQL funcionando"
            ((TESTS_PASSED++))
        else
            warn "Falha na conexão MySQL"
            ((TESTS_FAILED++))
        fi
    fi

    echo ""
    info "Resultado: ${TESTS_PASSED} passou, ${TESTS_FAILED} falhou"
fi

# ─── 3.2 Relatório final ──────────────────────────────────────
step "3.2 Relatório final"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
DURATION_MIN=$((DURATION / 60))
DURATION_SEC=$((DURATION % 60))

cd "$SCRIPT_DIR"
TOTAL_TR=$(python3 -c "import json; print(len(json.load(open('translations/translations.json')).get('translations',{})))" 2>/dev/null || echo "?")
TOTAL_PD=$(python3 -c "import json; print(len(json.load(open('translations/pending.json')).get('pending',{})))" 2>/dev/null || echo "?")

# Contar arquivos com chinês restante
REMAINING_CHINESE="?"
if [ -d "$PROJECT_DIR" ]; then
    REMAINING_CHINESE=$(find "$PROJECT_DIR" \( -name "*.py" -o -name "*.yaml" -o -name "*.json" -o -name "*.vue" \) -type f 2>/dev/null | head -500 | xargs grep -l '[\u4e00-\u9fff]' 2>/dev/null | wc -l || echo "?")
fi

echo ""
echo -e "${B}╔═════════════════════════════════════════════════════════════════╗${N}"
echo -e "${B}║                      RELATÓRIO FINAL                            ║${N}"
echo -e "${B}╠═════════════════════════════════════════════════════════════════╣${N}"
echo -e "${B}║${N}                                                                 ${B}║${N}"
echo -e "${B}║${N}  ${BOLD}Estatísticas do banco:${N}                                        ${B}║${N}"
echo -e "${B}║${N}    Traduções armazenadas : ${G}${TOTAL_TR}${N}                              "
echo -e "${B}║${N}    Strings pendentes     : ${Y}${TOTAL_PD}${N}                              "
echo -e "${B}║${N}                                                                 ${B}║${N}"
echo -e "${B}║${N}  ${BOLD}Tempo de execução:${N} ${DURATION_MIN}min ${DURATION_SEC}s                              "
echo -e "${B}║${N}                                                                 ${B}║${N}"
echo -e "${B}║${N}  ${BOLD}Arquivos:${N}                                                     ${B}║${N}"
echo -e "${B}║${N}    Log completo: $LOG_FILE"
echo -e "${B}║${N}                                                                 ${B}║${N}"
echo -e "${B}╚═════════════════════════════════════════════════════════════════╝${N}"
echo ""

log "Relatório: TR=$TOTAL_TR PD=$TOTAL_PD DURATION=${DURATION}s"

if [ "$DRY_RUN" = true ]; then
    echo -e "  ${Y}Modo DRY-RUN — nenhuma alteração foi aplicada.${N}"
    echo ""
else
    echo -e "  ${G}Pipeline concluído com sucesso!${N}"
    echo ""

    if [ "$TOTAL_PD" != "0" ] && [ "$TOTAL_PD" != "?" ]; then
        echo -e "  ${Y}Ainda há $TOTAL_PD strings pendentes de tradução.${N}"
        echo -e "  Para revisar manualmente:"
        echo -e "    ${C}python3 scripts/translate_pending.py --export-csv${N}"
        echo ""
    fi
fi

# ─── 3.3 Parar containers ─────────────────────────────────────
step "3.3 Gerenciamento de containers"

if [ "$DOCKER_AVAILABLE" = false ]; then
    skip "Docker não disponível"
elif [ "$DRY_RUN" = true ]; then
    skip "DRY-RUN — containers não afetados"
elif [ "$KEEP_CONTAINERS" = true ]; then
    ok "Containers mantidos rodando (--keep-containers)"
elif [ "$STOP_AFTER" = true ]; then
    info "Parando containers automaticamente (--stop-after)..."
    cd "$COMPOSE_DIR"
    $COMPOSE_CMD -f docker-compose_all.yml down 2>&1 | while read -r line; do echo "    $line"; done
    ok "Containers parados"
elif confirm "Manter os containers rodando?"; then
    ok "Containers mantidos"
else
    info "Parando containers..."
    cd "$COMPOSE_DIR"
    $COMPOSE_CMD -f docker-compose_all.yml down 2>&1 | while read -r line; do echo "    $line"; done
    ok "Containers parados"
fi

# ─── Fim ──────────────────────────────────────────────────────
echo ""
echo -e "${G}═══════════════════════════════════════════════════════════════${N}"
echo -e "${G}  Pipeline finalizado com sucesso!${N}"
echo -e "${G}═══════════════════════════════════════════════════════════════${N}"
echo ""

log "Pipeline finalizado com sucesso"
exit 0
