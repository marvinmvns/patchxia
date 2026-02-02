#!/bin/bash
#===============================================================================
# Script de Teste do Sistema de Tradução
#===============================================================================
# Este script cria um ambiente de teste com arquivos simulados do projeto
# xiaozhi-esp32-server para validar o funcionamento do patch de tradução.
#
# Uso: ./test_translation.sh [--clean]
#===============================================================================

set -e

# Diretórios
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH_DIR="$(dirname "$SCRIPT_DIR")"
TEST_PROJECT="${SCRIPT_DIR}/test_project"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[TEST]${NC} $1"
}

error() {
    echo -e "${RED}[ERRO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[AVISO]${NC} $1"
}

# Limpar ambiente de teste
clean_test_env() {
    log "Limpando ambiente de teste..."
    rm -rf "$TEST_PROJECT"
    log "Ambiente limpo!"
}

# Criar arquivos de teste simulando o projeto real
create_test_files() {
    log "Criando arquivos de teste..."

    mkdir -p "$TEST_PROJECT"/{main,docs,config}

    # Simular arquivo Python com strings em chinês
    cat > "$TEST_PROJECT/main/server.py" << 'PYEOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务器主程序 - Servidor principal
Este arquivo simula o servidor do xiaozhi-esp32
"""

import logging

# 配置文件路径
CONFIG_PATH = "/etc/xiaozhi/config.yaml"

class VoiceServer:
    """语音识别服务器"""

    def __init__(self):
        self.status = "离线"
        self.message = "请稍候"
        logging.info("服务器启动中...")

    def connect(self):
        """连接成功后的处理"""
        self.status = "在线"
        return "连接成功"

    def disconnect(self):
        """断开连接"""
        self.status = "离线"
        return "连接失败"

    def process_audio(self, audio_data):
        """
        处理音频数据
        使用语音合成和语音识别
        """
        if not audio_data:
            return {"错误": "无数据"}

        # 正在处理音频
        result = self._recognize(audio_data)
        return {"成功": result, "消息": "处理完成"}

    def _recognize(self, data):
        """智能对话处理"""
        return "大语言模型响应"


if __name__ == "__main__":
    server = VoiceServer()
    print("开始服务器")
    server.connect()
    print("停止服务器")
PYEOF

    # Simular arquivo Vue com strings em chinês
    cat > "$TEST_PROJECT/main/dashboard.vue" << 'VUEEOF'
<template>
  <div class="dashboard">
    <h1>智能家居控制面板</h1>

    <div class="status">
      <span>状态: {{ status }}</span>
      <button @click="refresh">刷新</button>
    </div>

    <div class="controls">
      <button @click="start">开始</button>
      <button @click="stop">停止</button>
      <button @click="settings">设置</button>
    </div>

    <div class="device-list">
      <h2>设备列表</h2>
      <div v-if="devices.length === 0">暂无内容</div>
      <div v-for="device in devices" :key="device.id">
        <span>{{ device.name }}</span>
        <span>{{ device.online ? '在线' : '离线' }}</span>
      </div>
    </div>

    <div class="audio-controls">
      <h2>音频控制</h2>
      <button @click="play">播放</button>
      <button @click="pause">暂停</button>
      <button @click="mute">静音</button>
      <input type="range" v-model="volume" min="0" max="100" />
      <span>音量: {{ volume }}%</span>
    </div>

    <!-- 加载中提示 -->
    <div v-if="loading" class="loading">
      加载中...
    </div>
  </div>
</template>

<script>
export default {
  name: 'Dashboard',
  data() {
    return {
      status: '离线',
      loading: false,
      volume: 50,
      devices: []
    }
  },
  methods: {
    start() {
      this.status = '在线'
      console.log('开始')
    },
    stop() {
      this.status = '离线'
      console.log('停止')
    },
    refresh() {
      this.loading = true
      console.log('刷新')
    },
    settings() {
      console.log('打开设置')
    },
    play() {
      console.log('播放')
    },
    pause() {
      console.log('暂停')
    },
    mute() {
      console.log('静音')
    }
  }
}
</script>
VUEEOF

    # Simular arquivo JSON de configuração
    cat > "$TEST_PROJECT/config/settings.json" << 'JSONEOF'
{
  "app_name": "小智ESP32服务器",
  "version": "1.0.0",
  "language": "zh-CN",
  "ui": {
    "title": "智能语音助手",
    "welcome_message": "欢迎使用小智语音助手",
    "loading_text": "加载中",
    "error_text": "错误",
    "success_text": "成功",
    "buttons": {
      "start": "开始",
      "stop": "停止",
      "save": "保存",
      "cancel": "取消",
      "confirm": "确定",
      "delete": "删除",
      "add": "添加",
      "edit": "编辑",
      "search": "搜索",
      "refresh": "刷新"
    },
    "messages": {
      "connection_success": "连接成功",
      "connection_failed": "连接失败",
      "please_wait": "请稍候",
      "no_data": "无数据",
      "processing": "正在处理"
    }
  },
  "voice": {
    "wake_word": "小智小智",
    "tts_engine": "语音合成引擎",
    "asr_engine": "语音识别引擎"
  }
}
JSONEOF

    # Simular arquivo YAML
    cat > "$TEST_PROJECT/config/server.yaml" << 'YAMLEOF'
# 服务器配置文件
server:
  name: "小智服务器"  # 服务器名称
  port: 8080
  host: "0.0.0.0"

# 语音识别配置
asr:
  engine: "whisper"
  language: "zh"
  description: "语音识别引擎配置"

# 语音合成配置
tts:
  engine: "edge-tts"
  voice: "zh-CN-XiaoxiaoNeural"
  description: "语音合成引擎配置"

# 大语言模型配置
llm:
  provider: "openai"
  model: "gpt-4"
  description: "大语言模型配置"

# 日志配置
logging:
  level: "INFO"
  format: "%(asctime)s - %(levelname)s - %(message)s"
  description: "日志配置"
YAMLEOF

    # Criar Dockerfile simulado
    cat > "$TEST_PROJECT/Dockerfile" << 'DOCKEREOF'
# 基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install -r requirements.txt

# 复制代码
COPY . .

# 启动服务器
CMD ["python", "main/server.py"]
DOCKEREOF

    # Criar docker-setup.sh simulado
    cat > "$TEST_PROJECT/docker-setup.sh" << 'SHEOF'
#!/bin/bash
# Docker 安装脚本
# 自动配置和启动服务器

echo "开始安装..."
echo "正在处理依赖..."
echo "安装完成！"
echo "启动服务器..."
SHEOF

    chmod +x "$TEST_PROJECT/docker-setup.sh"

    log "Arquivos de teste criados em: $TEST_PROJECT"
}

# Executar teste de tradução
run_translation_test() {
    log "Executando teste de tradução..."
    echo ""

    # Verificar se o tradutor existe
    if [ ! -f "${PATCH_DIR}/scripts/translator.py" ]; then
        error "translator.py não encontrado!"
        exit 1
    fi

    # Verificar sintaxe do Python
    log "Verificando sintaxe do tradutor Python..."
    python3 -m py_compile "${PATCH_DIR}/scripts/translator.py" || {
        error "Erro de sintaxe no translator.py"
        exit 1
    }
    log "Sintaxe OK!"

    # Executar tradução em modo dry-run
    log "Executando tradução em modo dry-run..."
    echo ""

    python3 "${PATCH_DIR}/scripts/translator.py" \
        --project "$TEST_PROJECT" \
        --translations "${PATCH_DIR}/translations/translations.json" \
        --pending "${PATCH_DIR}/translations/pending.json" \
        --dry-run \
        --incremental

    echo ""
    log "Teste dry-run concluído!"
}

# Executar tradução real (com modificação de arquivos)
run_real_translation() {
    log "Executando tradução real nos arquivos de teste..."
    echo ""

    python3 "${PATCH_DIR}/scripts/translator.py" \
        --project "$TEST_PROJECT" \
        --translations "${PATCH_DIR}/translations/translations.json" \
        --pending "${PATCH_DIR}/translations/pending.json" \
        --incremental

    echo ""
    log "Tradução aplicada!"

    # Mostrar arquivos modificados
    log "Verificando arquivos traduzidos..."
    echo ""

    echo "=== server.py (primeiras 30 linhas) ==="
    head -30 "$TEST_PROJECT/main/server.py"
    echo ""

    echo "=== settings.json (primeiras 30 linhas) ==="
    head -30 "$TEST_PROJECT/config/settings.json"
    echo ""
}

# Validar código após tradução
validate_translated_code() {
    log "Validando código traduzido..."

    local errors=0

    # Verificar Python
    for file in "$TEST_PROJECT"/**/*.py; do
        if [ -f "$file" ]; then
            if ! python3 -m py_compile "$file" 2>/dev/null; then
                error "Erro de sintaxe em: $file"
                ((errors++))
            fi
        fi
    done

    # Verificar JSON
    for file in "$TEST_PROJECT"/**/*.json; do
        if [ -f "$file" ]; then
            if ! python3 -c "import json; json.load(open('$file'))" 2>/dev/null; then
                error "JSON inválido em: $file"
                ((errors++))
            fi
        fi
    done

    if [ $errors -eq 0 ]; then
        log "Validação OK! Nenhum erro encontrado."
        return 0
    else
        error "Validação encontrou $errors erro(s)"
        return 1
    fi
}

# Mostrar ajuda
show_help() {
    echo "Uso: $0 [opções]"
    echo ""
    echo "Opções:"
    echo "  --clean      Limpa o ambiente de teste"
    echo "  --dry-run    Executa apenas em modo simulação"
    echo "  --real       Executa tradução real nos arquivos"
    echo "  --validate   Apenas valida os arquivos traduzidos"
    echo "  --full       Executa todos os testes"
    echo "  --help       Mostra esta ajuda"
    echo ""
}

# Main
main() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║         TESTE DO SISTEMA DE TRADUÇÃO PT-BR                   ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    case "${1:-}" in
        --clean)
            clean_test_env
            ;;
        --dry-run)
            clean_test_env
            create_test_files
            run_translation_test
            ;;
        --real)
            clean_test_env
            create_test_files
            run_real_translation
            validate_translated_code
            ;;
        --validate)
            validate_translated_code
            ;;
        --full)
            clean_test_env
            create_test_files
            log "=== FASE 1: Teste Dry-Run ==="
            run_translation_test
            echo ""
            log "=== FASE 2: Tradução Real ==="
            run_real_translation
            echo ""
            log "=== FASE 3: Validação ==="
            validate_translated_code
            echo ""
            log "Todos os testes concluídos com sucesso!"
            ;;
        --help|-h)
            show_help
            ;;
        *)
            # Teste padrão: dry-run
            clean_test_env
            create_test_files
            run_translation_test
            ;;
    esac
}

main "$@"
