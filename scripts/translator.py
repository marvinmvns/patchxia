#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XIAOZHI ESP32 SERVER - Tradutor de Chinês/Inglês para Português do Brasil
Versão 2.0 - Corrigido para substituição precisa

Melhorias:
- Extração de strings mais precisa (não captura blocos grandes)
- Substituição posicional (de trás para frente) para não quebrar índices
- Preserva aspas e contexto original
- Hashes MD5 corretos
"""

import argparse
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import ssl

ssl._create_default_https_context = ssl._create_unverified_context


@dataclass
class TranslationEntry:
    original: str
    translated: str
    source_lang: str
    translator: str
    file_path: str
    line_number: int
    context: str
    date_added: str
    verified: bool = False


@dataclass
class PendingEntry:
    original: str
    source_lang: str
    file_path: str
    line_number: int
    context: str
    hash: str
    date_found: str
    suggested_translation: str = ""


class TranslationDatabase:
    def __init__(self, translations_file: str, pending_file: str):
        self.translations_file = translations_file
        self.pending_file = pending_file
        self.translations: Dict[str, TranslationEntry] = {}
        self.pending: Dict[str, PendingEntry] = {}
        self.load()

    def load(self):
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
        os.makedirs(os.path.dirname(self.translations_file), exist_ok=True)
        with open(self.translations_file, 'w', encoding='utf-8') as f:
            data = {
                'version': '2.0.0',
                'last_updated': datetime.now().isoformat(),
                'total_translations': len(self.translations),
                'translations': {k: asdict(v) for k, v in self.translations.items()}
            }
            json.dump(data, f, ensure_ascii=False, indent=2)

        with open(self.pending_file, 'w', encoding='utf-8') as f:
            data = {
                'version': '2.0.0',
                'last_updated': datetime.now().isoformat(),
                'total_pending': len(self.pending),
                'pending': {k: asdict(v) for k, v in self.pending.items()}
            }
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_hash(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

    def get_translation(self, text: str) -> Optional[str]:
        hash_key = self.get_hash(text)
        if hash_key in self.translations:
            return self.translations[hash_key].translated
        return None

    def add_translation(self, entry: TranslationEntry):
        hash_key = self.get_hash(entry.original)
        self.translations[hash_key] = entry
        if hash_key in self.pending:
            del self.pending[hash_key]

    def add_pending(self, entry: PendingEntry):
        if entry.hash not in self.translations and entry.hash not in self.pending:
            self.pending[entry.hash] = entry


class TranslatorService:
    def __init__(self):
        self.cache: Dict[str, str] = {}
        self.rate_limit_delay = 0.5

    def translate_mymemory(self, text: str, source_lang: str) -> Optional[str]:
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
        except Exception:
            pass
        return None

    def translate_google_free(self, text: str, source_lang: str) -> Optional[str]:
        try:
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
        except Exception:
            pass
        return None

    def translate(self, text: str, source_lang: str) -> Tuple[Optional[str], str]:
        if not text or len(text.strip()) < 2:
            return None, 'skip'

        cache_key = f"{source_lang}:{text}"
        if cache_key in self.cache:
            return self.cache[cache_key], 'cache'

        time.sleep(self.rate_limit_delay)
        result = self.translate_mymemory(text, source_lang)
        if result:
            self.cache[cache_key] = result
            return result, 'mymemory'

        time.sleep(self.rate_limit_delay)
        result = self.translate_google_free(text, source_lang)
        if result:
            self.cache[cache_key] = result
            return result, 'google'

        return None, 'failed'


class FileProcessor:
    # Padrão para detectar chinês
    CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]+')

    # Strings que devem ser ignoradas
    SKIP_PATTERNS = [
        r'^https?://',
        r'^[a-zA-Z_][a-zA-Z0-9_]*$',
        r'^\d+$',
        r'^[\s\W]+$',
        r'^[a-zA-Z0-9_\-\.]+\.[a-zA-Z]+$',
    ]

    def __init__(self, db: TranslationDatabase, translator: TranslatorService):
        self.db = db
        self.translator = translator
        self.stats = {
            'files_processed': 0,
            'strings_found': 0,
            'strings_translated': 0,
            'strings_pending': 0,
        }

    def should_skip(self, text: str) -> bool:
        text = text.strip()
        if len(text) < 1 or len(text) > 5000:
            return True
        for pattern in self.SKIP_PATTERNS:
            if re.match(pattern, text):
                return True
        return False

    def has_chinese(self, text: str) -> bool:
        return bool(self.CHINESE_PATTERN.search(text))

    def find_chinese_strings(self, content: str) -> List[Tuple[int, int, str]]:
        """
        Encontra strings em chinês no conteúdo.
        Retorna lista de (start, end, text) ordenada por posição.
        """
        matches = []

        # Padrões para capturar strings com chinês
        patterns = [
            # Triple quotes (multiline) - Corrigido para não "vazar" entre docstrings
            (r'"""((?:(?!""").)*?[\u4e00-\u9fff\u3400-\u4dbf](?:(?!""").)*?)"""', 1),
            (r"'''((?:(?!''').)*?[\u4e00-\u9fff\u3400-\u4dbf](?:(?!''').)*?)'''", 1),
            # Single quoted strings (no newlines)
            (r'"([^"\n]*[\u4e00-\u9fff\u3400-\u4dbf][^"\n]*)"', 1),
            (r"'([^'\n]*[\u4e00-\u9fff\u3400-\u4dbf][^'\n]*)'", 1),
            # Backticks (template literals JS)
            (r'`([^`]*[\u4e00-\u9fff\u3400-\u4dbf][^`]*)`', 1),
            # Texto entre tags HTML/Vue
            (r'>([^<\n]*[\u4e00-\u9fff\u3400-\u4dbf][^<\n]*)<', 1),
            # Comentários Python/Shell com chinês
            (r'#\s*([^\n]*[\u4e00-\u9fff\u3400-\u4dbf][^\n]*)', 1),
            # Comentários HTML
            (r'<!--\s*((?:(?!-->).)*[\u4e00-\u9fff\u3400-\u4dbf](?:(?!-->).)*)\s*-->', 1),
            # YAML: valores sem aspas em itens de lista ("  - valor chinês")
            (r'(?:^|\n)([ \t]*-[ \t]+)([\u4e00-\u9fff\u3400-\u4dbf][^\n#]*)', 2),
            # YAML: valores sem aspas em chaves ("  chave: valor chinês")
            # Apenas captura o valor (grupo 2), não a chave
            (r'(?:^|\n)([ \t]*[\w._-]+:[ \t]+)([\u4e00-\u9fff\u3400-\u4dbf][^\n#]*)', 2),
            # Shell: echo/whiptail com strings chinesas não-entoquotadas
            (r'(?:echo|msgbox)\s+"([^"]*[\u4e00-\u9fff\u3400-\u4dbf][^"]*)"', 1),

            # === NOVOS PADRÕES ===

            # SQL: comentários de linha única -- comentário
            (r'--\s*([^\n]*[\u4e00-\u9fff\u3400-\u4dbf][^\n]*)', 1),
            # SQL: comentários de bloco /* comentário */
            (r'/\*\s*((?:(?!\*/).)*[\u4e00-\u9fff\u3400-\u4dbf](?:(?!\*/).)*)\s*\*/', 1),
            # SQL: valores em INSERT/UPDATE (strings entre aspas simples)
            # já coberto pelo padrão de aspas simples acima

            # TypeScript/JavaScript: comentários de linha única // comentário
            (r'//\s*([^\n]*[\u4e00-\u9fff\u3400-\u4dbf][^\n]*)', 1),

            # XML: comentários <!-- comentário --> (já coberto por HTML acima)
            # XML: atributos com chinês (ex: label="文本")
            # já coberto pelos padrões de aspas

            # CSS/SCSS: comentários /* comentário */ (já coberto por SQL block comments)
            # CSS: comentários de linha // em SCSS
            # já coberto por TypeScript comments

            # Dockerfile: comentários # (já coberto por Python/Shell)
        ]

        for pattern, group in patterns:
            for match in re.finditer(pattern, content):
                text = match.group(group).strip()
                if not self.should_skip(text) and self.has_chinese(text):
                    start = match.start(group)
                    end = match.end(group)
                    matches.append((start, end, text))

        # Remover duplicatas mantendo primeira ocorrência
        seen_texts = set()
        candidates = []
        for start, end, text in sorted(matches, key=lambda x: x[0]):
            if text not in seen_texts:
                seen_texts.add(text)
                candidates.append((start, end, text))

        # Filtrar sobreposições (manter o match mais externo/maior)
        # Ordenar por início
        candidates.sort(key=lambda x: x[0])
        
        unique_matches = []
        last_end = -1
        
        for start, end, text in candidates:
            # Se o match atual começa depois do último terminar, não há sobreposição
            if start >= last_end:
                unique_matches.append((start, end, text))
                last_end = end
            else:
                # Há sobreposição. Como ordenamos por início, e strings aninhadas começam depois (ou igual),
                # o 'candidiate' atual é interno ou sobreposto ao anterior.
                # Mantemos o 'last' (o anterior) que é o externo.
                # Nota: Em regex de strings, overlaps parciais não acontecem, apenas aninhamento.
                # O regex externo captura "...", o interno captura '...' dentro dele.
                # O externo começa antes (ou igual) e termina depois (ou igual).
                # Então descartamos o atual.
                continue

        return unique_matches

    def verify_interpolation(self, original: str, translated: str) -> bool:
        """Verifica se a interpolação de variáveis (f-strings) foi preservada corretamente."""
        # Regex simplificado para capturar conteúdo entre {} que não seja {{ ou }}
        # Nota: Não suporta aninhamento complexo, mas serve para a maioria dos casos simples
        pattern = re.compile(r'(?<!{){([^{}]+)}(?!})')
        
        orig_vars = sorted([m.group(1).replace(" ", "") for m in pattern.finditer(original)])
        trans_vars = sorted([m.group(1).replace(" ", "") for m in pattern.finditer(translated)])
        
        return orig_vars == trans_vars

    def process_file(self, file_path: str, dry_run: bool = False, use_auto_translate: bool = False) -> Tuple[str, List[dict]]:
        """Processa um arquivo e aplica traduções de forma segura."""
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        changes = []
        lines = content.split('\n')

        # Encontrar strings chinesas
        matches = self.find_chinese_strings(content)
        self.stats['strings_found'] += len(matches)

        # Lista de substituições a fazer
        replacements = []

        for start, end, text in matches:
            line_num = content[:start].count('\n') + 1
            context = lines[line_num - 1].strip()[:80] if line_num <= len(lines) else ""

            # Verificar contexto das aspas para escapar corretamente
            quote_char = None
            if start > 0:
                char_before = content[start-1]
                if char_before in ['"', "'", '`']:
                    quote_char = char_before
                elif start >= 3 and content[start-3:start] in ['"""', "'''"]:
                    quote_char = content[start-3:start]

            # Buscar tradução existente
            translation = self.db.get_translation(text)

            if translation:
                # Verificar se interpolação foi preservada
                if not self.verify_interpolation(text, translation):
                    print(f"    [WARN] Ignorando tradução insegura (interpolação quebrada): {text[:30]}...")
                    self._add_pending(text, file_path, line_num, context)
                    continue

                # Escapar aspas na tradução se necessário
                final_translation = translation
                if quote_char:
                    if len(quote_char) == 1: # Aspas simples/duplas normais
                        final_translation = final_translation.replace(quote_char, f"\\{quote_char}")
                    # Para triple quotes, geralmente não precisa escapar a menos que contenha a própria triple quote

                replacements.append((start, end, text, final_translation))
                changes.append({
                    'original': text,
                    'translated': final_translation,
                    'line': line_num,
                    'source': 'database'
                })
                self.stats['strings_translated'] += 1
            elif use_auto_translate:
                translated, translator_name = self.translator.translate(text, 'zh')

                if translated and translator_name != 'failed':
                    # Verificar se interpolação foi preservada
                    if not self.verify_interpolation(text, translated):
                        print(f"    [WARN] Ignorando tradução insegura (interpolação quebrada): {text[:30]}...")
                        self._add_pending(text, file_path, line_num, context)
                        continue

                    # Escapar aspas na tradução automática também
                    final_translated = translated
                    if quote_char and len(quote_char) == 1:
                        final_translated = final_translated.replace(quote_char, f"\\{quote_char}")

                    entry = TranslationEntry(
                        original=text,
                        translated=translated, # Salva no banco SEM escape
                        source_lang='zh',
                        translator=translator_name,
                        file_path=file_path,
                        line_number=line_num,
                        context=context,
                        date_added=datetime.now().isoformat(),
                        verified=False
                    )
                    self.db.add_translation(entry)
                    replacements.append((start, end, text, final_translated))
                    changes.append({
                        'original': text,
                        'translated': final_translated,
                        'line': line_num,
                        'source': translator_name
                    })
                    self.stats['strings_translated'] += 1
                    print(f"    [AUTO] {text[:30]}... -> {final_translated[:30]}...")
                else:
                    self._add_pending(text, file_path, line_num, context)
            else:
                self._add_pending(text, file_path, line_num, context)

        # Aplicar substituições de trás para frente (preserva índices)
        if not dry_run and replacements:
            replacements.sort(key=lambda x: x[0], reverse=True)
            for start, end, original, translated in replacements:
                content = content[:start] + translated + content[end:]

        self.stats['files_processed'] += 1
        return content, changes

    def _add_pending(self, text: str, file_path: str, line_num: int, context: str):
        hash_key = self.db.get_hash(text)
        pending = PendingEntry(
            original=text,
            source_lang='zh',
            file_path=file_path,
            line_number=line_num,
            context=context,
            hash=hash_key,
            date_found=datetime.now().isoformat(),
            suggested_translation=""
        )
        self.db.add_pending(pending)
        self.stats['strings_pending'] += 1


