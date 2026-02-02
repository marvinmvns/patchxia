# Xiaozhi Server Translation Patch (Português Brasileiro) 🇧🇷

Este projeto fornece um sistema de patch para traduzir o servidor do Xiaozhi ESP32 para Português do Brasil (pt-BR). Ele funciona modificando os arquivos originais do servidor (frontend e backend) para substituir textos em chinês por suas traduções em português.

## 📋 Funcionalidades

- **Tradução do Frontend (Web)**: Gera arquivos de internacionalização (`i18n`) e atualiza o código para suportar o novo idioma.
- **Tradução do Backend (Python)**: Substitui strings diretamente no código fonte do servidor Python.
- **Dicionário Centralizado**: Utiliza um arquivo `glossary.json` para gerenciar todas as traduções.
- **Scanner de Strings**: Capacidade de escanear o código em busca de novas strings que precisam de tradução.

## 🚀 Como Usar

### Pré-requisitos
- Python 3 instalado.
- Acesso aos arquivos do servidor Xiaozhi (este patch deve estar dentro da pasta `translation_patch` na raiz do projeto do servidor).

### 1. Aplicar Traduções
Para aplicar as traduções existentes ao servidor, execute o seguinte comando a partir da raiz do repositório:

```bash
python translation_patch/manager.py apply
```

Isso irá:
1. Ler o dicionário `glossary.json`.
2. Processar os arquivos do Frontend (Web) e Backend (Server).
3. Substituir os textos originais pelos textos traduzidos.

### 2. Atualizar ou Adicionar Traduções
Se você encontrar textos que ainda não foram traduzidos ou quiser melhorar uma tradução existente:

1. **Escaneie o código** para encontrar novas strings:
   ```bash
   python translation_patch/manager.py scan
   ```
   Isso atualizará o arquivo `translation_patch/glossary.json` com novas entradas marcadas como "TODO".

2. **Edite o Glossário**:
   Abra o arquivo `translation_patch/glossary.json` e adicione as traduções desejadas nos campos marcados como "TODO" ou vazios.

3. **Reaplique o Patch**:
   ```bash
   python translation_patch/manager.py apply
   ```

### 3. Tradução Automática (Opcional)
Existe um script auxiliar `translate_glossary.py` que contém um mapeamento de termos comuns. Você pode executá-lo para preencher automaticamente algumas traduções padrão:

```bash
python translation_patch/translate_glossary.py
```

## 📂 Estrutura do Projeto

- `manager.py`: O script principal CLI que gerencia o processo de scan e aplicação.
- `glossary.json`: O "banco de dados" de traduções. Contém pares de chave-valor (Chinês -> Português).
- `translate_glossary.py`: Script auxiliar para preencher traduções comuns.
- `processors/`: Contém a lógica específica para modificar diferentes partes do sistema:
  - `web.py`: Processador para o Frontend (Vue/JS).
  - `server.py`: Processador para o Backend (Python).
  - `mobile.py`: (Experimental) Processador para componentes móveis.
  - `api.py`: Processador para APIs.

## ⚠️ Avisos Importantes

1. **Backup**: Este patch modifica os arquivos originais do código fonte. Recomenda-se fazer um backup ou usar git para que você possa descartar as alterações se algo der errado (`git checkout .`).
2. **Segurança**: A tradução do backend usa substituição direta de strings. Embora projetado para ser seguro, verifique se o servidor inicia corretamente após a aplicação do patch.
3. **Persistência**: Se você atualizar o código do servidor original (git pull do repositório original), precisará reaplicar este patch.

## 🤝 Contribuindo

Contribuições para o glossário são muito bem-vindas! Se você melhorou as traduções no seu `glossary.json`, considere enviar um Pull Request com as atualizações.

1. Faça um fork do projeto.
2. Melhore o `glossary.json`.
3. Envie um PR.
