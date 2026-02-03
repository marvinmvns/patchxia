#!/usr/bin/env python3
"""
translate_md.py — Traduz arquivos .md do projeto xiaozhi para pt-BR.

Preserva integralmente:
  - Blocos de código (``` ... ```) e código inline (`...`)
  - URLs e caminhos de arquivo
  - Links [texto](url)  →  texto traduzido, URL intacta
  - Imagens ![alt](url)
  - Tags HTML (<br/>, etc.)
  - Separadores de tabela (|---|---|)
  - Marcadores de lista e indentação

Uso:
  python3 scripts/translate_md.py                          # todos os .md
  python3 scripts/translate_md.py docs/FAQ.md              # arquivo específico
  python3 scripts/translate_md.py --dry-run                # preview sem aplicar
  python3 scripts/translate_md.py --no-api                 # só traduções em cache
"""

import argparse, hashlib, json, os, re, sys, time
import urllib.parse, urllib.request, ssl
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple

ssl._create_default_https_context = ssl._create_unverified_context

# ─── Caminhos ─────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
PATCH_ROOT   = SCRIPT_DIR.parent
TRANS_FILE   = PATCH_ROOT / "translations" / "translations.json"
PENDING_FILE = PATCH_ROOT / "translations" / "pending.json"

CHINESE = re.compile(r'[\u4e00-\u9fff]')

# Projeto padrão
DEFAULT_PROJECT = Path("/home/bigfriend/Documentos/bora/xiaozhi-esp32-server")

# ─── JSON helpers ─────────────────────────────────────────
def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── APIs de tradução ─────────────────────────────────────
def _mymemory(text: str) -> Optional[str]:
    try:
        url = ("https://api.mymemory.translated.net/get"
               f"?q={urllib.parse.quote(text)}&langpair=zh|pt-BR")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
            if data.get("responseStatus") == 200:
                t = data.get("responseData", {}).get("translatedText", "")
                if t and t.lower() != text.lower():
                    return t
    except Exception:
        pass
    return None

def _google(text: str) -> Optional[str]:
    try:
        url = ("https://translate.googleapis.com/translate_a/single"
               f"?client=gtx&sl=zh-CN&tl=pt&dt=t&q={urllib.parse.quote(text)}")
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
            if data and data[0]:
                return "".join(p[0] for p in data[0] if p[0])
    except Exception:
        pass
    return None

def api_translate(text: str) -> Optional[str]:
    """Tenta MyMemory (até 500 chars) depois Google."""
    if len(text.strip()) < 2:
        return None
    time.sleep(0.3)
    if len(text) <= 500:
        result = _mymemory(text)
        if result:
            return result
        time.sleep(0.2)
    return _google(text)

# ─── Hash ─────────────────────────────────────────────────
def md5_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

# ─── Protecção de elementos inline ────────────────────────
# Placeholder: {__N__}  — improvável de aparecer em texto natural
PH_RE = re.compile(r"\{__\s*(\d+)\s*__\}")

def protect(line: str) -> Tuple[str, List[str]]:
    """Substitui código inline, URLs e HTML por placeholders {__N__}.

    Links [texto](url): a URL fica protegida, o texto fica visível
    para a API traduzir junto com o resto da linha.
    Imagens e links sem texto chinês ficam protegidos inteiros.
    """
    slots: List[str] = []

    def _slot(s: str) -> str:
        idx = len(slots)
        slots.append(s)
        return f"{{__{idx}__}}"

    # 1. Imagens  ![alt](url)  — inteiras
    line = re.sub(r"!\[[^\]]*\]\([^)]+\)", lambda m: _slot(m.group()), line)

    # 2. Links  [texto](url)
    def _link(m):
        txt, url = m.group(1), m.group(2)
        if CHINESE.search(txt):
            # Texto tem chinês → protege só a URL, texto fica para traduzir
            return f"[{txt}]({_slot(url)})"
        # Texto sem chinês → protege o link inteiro
        return _slot(m.group())
    line = re.sub(r"\[([^\]]*)\]\(([^)]+)\)", _link, line)

    # 3. Código inline  `...`
    line = re.sub(r"`[^`]+`", lambda m: _slot(m.group()), line)

    # 4. URLs bare
    line = re.sub(r"https?://[^\s\)>\]]+", lambda m: _slot(m.group()), line)

    # 5. Tags HTML  <...>
    line = re.sub(r"<[^>]+>", lambda m: _slot(m.group()), line)

    # 6. Bold  **texto**  →  {__N__}texto{__M__}   (marcadores protegidos)
    #    Italic  *texto*  →  {__N__}texto{__M__}    (só quando não é lista)
    line = re.sub(r"\*\*", lambda m: _slot("**"), line)
    # Italic: *word* mas não no início da linha (lista)
    line = re.sub(r"(?<=\S)\*(?=\S)|(?<=\s)\*(?=\S[^*])", lambda m: _slot("*"), line)

    return line, slots

