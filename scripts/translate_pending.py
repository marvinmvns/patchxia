#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utilitário para traduzir strings pendentes automaticamente.

Este script:
1. Lê o arquivo pending.json
2. Traduz cada string usando APIs gratuitas
3. Move as traduções para translations.json
4. Permite revisão antes de salvar

Uso:
    python translate_pending.py                    # Traduz todas as pendentes
    python translate_pending.py --limit 10         # Traduz apenas 10
    python translate_pending.py --review           # Modo revisão interativo
    python translate_pending.py --export           # Exporta para CSV para revisão manual
"""

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Diretórios
SCRIPT_DIR = Path(__file__).parent
TRANSLATIONS_DIR = SCRIPT_DIR.parent / "translations"
TRANSLATIONS_FILE = TRANSLATIONS_DIR / "translations.json"
PENDING_FILE = TRANSLATIONS_DIR / "pending.json"


def get_hash(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]


def load_json(filepath: Path) -> dict:
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_json(filepath: Path, data: dict):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def translate_mymemory(text: str, source_lang: str = 'zh') -> str:
    """Traduz usando MyMemory API (gratuito)"""
    try:
        langpair = f"{source_lang}|pt-BR"
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair={langpair}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('responseStatus') == 200:
                translated = data.get('responseData', {}).get('translatedText', '')
                if translated and translated.lower() != text.lower():
                    return translated
            elif data.get('responseStatus') == 429:
                return "ERR_429"
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return "ERR_429"
        print(f"  [MyMemory HTTP erro: {e}]")
    except Exception as e:
        print(f"  [MyMemory erro: {e}]")
    return ""


def translate_google(text: str, source_lang: str = 'zh') -> str:
    """Traduz usando Google Translate (gratuito via web)"""
    try:
        sl = 'zh-CN' if source_lang == 'zh' else source_lang
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl=pt&dt=t&q={urllib.parse.quote(text)}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data and data[0]:
                translated = ''.join(part[0] for part in data[0] if part[0])
                if translated:
                    return translated
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return "ERR_429"
        try:
            body = e.read().decode('utf-8', errors='replace')
        except Exception:
            body = ''
        print(f"  [Google HTTP erro: {e.code} — {body[:200]}]")
    except Exception as e:
        print(f"  [Google erro: {e}]")
    return ""


# Circuit breaker for MyMemory
mymemory_enabled = False  # Desabilitado — usar apenas Google
mymemory_fail_count = 0

def translate_text(text: str, source_lang: str = 'zh') -> tuple:
    """Tenta traduzir usando múltiplos serviços com fallback rápido (Fail-Fast)"""
    global mymemory_enabled, mymemory_fail_count
    
    # MyMemory Strategy: Try if enabled
    if mymemory_enabled:
        time.sleep(0.1) # Minimal sleep
        result = translate_mymemory(text, source_lang)
        
        if result and result != "ERR_429":
            return result, 'mymemory'
            
        if result == "ERR_429":
            # Count failures
            mymemory_fail_count += 1
            if mymemory_fail_count >= 5:
                print(f"  [SISTEMA] MyMemory desativado permanentemente (Muitos 429).")
                mymemory_enabled = False
    
    # Google Strategy: Direct attempt
    time.sleep(0.35)
    result = translate_google(text, source_lang)
    
    if result and result != "ERR_429":
        return result, 'google'
    
    # Fail fast if Google also denies
    if result == "ERR_429":
        # Don't sleep, just return error so we move to next
        return "", 'failed_429'

    return "", 'failed'


import threading

# Global rate limit tracker
rate_limit_lock = threading.Lock()
consecutive_429_count = 0

MAX_TRANSLATE_LEN = 500  # limite seguro para o endpoint gratuito do Google

def translate_worker(args):
    global consecutive_429_count
    hash_key, entry, review = args
    original = entry['original']
    source_lang = entry.get('source_lang', 'zh')

    if len(original) > MAX_TRANSLATE_LEN:
        print(f"  [PULAR] hash={hash_key} — string com {len(original)} chars (máximo {MAX_TRANSLATE_LEN}). Use --export para tradução manual.")
        return hash_key, "ERR_TOO_LONG"

    translated, service = translate_text(original, source_lang)
    
    if translated and translated != "ERR_429" and service != 'failed_429':
        with rate_limit_lock:
             consecutive_429_count = 0 # Reset on success
             
        return hash_key, {
            'original': original,
            'translated': translated,
            'source_lang': source_lang,
            'translator': service,
            'file_path': entry.get('file_path', 'auto'),
            'line_number': entry.get('line_number', 0),
            'context': entry.get('context', ''),
            'date_added': datetime.now().isoformat(),
            'verified': False
        }
    elif service == 'failed_429':
        # Just fail silently/quickly
        return hash_key, "ERR_429"
        
    return None

from concurrent.futures import ThreadPoolExecutor, as_completed

def translate_pending(limit: int = None, review: bool = False):
    """Traduz strings pendentes com concorrência"""
    global consecutive_429_count

    # Carregar arquivos
    translations_data = load_json(TRANSLATIONS_FILE)
    pending_data = load_json(PENDING_FILE)

    translations = translations_data.get('translations', {})
    pending = pending_data.get('pending', {})

    if not pending:
        print("Nenhuma string pendente para traduzir!")
        return

    print(f"\n{'='*60}")
    print(f"TRADUÇÃO AUTOMÁTICA DE STRINGS PENDENTES (CONCORRENTE)")
    print(f"{'='*60}")
    print(f"Pendentes: {len(pending)}")
    print(f"Limite: {limit or 'Todas'}")
    print(f"Modo revisão: {'Sim' if review else 'Não'}")
    print(f"{'='*60}\n")

    items = list(pending.items())
    if limit:
        items = items[:limit]

    translated_count = 0
    failed_count = 0
    skipped_too_long = 0
    new_translations = {}
    
    # Use ThreadPoolExecutor
    max_workers = 2  # Google-only: 2 workers para evitar 429
    print(f"Iniciando tradução com {max_workers} threads...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Prepare args
        future_to_item = {
            executor.submit(translate_worker, (hash_key, entry, review)): hash_key 
            for hash_key, entry in items
        }
        
        total = len(items)
        done = 0
        
        for future in as_completed(future_to_item):
            done += 1
            result = future.result()
            
            if result:
                hash_key, trans_entry = result
                
                # Check for error returns
                if trans_entry == "ERR_429":
                    failed_count += 1
                    if done % 10 == 0:
                        print(f"[{done}/{total}] ⚠️  Rate Limit (429) - Pausando...")
                        time.sleep(5)
                    continue

                if trans_entry == "ERR_TOO_LONG":
                    skipped_too_long += 1
                    continue

                new_translations[hash_key] = trans_entry
                translated_count += 1
                
                if done % 10 == 0:
                    print(f"[{done}/{total}] Traduzido: {trans_entry['translated'][:30]}...")
                    
                    # SAVE PROGRESS INCREMENTALLY
                    try:
                        # Update main dicts
                        translations.update(new_translations)
                        for k in new_translations:
                            if k in pending:
                                del pending[k]
                        
                        # Save
                        translations_data['translations'] = translations
                        translations_data['total_translations'] = len(translations)
                        translations_data['last_updated'] = datetime.now().isoformat()
                        save_json(TRANSLATIONS_FILE, translations_data)

                        pending_data['pending'] = pending
                        pending_data['total_pending'] = len(pending)
                        pending_data['last_updated'] = datetime.now().isoformat()
                        save_json(PENDING_FILE, pending_data)
                        
                        # Clear processed dict to avoid processing again
                        new_translations = {}
                    except Exception as e:
                        print(f"Erro ao salvar progresso parcial: {e}")

            else:
                failed_count += 1
                if done % 10 == 0:
                    print(f"[{done}/{total}] Falha ou vazio")

    # Final Save (for any remainders)
    if new_translations:
        translations.update(new_translations)
        for k in new_translations:
            if k in pending:
                del pending[k]

        translations_data['translations'] = translations
        translations_data['total_translations'] = len(translations)
        translations_data['last_updated'] = datetime.now().isoformat()
        save_json(TRANSLATIONS_FILE, translations_data)

        pending_data['pending'] = pending
        pending_data['total_pending'] = len(pending)
        pending_data['last_updated'] = datetime.now().isoformat()
        save_json(PENDING_FILE, pending_data)

    print(f"\n{'='*60}")
    print(f"RESULTADO FINAL")
    print(f"{'='*60}")
    print(f"Traduzidas: {translated_count}")
    print(f"Falharam:   {failed_count}")
    print(f"Puladas (muito longas): {skipped_too_long}")
    print(f"Total no banco: {len(translations)}")
    print(f"Pendentes restantes: {len(pending)}")
    print(f"{'='*60}\n")



def export_pending_csv():
    """Exporta pendentes para CSV para revisão manual"""
    pending_data = load_json(PENDING_FILE)
    pending = pending_data.get('pending', {})

    if not pending:
        print("Nenhuma string pendente!")
        return

    csv_file = TRANSLATIONS_DIR / "pending_review.csv"

    with open(csv_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['hash', 'original', 'translated', 'context', 'file_path'])

        for hash_key, entry in pending.items():
            writer.writerow([
                hash_key,
                entry['original'],
                '',  # Campo para tradução manual
                entry.get('context', ''),
                entry.get('file_path', '')
            ])

    print(f"\nExportado para: {csv_file}")
    print(f"Total de strings: {len(pending)}")
    print("\nPreencha a coluna 'translated' e use --import para importar.")


def import_from_csv():
    """Importa traduções de um CSV"""
    csv_file = TRANSLATIONS_DIR / "pending_review.csv"

    if not csv_file.exists():
        print(f"Arquivo não encontrado: {csv_file}")
        return

    translations_data = load_json(TRANSLATIONS_FILE)
    pending_data = load_json(PENDING_FILE)

    translations = translations_data.get('translations', {})
    pending = pending_data.get('pending', {})

    imported = 0

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            if row['translated'].strip():
                hash_key = row['hash']

                translations[hash_key] = {
                    'original': row['original'],
                    'translated': row['translated'],
                    'source_lang': 'zh',
                    'translator': 'manual_csv',
                    'file_path': row.get('file_path', ''),
                    'line_number': 0,
                    'context': row.get('context', ''),
                    'date_added': datetime.now().isoformat(),
                    'verified': True
                }

                if hash_key in pending:
                    del pending[hash_key]

                imported += 1

    # Salvar
    translations_data['translations'] = translations
    translations_data['total_translations'] = len(translations)
    translations_data['last_updated'] = datetime.now().isoformat()
    save_json(TRANSLATIONS_FILE, translations_data)

    pending_data['pending'] = pending
    pending_data['total_pending'] = len(pending)
    pending_data['last_updated'] = datetime.now().isoformat()
    save_json(PENDING_FILE, pending_data)

    print(f"\nImportadas: {imported} traduções")
    print(f"Total no banco: {len(translations)}")
    print(f"Pendentes restantes: {len(pending)}")


def show_stats():
    """Mostra estatísticas"""
    translations_data = load_json(TRANSLATIONS_FILE)
    pending_data = load_json(PENDING_FILE)

    translations = translations_data.get('translations', {})
    pending = pending_data.get('pending', {})

    print(f"\n{'='*60}")
    print(f"ESTATÍSTICAS DO BANCO DE TRADUÇÕES")
    print(f"{'='*60}")
    print(f"Traduções verificadas: {sum(1 for t in translations.values() if t.get('verified'))}")
    print(f"Traduções automáticas: {sum(1 for t in translations.values() if not t.get('verified'))}")
    print(f"Total de traduções: {len(translations)}")
    print(f"Strings pendentes: {len(pending)}")
    print(f"{'='*60}\n")

    # Mostrar algumas pendentes
    if pending:
        print("Exemplos de strings pendentes:")
        for i, (_, entry) in enumerate(list(pending.items())[:5]):
            print(f"  - {entry['original'][:60]}")
        if len(pending) > 5:
            print(f"  ... e mais {len(pending) - 5}")


def main():
    parser = argparse.ArgumentParser(description='Traduzir strings pendentes')
    parser.add_argument('--limit', type=int, help='Limitar número de traduções')
    parser.add_argument('--review', action='store_true', help='Modo revisão interativo')
    parser.add_argument('--export', action='store_true', help='Exportar para CSV')
    parser.add_argument('--import-csv', action='store_true', help='Importar de CSV')
    parser.add_argument('--stats', action='store_true', help='Mostrar estatísticas')

    args = parser.parse_args()

    if args.export:
        export_pending_csv()
    elif args.import_csv:
        import_from_csv()
    elif args.stats:
        show_stats()
    else:
        translate_pending(limit=args.limit, review=args.review)


if __name__ == '__main__':
    main()
