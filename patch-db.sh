#!/bin/bash
# ==============================================================
# patch-db.sh — Patch completo do banco MySQL do xiaozhi
# ==============================================================
# Executa todo o fluxo em uma única chamada:
#   1. Verifica se o container do banco está rodando
#   2. Mostra preview das mudanças (dry-run)
#   3. Aplica as traduções no banco
#   4. Processa strings que ficaram pendentes via API
#
# Uso:
#   ./patch-db.sh            # fluxo completo (preview → aplica → pendentes)
#   ./patch-db.sh --dry-run  # apenas preview, sem alterar nada
#   ./patch-db.sh --no-api   # aplica sem chamadas externas de API
# ==============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_CONTAINER="xiaozhi-esp32-server-db"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ── flags ─────────────────────────────────────────────────────
DRY_RUN=false
NO_API=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)  DRY_RUN=true;  shift ;;
        --no-api)   NO_API=true;   shift ;;
        --help|-h)
            echo "Uso: $0 [--dry-run] [--no-api]"
            echo "  --dry-run   Mostra preview sem alterar o banco"
            echo "  --no-api    Aplica usando apenas o banco de traduções local"
            exit 0
            ;;
        *)
            echo -e "${RED}Opção desconhecida: $1${NC}"
            echo "Uso: $0 [--dry-run] [--no-api]"
            exit 1
            ;;
    esac
done

# ── 1. Verificar container ────────────────────────────────────
echo -e "${YELLOW}[1/3] Verificando container do banco...${NC}"
if ! docker inspect --format '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null | grep -q "true"; then
    echo -e "${RED}[ERRO] Container '$DB_CONTAINER' não está rodando.${NC}"
    echo "Inicie com:  docker compose -f docker-compose_all.yml up -d"
    exit 1
fi
echo -e "${GREEN}  [OK] $DB_CONTAINER está rodando${NC}"

# ── 2. Dry-run (sempre executa primeiro para mostrar preview) ─
echo ""
echo -e "${YELLOW}[2/3] Preview das mudanças no banco...${NC}"
python3 "$SCRIPT_DIR/scripts/patch_database.py" --dry-run

# Se o modo solicitado for apenas dry-run, para aqui
if [ "$DRY_RUN" = true ]; then
    echo ""
    echo -e "${GREEN}Modo dry-run — nada foi alterado.${NC}"
    exit 0
fi

# ── 3. Aplicar traduções ──────────────────────────────────────
echo ""
echo -e "${YELLOW}[3/3] Aplicando traduções no banco...${NC}"

ARGS=""
[ "$NO_API" = true ] && ARGS="--no-api"

python3 "$SCRIPT_DIR/scripts/patch_database.py" $ARGS

# ── 4. Processar pendentes (se API habilitada) ───────────────
if [ "$NO_API" = false ]; then
    echo ""
    echo -e "${YELLOW}Processando strings pendentes via API...${NC}"
    python3 "$SCRIPT_DIR/scripts/translate_pending.py" || true
fi

echo ""
echo -e "${GREEN}Patch do banco concluído.${NC}"