class PatchTranslator:
    def __init__(self, project_path: str, translations_file: str, pending_file: str):
        self.project_path = Path(project_path)
        self.db = TranslationDatabase(translations_file, pending_file)
        self.translator = TranslatorService()
        self.processor = FileProcessor(self.db, self.translator)

    def find_translatable_files(self) -> List[Path]:
        extensions = [
            '.py', '.js', '.vue', '.html', '.json', '.yaml', '.yml', '.sh', '.md', '.txt',
            # Novos tipos adicionados
            '.ts', '.tsx', '.jsx',  # TypeScript/React
            '.sql',                  # SQL migrations
            '.xml',                  # MyBatis mappers
            '.scss', '.css',         # Stylesheets
        ]
        # Diretórios a ignorar completamente
        ignore_dirs = {'node_modules', '.git', '__pycache__', 'mysql', '.venv', 'venv', 'dist', 'build'}
        files = []
        for ext in extensions:
            for f in self.project_path.glob(f"**/*{ext}"):
                # Filtrar diretórios ignorados no caminho
                if any(ign in f.parts for ign in ignore_dirs):
                    continue
                files.append(f)

        # Adicionar Dockerfiles (sem extensão)
        for f in self.project_path.glob("**/Dockerfile*"):
            if any(ign in f.parts for ign in ignore_dirs):
                continue
            files.append(f)

        return sorted(files, key=lambda f: str(f))

    def run(self, incremental: bool = True, dry_run: bool = False, use_auto_translate: bool = False):
        print("\n" + "=" * 70)
        print("SISTEMA DE TRADUÇÃO PT-BR v2.0")
        print("=" * 70)
        print(f"Projeto: {self.project_path}")
        print(f"Dry Run: {'Sim' if dry_run else 'Não'}")
        print(f"Tradução Automática: {'Sim' if use_auto_translate else 'Não'}")
        print(f"Traduções no banco: {len(self.db.translations)}")
        print("=" * 70 + "\n")

        files = self.find_translatable_files()
        print(f"Arquivos encontrados: {len(files)}\n")

        for file_path in files:
            rel_path = file_path.relative_to(self.project_path)

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                if not self.processor.has_chinese(content):
                    continue
            except Exception:
                continue

            print(f"Processando: {rel_path}")

            try:
                new_content, changes = self.processor.process_file(
                    str(file_path),
                    dry_run=dry_run,
                    use_auto_translate=use_auto_translate
                )

                if changes:
                    if not dry_run:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                        print(f"  -> {len(changes)} traduções aplicadas")
                    else:
                        print(f"  -> {len(changes)} traduções encontradas (dry-run)")

            except Exception as e:
                print(f"  ERRO: {e}")

        if not dry_run:
            self.db.save()

        self._show_stats()

    def _show_stats(self):
        print("\n" + "=" * 70)
        print("ESTATÍSTICAS")
        print("=" * 70)
        print(f"Arquivos processados:    {self.processor.stats['files_processed']}")
        print(f"Strings encontradas:     {self.processor.stats['strings_found']}")
        print(f"Strings traduzidas:      {self.processor.stats['strings_translated']}")
        print(f"Strings pendentes:       {self.processor.stats['strings_pending']}")
        print(f"Total no banco:          {len(self.db.translations)}")
        print(f"Total pendentes:         {len(self.db.pending)}")
        print("=" * 70)

        if self.db.pending:
            print("\nSTRINGS PENDENTES (primeiras 10):")
            print("-" * 70)
            for i, (_, entry) in enumerate(list(self.db.pending.items())[:10]):
                print(f"  {entry.original[:50]}")
            if len(self.db.pending) > 10:
                print(f"  ... e mais {len(self.db.pending) - 10}")
            print("-" * 70)


def main():
    parser = argparse.ArgumentParser(description='Tradutor CN/EN -> PT-BR v2.0')
    parser.add_argument('--project', required=True)
    parser.add_argument('--translations', required=True)
    parser.add_argument('--pending', required=True)
    parser.add_argument('--incremental', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--use-llm', action='store_true')
    parser.add_argument('--auto-translate', action='store_true')

    args = parser.parse_args()
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
