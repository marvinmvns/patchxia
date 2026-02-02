#!/bin/bash
#===============================================================================
# XIAOZHI ESP32 SERVER - Sistema de Patch de Tradução para Português do Brasil
#===============================================================================
# Este script aplica traduções de Chinês/Inglês para Português do Brasil
# sem modificar a estrutura do código original.
#
# Uso: ./apply-patch.sh <caminho-do-projeto> [opções]
#
# Opções:
#   --incremental    Traduz apenas strings novas (padrão)
#   --full           Retraduz todas as strings
#   --dry-run        Mostra o que seria traduzido sem aplicar
#   --rollback       Restaura o backup mais recente
#   --use-llm        Usa LLM para traduzir strings não encontradas
#   --validate       Apenas valida o código após patch
#===============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Diretório do patch
PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRANSLATIONS_DIR="${PATCH_DIR}/translations"
BACKUPS_DIR="${PATCH_DIR}/backups"
SCRIPTS_DIR="${PATCH_DIR}/scripts"
CONFIG_DIR="${PATCH_DIR}/config"
LOGS_DIR="${PATCH_DIR}/logs"

# Arquivo de traduções principal
TRANSLATIONS_FILE="${TRANSLATIONS_DIR}/translations.json"
PENDING_FILE="${TRANSLATIONS_DIR}/pending.json"

# Configurações padrão
INCREMENTAL=true
DRY_RUN=false
USE_LLM=false
VALIDATE_ONLY=false
ROLLBACK=false

# Função de log
log() {
    local level=$1
    shift
    local msg="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        INFO)  echo -e "${GREEN}[INFO]${NC} ${timestamp} - $msg" ;;
        WARN)  echo -e "${YELLOW}[WARN]${NC} ${timestamp} - $msg" ;;
        ERROR) echo -e "${RED}[ERROR]${NC} ${timestamp} - $msg" ;;
        DEBUG) echo -e "${CYAN}[DEBUG]${NC} ${timestamp} - $msg" ;;
        *)     echo -e "${timestamp} - $msg" ;;
    esac

    # Salvar log em arquivo
    mkdir -p "$LOGS_DIR"
    echo "[${level}] ${timestamp} - $msg" >> "${LOGS_DIR}/patch-$(date '+%Y%m%d').log"
}

# Banner
show_banner() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════════╗"
    echo "║     XIAOZHI ESP32 SERVER - Patch de Tradução PT-BR v1.0.0        ║"
    echo "║                                                                   ║"
    echo "║  Traduz Chinês/Inglês → Português do Brasil                      ║"
    echo "║  Repositório: github.com/xinnan-tech/xiaozhi-esp32-server        ║"
    echo "╚═══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Mostrar ajuda
show_help() {
    show_banner
    echo "Uso: $0 <caminho-do-projeto> [opções]"
    echo ""
    echo "Opções:"
    echo "  --incremental    Traduz apenas strings novas (padrão)"
    echo "  --full           Retraduz todas as strings"
    echo "  --dry-run        Mostra o que seria traduzido sem aplicar"
    echo "  --rollback       Restaura o backup mais recente"
    echo "  --use-llm        Usa LLM para traduzir strings não encontradas"
    echo "  --validate       Apenas valida o código após patch"
    echo "  --help, -h       Mostra esta ajuda"
    echo ""
    echo "Exemplos:"
    echo "  $0 ./xiaozhi-esp32-server                    # Aplica tradução incremental"
    echo "  $0 ./xiaozhi-esp32-server --dry-run          # Simula tradução"
    echo "  $0 ./xiaozhi-esp32-server --use-llm          # Usa LLM para novas strings"
    echo "  $0 ./xiaozhi-esp32-server --rollback         # Restaura backup"
    echo ""
}

