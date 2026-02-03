#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplica patches de tradução nos assets JS compilados do container web.

O frontend Vue usa i18n ($t()) para maioria das strings, mas algumas são
hardcoded diretamente no bundle webpack. Este script encontra essas strings
chinesas nos arquivos JS compilados dentro do container nginx e as traduz
em-place, sem recompilar o frontend.

Após docker pull de nova imagem, os patches precisam ser reaplicados.

Uso:
    python3 scripts/patch_web_assets.py              # Aplica com API
    python3 scripts/patch_web_assets.py --dry-run    # Mostra sem aplicar
    python3 scripts/patch_web_assets.py --no-api     # Só banco local
"""

import subprocess
import json
import re
import hashlib
import time
import os
import tempfile
import argparse
import ssl
import urllib.parse
import urllib.request
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

ssl._create_default_https_context = ssl._create_unverified_context

# ─── Caminhos ────────────────────────────────────────────────
SCRIPT_DIR        = Path(__file__).parent
PATCH_ROOT        = SCRIPT_DIR.parent
TRANSLATIONS_FILE = PATCH_ROOT / "translations" / "translations.json"
PENDING_FILE      = PATCH_ROOT / "translations" / "pending.json"

# ─── Docker ──────────────────────────────────────────────────
WEB_CONTAINER = "xiaozhi-esp32-server-web"
NGINX_ROOT    = "/usr/share/nginx/html"

CHINESE = re.compile(r'[\u4e00-\u9fff]')

# Regex para strings em aspas duplas ou simples que contêm chinês.
# Trata escapes básicos (\") dentro da string.
DQUOTE_CHINESE = re.compile(r'"((?:[^"\\]|\\.)*?[\u4e00-\u9fff](?:[^"\\]|\\.)*?)"')
SQUOTE_CHINESE = re.compile(r"'((?:[^'\\]|\\.)*?[\u4e00-\u9fff](?:[^'\\]|\\.)*?)'")

# Strings que devem ser ignoradas mesmo contendo chinês
SKIP_RE = [
    re.compile(r'^https?://'),                          # URLs
    re.compile(r'^[\w./\-]+\.\w+$'),                    # paths como arquivo.ext
    re.compile(r'^\d+$'),                               # números
    re.compile(r'[\u4e00-\u9fff].*[=;{}\[\]<>()]'),     # fragmentos de código
    re.compile(r'^\\u[0-9a-fA-F]{4}'),                  # escape unicode literal
]


def get_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


# ─── Docker helpers ──────────────────────────────────────────

def container_alive(name: str) -> bool:
    r = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", name],
        capture_output=True, text=True
    )
    return r.stdout.strip() == "true"


def docker_read(container: str, path: str) -> str:
    """Lê arquivo do container."""
    r = subprocess.run(
        ["docker", "exec", container, "cat", path],
        capture_output=True, text=True, timeout=60
    )
    return r.stdout


def docker_cp(local_path: str, container: str, remote_path: str):
    """Copia arquivo local para dentro do container."""
    subprocess.run(
        ["docker", "cp", local_path, f"{container}:{remote_path}"],
        capture_output=True, timeout=30
    )


def find_js_files() -> List[str]:
    """Retorna JS files no container que contêm chinês.
    Filtragem feita no host após leitura — grep com Unicode não funciona
    de forma confiável dentro dos containers Alpine."""
    if not container_alive(WEB_CONTAINER):
        return []
    r = subprocess.run(
        ["docker", "exec", WEB_CONTAINER, "bash", "-c",
         f"find {NGINX_ROOT} -name '*.js' -type f"],
        capture_output=True, text=True, timeout=15
    )
    all_js = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]

    # Filtrar pelo host: lê cada JS e verifica chinês com regex Python
    with_chinese = []
    for fpath in all_js:
        content = docker_read(WEB_CONTAINER, fpath)
        if content and CHINESE.search(content):
            with_chinese.append(fpath)
    return with_chinese


# ─── Tradução via API ────────────────────────────────────────

def translate_mymemory(text: str) -> Optional[str]:
    try:
        url = (f"https://api.mymemory.translated.net/get"
               f"?q={urllib.parse.quote(text)}&langpair=zh|pt-BR")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("responseStatus") == 200:
                t = data.get("responseData", {}).get("translatedText", "")
                return t if t and t.lower() != text.lower() else None
    except Exception:
        pass
    return None


def translate_google(text: str) -> Optional[str]:
    try:
        url = (f"https://translate.googleapis.com/translate_a/single"
               f"?client=gtx&sl=zh-CN&tl=pt&dt=t&q={urllib.parse.quote(text)}")
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and data[0]:
                return "".join(p[0] for p in data[0] if p[0]) or None
    except Exception:
        pass
    return None


def api_translate(text: str) -> Tuple[Optional[str], str]:
    if len(text) > 300:
        return None, "too_long"
    time.sleep(0.25)
    r = translate_mymemory(text)
    if r:
        return r, "mymemory"
    time.sleep(0.25)
    r = translate_google(text)
    if r:
        return r, "google"
    return None, "failed"


# ─── Banco de traduções ──────────────────────────────────────

def load_db() -> Tuple[Dict, Dict]:
    translations, pending = {}, {}
    if TRANSLATIONS_FILE.exists():
        with open(TRANSLATIONS_FILE, encoding="utf-8") as f:
            translations = json.load(f).get("translations", {})
    if PENDING_FILE.exists():
        with open(PENDING_FILE, encoding="utf-8") as f:
            pending = json.load(f).get("pending", {})
    return translations, pending


def save_db(translations: Dict, pending: Dict):
    for path, key, data in [
        (TRANSLATIONS_FILE, "translations", translations),
        (PENDING_FILE,      "pending",      pending),
    ]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "version": "2.0.0",
                "last_updated": datetime.now().isoformat(),
                f"total_{key}": len(data),
                key: data,
            }, f, ensure_ascii=False, indent=2)


# ─── Helpers de string ───────────────────────────────────────

def unescape_js(s: str) -> str:
    """Decodifica escapes básicos de JS para comparação/hash."""
    return (s.replace("\\n", "\n")
             .replace("\\t", "\t")
             .replace('\\"', '"')
             .replace("\\'", "'")
             .replace("\\\\", "\\"))


def escape_js(s: str, quote: str = '"') -> str:
    """Escapa string para reinserção em JS."""
    s = s.replace("\\", "\\\\")
    s = s.replace(quote, "\\" + quote)
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    s = s.replace("\t", "\\t")
    return s


def should_skip(text: str) -> bool:
    text = text.strip()
    if len(text) < 2 or len(text) > 500:
        return True
    for pat in SKIP_RE:
        if pat.search(text):
            return True
    return False


# ─── Patch de um arquivo JS ──────────────────────────────────

def patch_js_file(fpath: str, translations: Dict, pending: Dict,
                  use_api: bool, dry_run: bool) -> int:
    """Patch um arquivo JS compilado. Retorna nº de substituições feitas."""
    content = docker_read(WEB_CONTAINER, fpath)
    if not content:
        return 0

    # Mapeia: match original (com aspas) → string traduzida (com aspas)
    replacements: Dict[str, str] = {}

    for pattern, quote in [(DQUOTE_CHINESE, '"'), (SQUOTE_CHINESE, "'")]:
        for match in pattern.finditer(content):
            raw_inner = match.group(1)          # sem aspas, com escapes
            full      = match.group(0)          # com aspas

            if full in replacements:
                continue  # já processado

            clean = unescape_js(raw_inner)      # texto puro
            if should_skip(clean):
                continue

            h = get_hash(clean)

            if h in translations:
                translated = translations[h]["translated"]
                replacements[full] = f'{quote}{escape_js(translated, quote)}{quote}'
                if dry_run:
                    print(f"    [DB]  \"{clean[:45]}\" → \"{translated[:45]}\"")

            elif use_api:
                translated, method = api_translate(clean)
                if translated:
                    translations[h] = {
                        "original": clean, "translated": translated,
                        "source_lang": "zh", "translator": method,
                        "file_path": f"web:{os.path.basename(fpath)}",
                        "line_number": 0, "context": clean[:60],
                        "date_added": datetime.now().isoformat(),
                        "verified": False,
                    }
                    pending.pop(h, None)
                    replacements[full] = f'{quote}{escape_js(translated, quote)}{quote}'
                    if dry_run:
                        print(f"    [API] \"{clean[:45]}\" → \"{translated[:45]}\"")
                else:
                    if h not in pending and h not in translations:
                        pending[h] = {
                            "original": clean, "source_lang": "zh",
                            "file_path": f"web:{os.path.basename(fpath)}",
                            "line_number": 0, "context": clean[:60],
                            "hash": h,
                            "date_found": datetime.now().isoformat(),
                            "suggested_translation": "",
                        }
            else:
                if h not in pending and h not in translations:
                    pending[h] = {
                        "original": clean, "source_lang": "zh",
                        "file_path": f"web:{os.path.basename(fpath)}",
                        "line_number": 0, "context": clean[:60],
                        "hash": h,
                        "date_found": datetime.now().isoformat(),
                        "suggested_translation": "",
                    }

    if not replacements:
        print(f"    Nada para traduzir neste arquivo.")
        return 0

    # Aplicar substituições (do maior para menor evita sobreposição)
    if not dry_run:
        for old, new in sorted(replacements.items(), key=lambda x: -len(x[0])):
            content = content.replace(old, new)

        # Gravar em tmp e copiar para o container
        fd, tmp_path = tempfile.mkstemp(suffix=".js")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            docker_cp(tmp_path, WEB_CONTAINER, fpath)
        finally:
            os.unlink(tmp_path)

    print(f"    Substituições: {len(replacements)}")
    return len(replacements)


# ─── Main ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Patch dos assets JS compilados no container web")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-api",  action="store_true")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  PATCH DOS ASSETS WEB — xiaozhi-esp32-server")
    print("=" * 60)

    if not container_alive(WEB_CONTAINER):
        print(f"\n  [ERRO] Container '{WEB_CONTAINER}' não está rodando!")
        sys.exit(1)

    translations, pending = load_db()
    print(f"\n  Traduções no banco : {len(translations)}")
    print(f"  Modo               : {'DRY-RUN' if args.dry_run else 'APLICAR'}")
    print(f"  API automática     : {'NÃO' if args.no_api else 'SIM'}")

    js_files = find_js_files()
    if not js_files:
        print("\n  Nenhum JS com chinês no container. Já traduzido ou não encontrado.")
        return

    print(f"\n  Arquivos JS com chinês: {len(js_files)}")

    total = 0
    for fpath in js_files:
        print(f"\n  [{os.path.basename(fpath)}]")
        total += patch_js_file(fpath, translations, pending,
                               use_api=not args.no_api, dry_run=args.dry_run)

    print(f"\n{'=' * 60}")
    print(f"  Total de substituições nos assets : {total}")
    print(f"{'=' * 60}")

    if not args.dry_run:
        save_db(translations, pending)
        print("\n  Banco de traduções atualizado.")


if __name__ == "__main__":
    main()
