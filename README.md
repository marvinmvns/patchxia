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
chmod +x apply-patch.sh
./apply-patch.sh ../xiaozhi-esp32-server
```

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
| `--help` | Mostra ajuda |

## Estrutura do Projeto

```
patchxia/
├── apply-patch.sh          # Script principal
├── scripts/
│   └── translator.py       # Motor de traducao Python
├── translations/
│   ├── translations.json   # Banco de traducoes verificadas
│   └── pending.json        # Strings pendentes de traducao
├── backups/                # Backups automaticos
├── tests/
│   └── test_translation.sh # Script de teste
├── config/                 # Configuracoes
└── logs/                   # Logs de execucao
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
2. Execute o patch novamente (modo incremental)
3. Novas strings serao adicionadas a `pending.json`
4. Revise e aprove as novas traducoes

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
