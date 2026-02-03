#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extrai e analisa todas as strings traduzíveis dos containers Docker.

Fontes escaneadas:
  1. Arquivos Python/YAML/JSON no container do servidor
  2. JS compilado no container web (nginx)
  3. Tabelas do MySQL com dados padrão em chinês

Uso:
    python3 scripts/extract_docker.py            # Análise completa
    python3 scripts/extract_docker.py --save     # Salva arquivos extraídos em extractions/
    python3 scripts/extract_docker.py --db-only  # Só banco de dados
"""

import subprocess
import json
import re
import hashlib
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

# ─── Config ──────────────────────────────────────────────────
SERVER_CONTAINER = "xiaozhi-esp32-server"
WEB_CONTAINER    = "xiaozhi-esp32-server-web"
DB_CONTAINER     = "xiaozhi-esp32-server-db"
DB_USER          = "root"
DB_PASS          = "123456"
DB_NAME          = "xiaozhi_esp32_server"
SERVER_BASE      = "/opt/xiaozhi-esp32-server"
NGINX_ROOT       = "/usr/share/nginx/html"

CHINESE = re.compile(r'[\u4e00-\u9fff]')

SCRIPT_DIR        = Path(__file__).parent
PATCH_ROOT        = SCRIPT_DIR.parent
TRANSLATIONS_FILE = PATCH_ROOT / "translations" / "translations.json"
PENDING_FILE      = PATCH_ROOT / "translations" / "pending.json"


def get_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def run(cmd: List[str], timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def container_alive(name: str) -> bool:
    return run(["docker", "inspect", "--format", "{{.State.Running}}", name]).strip() == "true"


def load_translations() -> Dict[str, dict]:
    if TRANSLATIONS_FILE.exists():
        with open(TRANSLATIONS_FILE, encoding="utf-8") as f:
            return json.load(f).get("translations", {})
    return {}


def load_pending() -> Dict[str, dict]:
    if PENDING_FILE.exists():
        with open(PENDING_FILE, encoding="utf-8") as f:
            return json.load(f).get("pending", {})
    return {}


# ─── Extração do servidor ────────────────────────────────────

def scan_server_files() -> List[Tuple[str, int]]:
    """Retorna lista de (arquivo_relativo, nlines_chinês) do container servidor."""
    if not container_alive(SERVER_CONTAINER):
        print("  [AVISO] Container do servidor não está rodando.")
        return []

    # Listar arquivos com extensões relevantes
    exts = "-name '*.py' -o -name '*.yaml' -o -name '*.yml' -o -name '*.json' -o -name '*.sh'"
    file_list = run(["docker", "exec", SERVER_CONTAINER, "bash", "-c",
                     f"find {SERVER_BASE} -type f \\( {exts} \\)"], timeout=15)

    results = []
    for fpath in sorted(file_list.strip().split("\n")):
        fpath = fpath.strip()
        if not fpath:
            continue
        content = run(["docker", "exec", SERVER_CONTAINER, "cat", fpath], timeout=10)
        if not content:
            continue
        cn_lines = sum(1 for line in content.split("\n") if CHINESE.search(line))
        if cn_lines > 0:
            rel = fpath.replace(SERVER_BASE + "/", "")
            results.append((rel, cn_lines))
    return results


# ─── Extração do web container ───────────────────────────────

def scan_web_assets() -> List[Tuple[str, int, List[str]]]:
    """Retorna (arquivo, nstrings, [strings_chinesas]) dos JS compilados."""
    if not container_alive(WEB_CONTAINER):
        print("  [AVISO] Container web não está rodando.")
        return []

    # Buscar JS com chinês
    r = run(["docker", "exec", WEB_CONTAINER, "bash", "-c",
             f"find {NGINX_ROOT} -name '*.js' -type f"], timeout=15)
    all_js = [l.strip() for l in r.strip().split("\n") if l.strip()]

    dquote = re.compile(r'"((?:[^"\\]|\\.)*?[\u4e00-\u9fff](?:[^"\\]|\\.)*?)"')
    squote = re.compile(r"'((?:[^'\\]|\\.)*?[\u4e00-\u9fff](?:[^'\\]|\\.)*?)'")

    results = []
    for fpath in all_js:
        content = run(["docker", "exec", WEB_CONTAINER, "cat", fpath], timeout=10)
        if not content or not CHINESE.search(content):
            continue
        strings = set()
        for pat in [dquote, squote]:
            for m in pat.finditer(content):
                s = m.group(1).replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
                if CHINESE.search(s) and 2 <= len(s.strip()) <= 500:
                    strings.add(s.strip())
        if strings:
            fname = fpath.replace(NGINX_ROOT + "/", "")
            results.append((fname, len(strings), sorted(strings)))
    return results


# ─── Extração do banco ───────────────────────────────────────

def mysql_json(sql: str) -> str:
    return run(["docker", "exec", DB_CONTAINER,
                "mysql", "-u", DB_USER, f"-p{DB_PASS}",
                "--default-character-set=utf8mb4", DB_NAME, "-N", "-e", sql],
               timeout=30).strip()


def scan_database() -> Dict[str, List[Tuple[str, str]]]:
    """Retorna {tabela: [(campo_id, texto_chinês), ...]}"""
    if not container_alive(DB_CONTAINER):
        print("  [AVISO] Container do banco não está rodando.")
        return {}

    results = {}

    # sys_params
    raw = mysql_json("SELECT JSON_ARRAYAGG(JSON_OBJECT('code',param_code,'value',param_value,'remark',remark)) FROM sys_params WHERE param_code NOT IN ('xiaozhi','system-web.menu')")
    try:
        rows = json.loads(raw) or []
    except Exception:
        rows = []
    entries = []
    for row in rows:
        if not row:
            continue
        code = row.get("code", "")
        for col in ("value", "remark"):
            val = row.get(col) or ""
            if CHINESE.search(val):
                entries.append((f"{code}.{col}", val[:80]))
    if entries:
        results["sys_params"] = entries

    # sys_dict_data
    raw = mysql_json("SELECT JSON_ARRAYAGG(JSON_OBJECT('id',id,'label',dict_label,'remark',remark)) FROM sys_dict_data")
    try:
        rows = json.loads(raw) or []
    except Exception:
        rows = []
    entries = []
    for row in rows:
        if not row:
            continue
        for col in ("label", "remark"):
            val = row.get(col) or ""
            if CHINESE.search(val):
                entries.append((f"id={row['id']}.{col}", val[:60]))
    if entries:
        results["sys_dict_data"] = entries

    # ai_model_provider
    raw = mysql_json("SELECT JSON_ARRAYAGG(JSON_OBJECT('id',id,'name',name,'fields',fields)) FROM ai_model_provider")
    try:
        rows = json.loads(raw) or []
    except Exception:
        rows = []
    entries = []
    for row in rows:
        if not row:
            continue
        rec_id = row.get("id", "")
        if row.get("name") and CHINESE.search(row["name"]):
            entries.append((f"id={rec_id}.name", row["name"]))
        fields = row.get("fields") or []
        if isinstance(fields, str):
            try:
                fields = json.loads(fields)
            except Exception:
                fields = []
        for field in (fields if isinstance(fields, list) else []):
            label = field.get("label", "")
            if label and CHINESE.search(label):
                entries.append((f"id={rec_id}.fields[{field.get('key','')}].label", label))
    if entries:
        results["ai_model_provider"] = entries

    # ai_model_config — HEX(remark) evita quebra de JSON no MySQL 9.x
    raw = mysql_json("SELECT JSON_ARRAYAGG(JSON_OBJECT('id',id,'name',model_name,'remark',HEX(remark))) FROM ai_model_config")
    try:
        rows = json.loads(raw) or []
    except Exception:
        rows = []
    entries = []
    for row in rows:
        if not row:
            continue
        rec_id = row.get("id", "")
        remark = bytes.fromhex(row["remark"]).decode("utf-8") if row.get("remark") else ""
        if row.get("name") and CHINESE.search(row["name"]):
            entries.append((f"id={rec_id}.name", row["name"][:60]))
        if remark and CHINESE.search(remark):
            entries.append((f"id={rec_id}.remark", remark[:60] + "..."))
    if entries:
        results["ai_model_config"] = entries

    # ai_agent_template (só agent_name — system_prompt manter chinês)
    raw = mysql_json("SELECT JSON_ARRAYAGG(JSON_OBJECT('id',id,'name',agent_name)) FROM ai_agent_template")
    try:
        rows = json.loads(raw) or []
    except Exception:
        rows = []
    entries = []
    for row in rows:
        if not row:
            continue
        if row.get("name") and CHINESE.search(row["name"]):
            entries.append((f"id={row['id']}.agent_name", row["name"]))
    if entries:
        results["ai_agent_template"] = entries

    return results


# ─── Relatório ───────────────────────────────────────────────

def check_translation_coverage(db_entries: Dict, web_strings: List,
                               translations: Dict) -> Dict[str, int]:
    """Conta strings já traduzidas vs pendentes."""
    stats = {"total": 0, "translated": 0, "pending": 0}

    # DB entries
    for table, entries in db_entries.items():
        for _, text in entries:
            stats["total"] += 1
            h = get_hash(text)
            if h in translations:
                stats["translated"] += 1
            else:
                stats["pending"] += 1

    # Web strings
    for _, _, strings in web_strings:
        for s in strings:
            stats["total"] += 1
            h = get_hash(s)
            if h in translations:
                stats["translated"] += 1
            else:
                stats["pending"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Análise de strings traduzíveis nos containers")
    parser.add_argument("--save",    action="store_true", help="Salva extrações em disco")
    parser.add_argument("--db-only", action="store_true", help="Só banco de dados")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  ANÁLISE DE STRINGS — xiaozhi-esp32-server (Docker)")
    print("=" * 60)

    translations = load_translations()
    pending      = load_pending()
    print(f"\n  Banco de traduções: {len(translations)} | Pendentes: {len(pending)}")

    # ── Servidor ──
    server_files = []
    if not args.db_only:
        print("\n  ── Servidor (Python/YAML/JSON) ──")
        server_files = scan_server_files()
        if server_files:
            total_lines = sum(n for _, n in server_files)
            print(f"    Arquivos com chinês : {len(server_files)}")
            print(f"    Linhas com chinês   : {total_lines}")
            for rel, n in server_files:
                print(f"      {n:4d} | {rel}")
        else:
            print("    Nenhum arquivo com chinês no container.")

    # ── Web ──
    web_data = []
    if not args.db_only:
        print("\n  ── Assets Web (JS compilado) ──")
        web_data = scan_web_assets()
        if web_data:
            for fname, nstr, strings in web_data:
                print(f"    [{fname}] — {nstr} strings chinesas:")
                for s in strings[:15]:
                    h = get_hash(s)
                    status = "[OK]" if h in translations else "[--]"
                    print(f"      {status} \"{s[:60]}\"")
                if nstr > 15:
                    print(f"      ... e mais {nstr - 15}")
        else:
            print("    Nenhum JS com chinês. Assets já traduzidos!")

    # ── Banco de dados ──
    print("\n  ── Banco de Dados (MySQL) ──")
    db_data = scan_database()
    if db_data:
        for table, entries in db_data.items():
            print(f"\n    [{table}] — {len(entries)} campos com chinês:")
            for field_id, text in entries[:20]:
                h = get_hash(text)
                status = "[OK]" if h in translations else "[--]"
                print(f"      {status} {field_id}: \"{text[:55]}\"")
            if len(entries) > 20:
                print(f"      ... e mais {len(entries) - 20}")
    else:
        print("    Banco já traduzido ou não acessível.")

    # ── Cobertura ──
    coverage = check_translation_coverage(db_data, web_data, translations)
    total    = coverage["total"]
    done     = coverage["translated"]
    pct      = (done / total * 100) if total > 0 else 100

    print(f"\n{'=' * 60}")
    print(f"  COBERTURA DE TRADUÇÃO (DB + Web Assets)")
    print(f"  Total encontrado  : {total}")
    print(f"  Já traduzidos     : {done}")
    print(f"  Sem tradução      : {coverage['pending']}")
    print(f"  Cobertura         : {pct:.1f}%")
    print(f"{'=' * 60}")

    if coverage["pending"] > 0:
        print(f"\n  Para traduzir as pendentes:")
        print(f"    python3 scripts/patch_database.py          # banco")
        print(f"    python3 scripts/patch_web_assets.py        # assets web")

    # ── Salvar extrações ──
    if args.save:
        out_dir = PATCH_ROOT / "extractions"
        out_dir.mkdir(exist_ok=True)

        summary = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "server_files": [{"file": f, "chinese_lines": n} for f, n in server_files],
            "web_assets": [{"file": f, "strings": s} for f, _, s in web_data],
            "database": {t: [{"field": fid, "text": txt} for fid, txt in entries]
                         for t, entries in db_data.items()},
            "coverage": coverage,
        }
        with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"\n  Resumo salvo em: extractions/summary.json")


if __name__ == "__main__":
    main()