def restore(line: str, slots: List[str]) -> str:
    """Restaura placeholders → conteúdo original."""
    def _r(m):
        i = int(m.group(1))
        return slots[i] if i < len(slots) else m.group()
    return PH_RE.sub(_r, line)

def fixup(line: str) -> str:
    """Corrige artefactos que a API de tradução injecta."""
    # ** texto **  →  **texto**   (bold quebrado por espaços)
    line = re.sub(r'\*\* +', '**', line)
    line = re.sub(r' +\*\*', '**', line)
    # * texto *  →  *texto*     (italic quebrado — só entre palavras)
    line = re.sub(r'(?<=\S) \*(?=\s)', '*', line)
    line = re.sub(r'(?<=\s)\* (?=\S)', '*', line)
    # ] (url)  →  ](url)        (link markdown quebrado por espaço)
    line = re.sub(r'\]\s+\(', '](', line)
    return line

# ─── Tabelas ──────────────────────────────────────────────
TABLE_SEP = re.compile(r"^[|:\- ]+$")

def translate_table_row(line: str, resolve) -> str:
    """Traduz cada célula individualmente."""
    if TABLE_SEP.match(line.strip()):
        return line  # separador
    parts = line.split("|")
    out = []
    for i, cell in enumerate(parts):
        # Primeira e última parte são margem vazia
        if i == 0 or i == len(parts) - 1:
            out.append(cell)
            continue
        stripped = cell.strip()
        if not stripped or not CHINESE.search(stripped):
            out.append(cell)
            continue
        # Protege inline dentro da célula
        prot, slots = protect(stripped)
        if not CHINESE.search(prot):
            out.append(cell)  # chinês estava só em código
            continue
        t = resolve(prot)
        if t:
            t = fixup(restore(t, slots))
            out.append(f" {t} ")
        else:
            out.append(cell)
    return "|".join(out)

# ─── Tradutor principal ───────────────────────────────────
class MDTranslator:
    def __init__(self, use_api: bool = True):
        self.use_api = use_api
        raw = load_json(TRANS_FILE)
        self.db = raw.get("translations", raw)   # aceita ambos os formatos
        raw_pending = load_json(PENDING_FILE)
        self.pending = raw_pending.get("pending", raw_pending)  # aceita ambos os formatos
        self.dirty_db = False
        self.dirty_pending = False
        self.stats = {"translated": 0, "cached": 0, "pending": 0}

    # ── resolve: cache → API → pending ────────────────────
    def resolve(self, text: str) -> Optional[str]:
        h = md5_key(text)

        # Cache
        if h in self.db:
            entry = self.db[h]
            t = entry.get("translated", "") if isinstance(entry, dict) else ""
            if t:
                self.stats["cached"] += 1
                return t

        # API
        if self.use_api:
            t = api_translate(text)
            if t:
                self.db[h] = {
                    "original": text, "translated": t,
                    "source_lang": "zh", "translator": "md_api",
                    "file_path": "md", "line_number": 0, "context": "",
                    "date_added": datetime.now().isoformat(), "verified": False
                }
                self.dirty_db = True
                self.stats["translated"] += 1
                return t

        # Pending
        if h not in self.pending:
            self.pending[h] = {
                "original": text, "source_lang": "zh",
                "file_path": "md", "line_number": 0, "context": "",
                "hash": h, "date_found": datetime.now().isoformat(),
                "suggested_translation": ""
            }
            self.dirty_pending = True
        self.stats["pending"] += 1
        return None

    # ── traduz uma linha ──────────────────────────────────
    def translate_line(self, line: str) -> str:
        s = line.rstrip("\n")

        # Heading:  # Título
        hm = re.match(r"^(#{1,6}\s+)(.*)", s)
        if hm:
            prefix, text = hm.group(1), hm.group(2)
            if CHINESE.search(text):
                prot, slots = protect(text)
                if CHINESE.search(prot):
                    t = self.resolve(prot)
                    if t:
                        return prefix + fixup(restore(t, slots))
            return s

        # Tabela
        if s.lstrip().startswith("|"):
            return translate_table_row(s, self.resolve)

        # Linha normal com chinês
        if not CHINESE.search(s):
            return s

        # Preservar prefixo de lista  (- item / 1. item / * item)
        lm = re.match(r"^(\s*(?:[-*+]|\d+[.)]) +)", s)
        prefix = lm.group(1) if lm else ""
        body   = s[len(prefix):]

        prot, slots = protect(body)
        if not CHINESE.search(prot):
            return s  # chinês estava só dentro de código inline

        t = self.resolve(prot)
        if t:
            return prefix + fixup(restore(t, slots))
        return s  # sem tradução disponível

    # ── traduz arquivo inteiro ────────────────────────────
    def translate_file(self, filepath: str, dry_run: bool) -> bool:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()

        in_code = False
        out: List[str] = []
        changed = False

        for i, raw_line in enumerate(lines):
            s = raw_line.rstrip("\n")

            # Toggle code fence
            if s.startswith("```"):
                in_code = not in_code
                out.append(raw_line)
                continue

            # Dentro de code block — não toca
            if in_code:
                out.append(raw_line)
                continue

            # Sem chinês → passa
            if not CHINESE.search(s):
                out.append(raw_line)
                continue

            # HTML comment bloco
            if s.strip().startswith("<!--"):
                out.append(raw_line)
                continue

            translated = self.translate_line(s)
            if translated != s:
                changed = True
                if dry_run:
                    print(f"    [{i+1:4d}] {s[:70]}")
                    print(f"         → {translated[:70]}")
                out.append(translated + ("\n" if raw_line.endswith("\n") else ""))
            else:
                out.append(raw_line)

        if changed and not dry_run:
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(out)
        return changed

    # ── salvar banco ──────────────────────────────────────
    def save(self):
        if self.dirty_db:
            raw = load_json(TRANS_FILE)
            if "translations" in raw:
                raw["translations"].update(self.db)
            else:
                raw.update(self.db)
            save_json(TRANS_FILE, raw)
        if self.dirty_pending:
            raw = load_json(PENDING_FILE)
            if "pending" in raw:
                raw["pending"].update(self.pending)
            else:
                raw = {"pending": self.pending}
            save_json(PENDING_FILE, raw)