# Verificar dependências
check_dependencies() {
    log INFO "Verificando dependências..."

    local missing=()

    # Python 3
    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    fi

    # jq para manipulação JSON
    if ! command -v jq &> /dev/null; then
        missing+=("jq")
    fi

    if [ ${#missing[@]} -ne 0 ]; then
        log ERROR "Dependências faltando: ${missing[*]}"
        log INFO "Instale com: sudo apt-get install ${missing[*]}"
        exit 1
    fi

    # Verificar módulos Python
    python3 -c "import json, re, os, sys" 2>/dev/null || {
        log ERROR "Módulos Python básicos não disponíveis"
        exit 1
    }

    log INFO "Todas as dependências estão instaladas"
}

# Verificar se é o projeto correto
verify_project() {
    local project_path=$1

    log INFO "Verificando projeto em: $project_path"

    if [ ! -d "$project_path" ]; then
        log ERROR "Diretório não encontrado: $project_path"
        exit 1
    fi

    # Verificar arquivos típicos do xiaozhi-esp32-server
    local indicators=0

    [ -d "${project_path}/main" ] && ((indicators++)) || true
    [ -f "${project_path}/docker-setup.sh" ] && ((indicators++)) || true
    [ -f "${project_path}/Dockerfile" ] && ((indicators++)) || true
    [ -d "${project_path}/docs" ] && ((indicators++)) || true

    # Procurar por arquivos Python com conteúdo em chinês
    if find "$project_path" -name "*.py" -type f 2>/dev/null | head -1 | grep -q .; then
        ((indicators++)) || true
    fi

    if [ $indicators -lt 2 ]; then
        log WARN "Este pode não ser o projeto xiaozhi-esp32-server"
        log WARN "Indicadores encontrados: $indicators de 5"
        read -p "Deseja continuar mesmo assim? (s/N): " response
        if [[ ! "$response" =~ ^[Ss]$ ]]; then
            log INFO "Operação cancelada pelo usuário"
            exit 0
        fi
    else
        log INFO "Projeto verificado com sucesso (indicadores: $indicators/5)"
    fi
}

# Criar backup
create_backup() {
    local project_path=$1
    local backup_name="backup_$(date '+%Y%m%d_%H%M%S')"
    local backup_path="${BACKUPS_DIR}/${backup_name}"

    log INFO "Criando backup em: $backup_path"

    mkdir -p "$BACKUPS_DIR"

    # Criar arquivo com lista de arquivos modificados
    echo "$project_path" > "${backup_path}.source"

    # Backup apenas dos arquivos que serão modificados
    mkdir -p "$backup_path"

    # Encontrar arquivos com texto em chinês/traduzíveis
    find "$project_path" \( -name "*.py" -o -name "*.html" -o -name "*.vue" \
        -o -name "*.js" -o -name "*.json" -o -name "*.yaml" -o -name "*.yml" \
        -o -name "*.md" -o -name "*.txt" \) -type f 2>/dev/null | while read -r file; do

        # Verificar se contém caracteres chineses
        if grep -P '[\x{4e00}-\x{9fff}]' "$file" &>/dev/null 2>&1 || \
           grep -E '[\u4e00-\u9fff]' "$file" &>/dev/null 2>&1; then
            # Manter estrutura de diretórios
            rel_path="${file#$project_path/}"
            mkdir -p "$(dirname "${backup_path}/${rel_path}")"
            cp "$file" "${backup_path}/${rel_path}"
        fi
    done

    log INFO "Backup criado com sucesso"
    echo "$backup_path"
}

# Restaurar backup
restore_backup() {
    local project_path=$1

    log INFO "Procurando backups disponíveis..."

    if [ ! -d "$BACKUPS_DIR" ]; then
        log ERROR "Nenhum backup encontrado"
        exit 1
    fi

    # Listar backups
    local backups=($(ls -d ${BACKUPS_DIR}/backup_* 2>/dev/null | sort -r))

    if [ ${#backups[@]} -eq 0 ]; then
        log ERROR "Nenhum backup encontrado"
        exit 1
    fi

    echo ""
    echo "Backups disponíveis:"
    for i in "${!backups[@]}"; do
        echo "  [$i] ${backups[$i]}"
    done
    echo ""

    read -p "Selecione o backup (0-$((${#backups[@]}-1))) ou Enter para o mais recente: " selection

    if [ -z "$selection" ]; then
        selection=0
    fi

    local backup_path="${backups[$selection]}"

    if [ ! -d "$backup_path" ]; then
        log ERROR "Backup inválido"
        exit 1
    fi

    log INFO "Restaurando backup: $backup_path"

    # Restaurar arquivos
    cp -r "${backup_path}"/* "$project_path/" 2>/dev/null || true

    log INFO "Backup restaurado com sucesso!"
}

# Aplicar traduções
apply_translations() {
    local project_path=$1

    log INFO "Iniciando processo de tradução..."

    # Chamar script Python de tradução
    python3 "${SCRIPTS_DIR}/translator.py" \
        --project "$project_path" \
        --translations "$TRANSLATIONS_FILE" \
        --pending "$PENDING_FILE" \
        $([ "$INCREMENTAL" = true ] && echo "--incremental") \
        $([ "$DRY_RUN" = true ] && echo "--dry-run") \
        $([ "$USE_LLM" = true ] && echo "--use-llm")

    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log INFO "Tradução aplicada com sucesso!"
    else
        log ERROR "Erro ao aplicar tradução (código: $exit_code)"
        return $exit_code
    fi
}

# Validar código após patch
validate_code() {
    local project_path=$1

    log INFO "Validando código após patch..."

    local errors=0

    # Verificar sintaxe Python
    log INFO "Verificando sintaxe Python..."
    find "$project_path" -name "*.py" -type f 2>/dev/null | while read -r file; do
        if ! python3 -m py_compile "$file" 2>/dev/null; then
            log ERROR "Erro de sintaxe em: $file"
            ((errors++)) || true
        fi
    done

    # Verificar JSON válido
    log INFO "Verificando arquivos JSON..."
    find "$project_path" -name "*.json" -type f 2>/dev/null | while read -r file; do
        if ! python3 -c "import json; json.load(open('$file'))" 2>/dev/null; then
            log ERROR "JSON inválido em: $file"
            ((errors++)) || true
        fi
    done

    # Verificar YAML válido
    log INFO "Verificando arquivos YAML..."
    if python3 -c "import yaml" 2>/dev/null; then
        find "$project_path" \( -name "*.yaml" -o -name "*.yml" \) -type f 2>/dev/null | while read -r file; do
            if ! python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
                log ERROR "YAML inválido em: $file"
                ((errors++)) || true
            fi
        done
    fi

    if [ $errors -eq 0 ]; then
        log INFO "Validação concluída sem erros!"
        return 0
    else
        log ERROR "Validação encontrou $errors erro(s)"
        return 1
    fi
}

# Mostrar estatísticas
show_stats() {
    log INFO "Estatísticas da tradução:"

    if [ -f "$TRANSLATIONS_FILE" ]; then
        local total=$(python3 -c "import json; d=json.load(open('$TRANSLATIONS_FILE')); print(len(d.get('translations', {})))" 2>/dev/null || echo "0")
        echo -e "  ${GREEN}Traduções disponíveis:${NC} $total"
    fi

    if [ -f "$PENDING_FILE" ]; then
        local pending=$(python3 -c "import json; d=json.load(open('$PENDING_FILE')); print(len(d.get('pending', [])))" 2>/dev/null || echo "0")
        echo -e "  ${YELLOW}Strings pendentes:${NC} $pending"
    fi
}

# Main
main() {
    show_banner

    # Parsear argumentos
    local project_path=""

    while [[ $# -gt 0 ]]; do
        case $1 in
            --incremental)
                INCREMENTAL=true
                shift
                ;;
            --full)
                INCREMENTAL=false
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --use-llm)
                USE_LLM=true
                shift
                ;;
            --validate)
                VALIDATE_ONLY=true
                shift
                ;;
            --rollback)
                ROLLBACK=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            -*)
                log ERROR "Opção desconhecida: $1"
                show_help
                exit 1
                ;;
            *)
                project_path="$1"
                shift
                ;;
        esac
    done

    # Verificar caminho do projeto
    if [ -z "$project_path" ]; then
        log ERROR "Caminho do projeto não especificado"
        show_help
        exit 1
    fi

    # Resolver caminho absoluto
    project_path="$(cd "$project_path" 2>/dev/null && pwd)" || {
        log ERROR "Caminho inválido: $project_path"
        exit 1
    }

    # Verificar dependências
    check_dependencies

    # Verificar projeto
    verify_project "$project_path"

    # Rollback
    if [ "$ROLLBACK" = true ]; then
        restore_backup "$project_path"
        exit 0
    fi

    # Apenas validar
    if [ "$VALIDATE_ONLY" = true ]; then
        validate_code "$project_path"
        exit $?
    fi

    # Criar backup antes de modificar
    if [ "$DRY_RUN" = false ]; then
        create_backup "$project_path"
    fi

    # Aplicar traduções
    apply_translations "$project_path"

    # Validar código
    if [ "$DRY_RUN" = false ]; then
        if ! validate_code "$project_path"; then
            log WARN "Erros encontrados! Deseja restaurar o backup? (s/N)"
            read -p "" response
            if [[ "$response" =~ ^[Ss]$ ]]; then
                restore_backup "$project_path"
            fi
        fi
    fi

    # Mostrar estatísticas
    show_stats

    log INFO "Processo concluído!"
}

main "$@"
