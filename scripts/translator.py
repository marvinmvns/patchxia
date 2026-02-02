#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XIAOZHI ESP32 SERVER - Tradutor de Chinês/Inglês para Português do Brasil

Este script é o núcleo do sistema de tradução. Ele:
1. Encontra strings em chinês e inglês nos arquivos
2. Aplica traduções do banco de dados
3. Usa serviços gratuitos para novas traduções
4. Mantém registro de strings pendentes para revisão manual

Serviços de tradução suportados (gratuitos):
- Google Translate (via googletrans)
- MyMemory API
- DeepL Free API (requer chave)
- LibreTranslate (local ou API)

Uso:
    python translator.py --project <caminho> --translations <arquivo.json>
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from datetime import datetime
import ssl

# Configuração de SSL para evitar erros de certificado
ssl._create_default_https_context = ssl._create_unverified_context


@dataclass
class TranslationEntry:
    """Entrada de tradução"""
    original: str
    translated: str
    source_lang: str  # 'zh' para chinês, 'en' para inglês
    translator: str   # 'manual', 'google', 'mymemory', 'deepl', 'llm'
    file_path: str
    line_number: int
    context: str
    date_added: str
    verified: bool = False


@dataclass
class PendingEntry:
    """String pendente de tradução"""
    original: str
    source_lang: str
    file_path: str
    line_number: int
    context: str
    hash: str
    date_found: str
    suggested_translation: str = ""