# ─── CLI ──────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Traduz arquivos .md do xiaozhi para pt-BR")
    parser.add_argument("files", nargs="*",
                        help="Arquivos .md (caminho relativo ao projeto)")
    parser.add_argument("--project", default=str(DEFAULT_PROJECT),
                        help="Raiz do projeto xiaozhi")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview sem gravar")
    parser.add_argument("--no-api", action="store_true",
                        help="Usar apenas cache local, sem chamadas à API")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.exists():
        print(f"Erro: projeto não encontrado em {project}")
        sys.exit(1)

    # ── collectar arquivos alvo ─────────────────────────
    SKIP_DIRS = {"node_modules", ".git", "mysql"}
    if args.files:
        md_files = [project / f for f in args.files]
    else:
        md_files = sorted(
            f for f in project.rglob("*.md")
            if not SKIP_DIRS.intersection(f.parts)
        )

    # Filtrar por presença de chinês
    targets = []
    for f in md_files:
        if not f.exists():
            print(f"  [SKIP] não encontrado: {f}")
            continue
        with open(f, encoding="utf-8") as fh:
            if CHINESE.search(fh.read()):
                targets.append(f)

    # ── cabeçalho ─────────────────────────────────────
    mode = ("DRY-RUN" if args.dry_run
            else ("sem API (cache)" if args.no_api else "com API"))
    print()
    print("=" * 60)
    print("  TRADUÇÃO DE MARKDOWN — xiaozhi-esp32-server")
    print("=" * 60)
    print(f"  Modo     : {mode}")
    print(f"  Projeto  : {project}")
    print(f"  Arquivos : {len(targets)}")
    print()

    translator = MDTranslator(use_api=not args.no_api)

    for fpath in targets:
        rel = fpath.relative_to(project)
        print(f"  [{rel}]")
        changed = translator.translate_file(str(fpath), dry_run=args.dry_run)
        if args.dry_run:
            pass  # linhas já foram printadas dentro de translate_file
        elif changed:
            print(f"    → traduzido")
        else:
            print(f"    → sem alterações")

    # ── resumo ────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"  Traduzidos (API)  : {translator.stats['translated']}")
    print(f"  Em cache          : {translator.stats['cached']}")
    print(f"  Pendentes         : {translator.stats['pending']}")
    print("=" * 60)

    if not args.dry_run:
        translator.save()
        if translator.stats["pending"]:
            print(f"\n  {translator.stats['pending']} strings pendentes.")
            print("  Use: python3 scripts/translate_pending.py")
        else:
            print("\n  Banco de traduções atualizado.")


if __name__ == "__main__":
    main()