class TranslationDatabase:
    """Banco de dados de traduções"""

    def __init__(self, translations_file: str, pending_file: str):
        self.translations_file = translations_file
        self.pending_file = pending_file
        self.translations: Dict[str, TranslationEntry] = {}
        self.pending: Dict[str, PendingEntry] = {}
        self.load()

    def load(self):
        """Carrega traduções do arquivo"""
        if os.path.exists(self.translations_file):
            try:
                with open(self.translations_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for hash_key, entry in data.get('translations', {}).items():
                        self.translations[hash_key] = TranslationEntry(**entry)
            except Exception as e:
                print(f"Aviso: Erro ao carregar traduções: {e}")

        if os.path.exists(self.pending_file):
            try:
                with open(self.pending_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for hash_key, entry in data.get('pending', {}).items():
                        self.pending[hash_key] = PendingEntry(**entry)
            except Exception as e:
                print(f"Aviso: Erro ao carregar pendentes: {e}")

    def save(self):
        """Salva traduções no arquivo"""
        # Salvar traduções
        os.makedirs(os.path.dirname(self.translations_file), exist_ok=True)
        with open(self.translations_file, 'w', encoding='utf-8') as f:
            data = {
                'version': '1.0.0',
                'last_updated': datetime.now().isoformat(),
                'total_translations': len(self.translations),
                'translations': {k: asdict(v) for k, v in self.translations.items()}
            }
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Salvar pendentes
        with open(self.pending_file, 'w', encoding='utf-8') as f:
            data = {
                'version': '1.0.0',
                'last_updated': datetime.now().isoformat(),
                'total_pending': len(self.pending),
                'pending': {k: asdict(v) for k, v in self.pending.items()}
            }
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_hash(self, text: str) -> str:
        """Gera hash único para uma string"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

    def get_translation(self, text: str) -> Optional[str]:
        """Busca tradução existente"""
        hash_key = self.get_hash(text)
        if hash_key in self.translations:
            return self.translations[hash_key].translated
        return None

    def add_translation(self, entry: TranslationEntry):
        """Adiciona nova tradução"""
        hash_key = self.get_hash(entry.original)
        self.translations[hash_key] = entry
        # Remove do pendente se existir
        if hash_key in self.pending:
            del self.pending[hash_key]

    def add_pending(self, entry: PendingEntry):
        """Adiciona string pendente"""
        if entry.hash not in self.translations:
            self.pending[entry.hash] = entry


class TranslatorService:
    """Serviço de tradução com múltiplos backends"""

    def __init__(self, use_llm: bool = False):
        self.use_llm = use_llm
        self.cache: Dict[str, str] = {}
        self.rate_limit_delay = 1.0  # Segundos entre requisições

    def detect_language(self, text: str) -> str:
        """Detecta se o texto é chinês ou inglês"""
        # Padrão para caracteres chineses
        chinese_pattern = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')
        chinese_chars = len(chinese_pattern.findall(text))

        # Se mais de 30% são caracteres chineses, considerar chinês
        if len(text) > 0 and chinese_chars / len(text) > 0.3:
            return 'zh'

        # Verificar se é predominantemente ASCII (inglês)
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        if len(text) > 0 and ascii_chars / len(text) > 0.8:
            return 'en'

        return 'zh'  # Padrão para chinês

    def translate_mymemory(self, text: str, source_lang: str) -> Optional[str]:
        """Traduz usando MyMemory API (gratuito, 1000 palavras/dia)"""
        try:
            langpair = f"{source_lang}|pt-BR"
            url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair={langpair}"

            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

                if data.get('responseStatus') == 200:
                    translated = data.get('responseData', {}).get('translatedText', '')
                    if translated and translated.lower() != text.lower():
                        return translated

        except Exception as e:
            print(f"    Aviso MyMemory: {e}")

        return None

    def translate_google_free(self, text: str, source_lang: str) -> Optional[str]:
        """Traduz usando Google Translate (método gratuito via web)"""
        try:
            # URL do Google Translate
            sl = 'zh-CN' if source_lang == 'zh' else 'en'
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl=pt&dt=t&q={urllib.parse.quote(text)}"

            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

                if data and data[0]:
                    translated = ''.join(part[0] for part in data[0] if part[0])
                    if translated:
                        return translated

        except Exception as e:
            print(f"    Aviso Google: {e}")

        return None

    def translate_libretranslate(self, text: str, source_lang: str, api_url: str = "https://libretranslate.com/translate") -> Optional[str]:
        """Traduz usando LibreTranslate (auto-hospedável)"""
        try:
            data = json.dumps({
                'q': text,
                'source': source_lang,
                'target': 'pt',
                'format': 'text'
            }).encode('utf-8')

            req = urllib.request.Request(
                api_url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get('translatedText')

        except Exception as e:
            print(f"    Aviso LibreTranslate: {e}")

        return None

    def translate(self, text: str, source_lang: str = None) -> Tuple[Optional[str], str]:
        """
        Traduz texto usando múltiplos backends

        Retorna: (texto_traduzido, nome_do_tradutor)
        """
        if not text or len(text.strip()) < 2:
            return None, 'skip'

        # Verificar cache
        cache_key = f"{source_lang}:{text}"
        if cache_key in self.cache:
            return self.cache[cache_key], 'cache'

        # Detectar idioma se não especificado
        if not source_lang:
            source_lang = self.detect_language(text)

        # Se já é português, pular
        if source_lang == 'pt':
            return None, 'skip'

        # Tentar MyMemory primeiro (mais confiável)
        time.sleep(self.rate_limit_delay)
        result = self.translate_mymemory(text, source_lang)
        if result:
            self.cache[cache_key] = result
            return result, 'mymemory'

        # Tentar Google Translate
        time.sleep(self.rate_limit_delay)
        result = self.translate_google_free(text, source_lang)
        if result:
            self.cache[cache_key] = result
            return result, 'google'

        return None, 'failed'


class FileProcessor:
    """Processa arquivos para tradução"""

    # Extensões suportadas
    SUPPORTED_EXTENSIONS = {
        '.py': 'python',
        '.js': 'javascript',
        '.vue': 'vue',
        '.html': 'html',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.md': 'markdown',
        '.txt': 'text',
        '.sh': 'shell',
    }

    # Padrões para extrair strings traduzíveis
    PATTERNS = {
        'python': [
            # Strings em aspas simples/duplas
            (r'(["\'])(?P<text>(?:(?!\1)[^\\]|\\.)*?)\1', 'string'),
            # Comentários
            (r'#\s*(?P<text>.+)$', 'comment'),
            # Docstrings
            (r'"""(?P<text>.*?)"""', 'docstring'),
            (r"'''(?P<text>.*?)'''", 'docstring'),
        ],
        'javascript': [
            (r'(["\'])(?P<text>(?:(?!\1)[^\\]|\\.)*?)\1', 'string'),
            (r'//\s*(?P<text>.+)$', 'comment'),
            (r'`(?P<text>.*?)`', 'template'),
        ],
        'vue': [
            (r'>(?P<text>[^<]+)</', 'element'),
            (r'(["\'])(?P<text>(?:(?!\1)[^\\]|\\.)*?)\1', 'string'),
            (r'<!--\s*(?P<text>.*?)\s*-->', 'comment'),
        ],
        'html': [
            (r'>(?P<text>[^<]+)</', 'element'),
            (r'(["\'])(?P<text>(?:(?!\1)[^\\]|\\.)*?)\1', 'attribute'),
            (r'<!--\s*(?P<text>.*?)\s*-->', 'comment'),
        ],
        'json': [
            (r'"(?P<text>[^"\\]*(?:\\.[^"\\]*)*)"', 'value'),
        ],
        'yaml': [
            (r':\s*["\']?(?P<text>[^"\'\n#]+)["\']?\s*(?:#.*)?$', 'value'),
            (r'#\s*(?P<text>.+)$', 'comment'),
        ],
        'markdown': [
            (r'^(?P<text>.+)$', 'line'),
        ],
        'text': [
            (r'^(?P<text>.+)$', 'line'),
        ],
        'shell': [
            (r'#\s*(?P<text>.+)$', 'comment'),
            (r'echo\s+["\'](?P<text>[^"\']+)["\']', 'echo'),
        ],
    }

    # Padrão para detectar chinês
    CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')

    # Strings que não devem ser traduzidas (nomes de variáveis, URLs, etc.)
    SKIP_PATTERNS = [
        r'^https?://',      # URLs
        r'^[a-zA-Z_][a-zA-Z0-9_]*$',  # Identificadores
        r'^\d+$',           # Apenas números
        r'^[\s\W]+$',       # Apenas espaços/símbolos
        r'^[a-zA-Z0-9_\-\.]+\.[a-zA-Z]+$',  # Nomes de arquivo
        r'^\{.*\}$',        # Placeholders
        r'^%[sdf]',         # Format strings
        r'^\\[nrt]',        # Escape sequences
    ]

    def __init__(self, db: TranslationDatabase, translator: TranslatorService):
        self.db = db
        self.translator = translator
        self.stats = {
            'files_processed': 0,
            'strings_found': 0,
            'strings_translated': 0,
            'strings_pending': 0,
            'strings_skipped': 0,
        }

    def should_skip(self, text: str) -> bool:
        """Verifica se a string deve ser pulada"""
        text = text.strip()

        if len(text) < 2:
            return True

        for pattern in self.SKIP_PATTERNS:
            if re.match(pattern, text):
                return True

        return False

    def has_chinese(self, text: str) -> bool:
        """Verifica se o texto contém caracteres chineses"""
        return bool(self.CHINESE_PATTERN.search(text))

    def extract_strings(self, content: str, file_type: str) -> List[Tuple[str, int, str, str]]:
        """
        Extrai strings traduzíveis do conteúdo

        Retorna: [(texto, linha, tipo, contexto)]
        """
        strings = []
        patterns = self.PATTERNS.get(file_type, self.PATTERNS['text'])

        lines = content.split('\n')

        for pattern, string_type in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
                text = match.group('text') if 'text' in match.groupdict() else match.group(0)

                if not text or self.should_skip(text):
                    continue

                # Encontrar número da linha
                pos = match.start()
                line_num = content[:pos].count('\n') + 1

                # Contexto (linha completa)
                if line_num <= len(lines):
                    context = lines[line_num - 1].strip()[:100]
                else:
                    context = ""

                # Verificar se contém chinês ou é inglês traduzível
                if self.has_chinese(text):
                    strings.append((text, line_num, string_type, context))
                elif len(text) > 10 and text[0].isupper():
                    # Frases em inglês (começam com maiúscula e são longas)
                    strings.append((text, line_num, string_type, context))

        return strings

    def process_file(self, file_path: str, dry_run: bool = False, use_auto_translate: bool = False) -> Tuple[str, List[dict]]:
        """
        Processa um arquivo e aplica traduções

        Retorna: (conteúdo_modificado, lista_de_mudanças)
        """
        ext = os.path.splitext(file_path)[1].lower()
        file_type = self.SUPPORTED_EXTENSIONS.get(ext, 'text')

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        original_content = content
        changes = []

        # Extrair strings
        strings = self.extract_strings(content, file_type)
        self.stats['strings_found'] += len(strings)

        for text, line_num, string_type, context in strings:
            # Buscar tradução existente
            translation = self.db.get_translation(text)

            if translation:
                # Aplicar tradução existente
                if not dry_run:
                    content = content.replace(text, translation)
                changes.append({
                    'original': text,
                    'translated': translation,
                    'line': line_num,
                    'type': string_type,
                    'source': 'database'
                })
                self.stats['strings_translated'] += 1
            elif use_auto_translate:
                # Tentar tradução automática
                source_lang = 'zh' if self.has_chinese(text) else 'en'
                translated, translator_name = self.translator.translate(text, source_lang)

                if translated and translator_name != 'failed':
                    # Adicionar ao banco de dados
                    entry = TranslationEntry(
                        original=text,
                        translated=translated,
                        source_lang=source_lang,
                        translator=translator_name,
                        file_path=file_path,
                        line_number=line_num,
                        context=context,
                        date_added=datetime.now().isoformat(),
                        verified=False
                    )
                    self.db.add_translation(entry)

                    if not dry_run:
                        content = content.replace(text, translated)

                    changes.append({
                        'original': text,
                        'translated': translated,
                        'line': line_num,
                        'type': string_type,
                        'source': translator_name
                    })
                    self.stats['strings_translated'] += 1
                    print(f"    [AUTO] {text[:30]}... -> {translated[:30]}...")
                else:
                    # Adicionar como pendente
                    hash_key = self.db.get_hash(text)
                    pending = PendingEntry(
                        original=text,
                        source_lang=source_lang,
                        file_path=file_path,
                        line_number=line_num,
                        context=context,
                        hash=hash_key,
                        date_found=datetime.now().isoformat(),
                        suggested_translation=""
                    )
                    self.db.add_pending(pending)
                    self.stats['strings_pending'] += 1
            else:
                # Adicionar como pendente
                source_lang = 'zh' if self.has_chinese(text) else 'en'
                hash_key = self.db.get_hash(text)
                pending = PendingEntry(
                    original=text,
                    source_lang=source_lang,
                    file_path=file_path,
                    line_number=line_num,
                    context=context,
                    hash=hash_key,
                    date_found=datetime.now().isoformat(),
                    suggested_translation=""
                )
                self.db.add_pending(pending)
                self.stats['strings_pending'] += 1

        self.stats['files_processed'] += 1

        return content, changes


class PatchTranslator:
    """Orquestrador principal do sistema de tradução"""

    def __init__(self, project_path: str, translations_file: str, pending_file: str):
        self.project_path = Path(project_path)
        self.db = TranslationDatabase(translations_file, pending_file)
        self.translator = TranslatorService()
        self.processor = FileProcessor(self.db, self.translator)

    def find_translatable_files(self) -> List[Path]:
        """Encontra todos os arquivos traduzíveis no projeto"""
        files = []

        for ext in FileProcessor.SUPPORTED_EXTENSIONS.keys():
            pattern = f"**/*{ext}"
            files.extend(self.project_path.glob(pattern))

        # Ordenar por prioridade (Python e Vue primeiro)
        priority = {'.py': 0, '.vue': 1, '.js': 2, '.html': 3, '.json': 4}
        files.sort(key=lambda f: (priority.get(f.suffix, 10), str(f)))

        return files

    def run(self, incremental: bool = True, dry_run: bool = False, use_auto_translate: bool = False):
        """Executa o processo de tradução"""
        print("\n" + "=" * 70)
        print("INICIANDO PROCESSO DE TRADUÇÃO")
        print("=" * 70)
        print(f"Projeto: {self.project_path}")
        print(f"Modo: {'Incremental' if incremental else 'Completo'}")
        print(f"Dry Run: {'Sim' if dry_run else 'Não'}")
        print(f"Tradução Automática: {'Sim' if use_auto_translate else 'Não'}")
        print("=" * 70 + "\n")

        files = self.find_translatable_files()
        print(f"Arquivos encontrados: {len(files)}\n")

        all_changes = []

        for file_path in files:
            rel_path = file_path.relative_to(self.project_path)

            # Verificar se o arquivo contém chinês
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                if not self.processor.has_chinese(content):
                    # Verificar se tem frases em inglês longas
                    if not re.search(r'[A-Z][a-z]{10,}', content):
                        continue
            except:
                continue

            print(f"Processando: {rel_path}")

            try:
                new_content, changes = self.processor.process_file(
                    str(file_path),
                    dry_run=dry_run,
                    use_auto_translate=use_auto_translate
                )

                if changes:
                    all_changes.append({
                        'file': str(rel_path),
                        'changes': changes
                    })

                    if not dry_run and new_content:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        print(f"  -> {len(changes)} traduções aplicadas")
                    else:
                        print(f"  -> {len(changes)} traduções encontradas (dry-run)")

            except Exception as e:
                print(f"  ERRO: {e}")
                continue

        # Salvar banco de dados
        if not dry_run:
            self.db.save()

        # Mostrar estatísticas
        self.show_stats(all_changes)

        return all_changes

    def show_stats(self, changes: List[dict]):
        """Mostra estatísticas do processo"""
        print("\n" + "=" * 70)
        print("ESTATÍSTICAS")
        print("=" * 70)
        print(f"Arquivos processados:    {self.processor.stats['files_processed']}")
        print(f"Strings encontradas:     {self.processor.stats['strings_found']}")
        print(f"Strings traduzidas:      {self.processor.stats['strings_translated']}")
        print(f"Strings pendentes:       {self.processor.stats['strings_pending']}")
        print(f"Total no banco:          {len(self.db.translations)}")
        print(f"Total pendentes:         {len(self.db.pending)}")
        print("=" * 70 + "\n")

        if self.db.pending:
            print("STRINGS PENDENTES DE TRADUÇÃO:")
            print("-" * 70)
            for i, (hash_key, entry) in enumerate(list(self.db.pending.items())[:10]):
                print(f"  [{entry.source_lang}] {entry.original[:50]}...")
                print(f"      Arquivo: {entry.file_path}:{entry.line_number}")
            if len(self.db.pending) > 10:
                print(f"  ... e mais {len(self.db.pending) - 10} strings")
            print("-" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description='Tradutor de Chinês/Inglês para Português do Brasil'
    )
    parser.add_argument('--project', required=True, help='Caminho do projeto')
    parser.add_argument('--translations', required=True, help='Arquivo de traduções')
    parser.add_argument('--pending', required=True, help='Arquivo de pendentes')
    parser.add_argument('--incremental', action='store_true', help='Modo incremental')
    parser.add_argument('--dry-run', action='store_true', help='Apenas simula')
    parser.add_argument('--use-llm', action='store_true', help='Usar LLM para tradução')
    parser.add_argument('--auto-translate', action='store_true', help='Tradução automática')

    args = parser.parse_args()

    # Se use-llm foi especificado, habilitar tradução automática
    use_auto = args.auto_translate or args.use_llm

    translator = PatchTranslator(
        project_path=args.project,
        translations_file=args.translations,
        pending_file=args.pending
    )

    translator.run(
        incremental=args.incremental,
        dry_run=args.dry_run,
        use_auto_translate=use_auto
    )


if __name__ == '__main__':
    main()
