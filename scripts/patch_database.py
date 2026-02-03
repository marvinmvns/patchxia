#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplica patches de tradução no banco MySQL do xiaozhi-esp32-server via Docker.

Tabelas traduzidas:
  sys_params        → param_value (exit_commands, wakeup_words), remark
  sys_dict_data     → dict_label, remark
  ai_model_provider → name, fields[].label (JSON)
  ai_model_config   → model_name, remark
  ai_agent_template → agent_name

NÃO traduzido (intencionalmente):
  ai_agent_template.system_prompt  — prompt do LLM, manter chinês
  sys_params end_prompt.prompt     — prompt interno do LLM
  sys_params xiaozhi / system-web.menu — JSON estrutural
  Campos com chaves / tokens / URLs

Uso:
    python3 scripts/patch_database.py              # Aplica com tradução automática
    python3 scripts/patch_database.py --dry-run    # Mostra mudanças sem aplicar
    python3 scripts/patch_database.py --no-api     # Só usa banco de traduções local
"""

import subprocess
import json
import re
import hashlib
import time
import argparse
import ssl
import urllib.parse
import urllib.request
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime

ssl._create_default_https_context = ssl._create_unverified_context

# ─── Caminhos ────────────────────────────────────────────────
SCRIPT_DIR        = Path(__file__).parent
PATCH_ROOT        = SCRIPT_DIR.parent
TRANSLATIONS_FILE = PATCH_ROOT / "translations" / "translations.json"
PENDING_FILE      = PATCH_ROOT / "translations" / "pending.json"

# ─── Docker / MySQL ──────────────────────────────────────────
DB_CONTAINER = "xiaozhi-esp32-server-db"
DB_USER      = "root"
DB_PASS      = "123456"
DB_NAME      = "xiaozhi_esp32_server"

CHINESE = re.compile(r'[\u4e00-\u9fff]')

# ─── Campos cujo param_value NÃO deve ser traduzido ─────────
SKIP_VALUE_PARAMS = {
    "end_prompt.prompt",
    "server.secret", "server.public_key", "server.private_key",
    "log.log_format", "log.log_format_file",
    "xiaozhi", "system-web.menu",
    "server.fronted_url", "server.websocket", "server.ota",
    "server.mcp_endpoint", "server.voice_print",
    "server.mqtt_gateway", "server.mqtt_signature_key",
    "server.udp_gateway", "server.mqtt_manager_api",
    "aliyun.sms.access_key_id", "aliyun.sms.access_key_secret",
    "aliyun.sms.sign_name", "aliyun.sms.sms_code_template_code",
    "server.beian_icp_num", "server.beian_ga_num",
    "server.name",
}

# Parâmetros que são arrays separados por ; e devem ter cada item traduzido
ARRAY_PARAMS = {"exit_commands", "wakeup_words"}

# ─── Helpers ─────────────────────────────────────────────────

def get_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]


def mysql_json(sql: str) -> str:
    """Executa SELECT e retorna stdout raw."""
    try:
        r = subprocess.run(
            ["docker", "exec", DB_CONTAINER,
             "mysql", "-u", DB_USER, f"-p{DB_PASS}",
             "--default-character-set=utf8mb4", DB_NAME, "-N", "-e", sql],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            print(f"    [DB ERR] {r.stderr.strip()[:120]}")
        return r.stdout.strip()
    except Exception as e:
        print(f"    [Docker ERR] {e}")
        return ""


def mysql_exec(sql: str) -> bool:
    """Executa UPDATE/INSERT."""
    try:
        r = subprocess.run(
            ["docker", "exec", DB_CONTAINER,
             "mysql", "-u", DB_USER, f"-p{DB_PASS}",
             "--default-character-set=utf8mb4", DB_NAME, "-e", sql],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            print(f"    [DB ERR] {r.stderr.strip()[:120]}")
            return False
        return True
    except Exception as e:
        print(f"    [Docker ERR] {e}")
        return False


def esc(s: str) -> str:
    """Escapa string para INSERT/UPDATE SQL."""
    return (s.replace("\\", "\\\\")
             .replace("'",  "\\'")
             .replace('"',  '\\"')
             .replace("\n", "\\n")
             .replace("\r", "\\r")
             .replace("\0", "\\0"))


def trunc(s: str, max_len: int) -> str:
    """Trunca string ao limite de caracteres da coluna varchar."""
    if len(s) <= max_len:
        return s
    return s[:max_len - 1] + "…"


def container_alive(name: str) -> bool:
    r = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", name],
        capture_output=True, text=True
    )
    return r.stdout.strip() == "true"


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
    # Textos muito longos (instruções setup) não traduzem bem via API gratuita
    if len(text) > 400:
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


# ─── Banco de traduções local ────────────────────────────────

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


# ─── Classe central do patcher ───────────────────────────────

class DBPatcher:
    def __init__(self, translations: Dict, pending: Dict,
                 use_api: bool, dry_run: bool):
        self.translations = translations
        self.pending      = pending
        self.use_api      = use_api
        self.dry_run      = dry_run
        self.stats        = {"translated": 0, "pending": 0, "skipped": 0}

    def resolve(self, text: str, context: str) -> Optional[str]:
        """Tenta obter tradução. Retorna string traduzida ou None."""
        if not text or not CHINESE.search(text):
            self.stats["skipped"] += 1
            return None

        h = get_hash(text)

        # 1. Já no banco local?
        if h in self.translations:
            self.stats["translated"] += 1
            return self.translations[h]["translated"]

        # 2. Tentar API?
        if self.use_api:
            translated, method = api_translate(text)
            if translated:
                self.translations[h] = {
                    "original": text, "translated": translated,
                    "source_lang": "zh", "translator": method,
                    "file_path": context, "line_number": 0,
                    "context": context[:80],
                    "date_added": datetime.now().isoformat(),
                    "verified": False,
                }
                self.pending.pop(h, None)
                self.stats["translated"] += 1
                return translated

        # 3. Registrar pendente
        if h not in self.pending and h not in self.translations:
            self.pending[h] = {
                "original": text, "source_lang": "zh",
                "file_path": context, "line_number": 0,
                "context": context[:80], "hash": h,
                "date_found": datetime.now().isoformat(),
                "suggested_translation": "",
            }
        self.stats["pending"] += 1
        return None


# ─── Patch por tabela ────────────────────────────────────────

def patch_sys_params(p: DBPatcher):
    """sys_params: exit_commands, wakeup_words (arrays ;-separados) + remarks."""
    print("\n  [sys_params]")

    raw = mysql_json(
        "SELECT JSON_ARRAYAGG(JSON_OBJECT("
        "'code',param_code,'value',param_value,"
        "'remark',remark,'vtype',value_type"
        ")) FROM sys_params"
        " WHERE param_code NOT IN ('xiaozhi','system-web.menu')"
    )
    try:
        rows = json.loads(raw)
    except Exception as e:
        print(f"    [PARSE ERR] {e}"); return

    if not rows or rows == [None]:
        return

    for row in rows:
        if row is None:
            continue
        code   = row.get("code", "")
        value  = row.get("value") or ""
        remark = row.get("remark") or ""

        # ── remark ──
        if remark and CHINESE.search(remark):
            new_remark = p.resolve(remark, f"db:sys_params:{code}:remark")
            if new_remark:
                if p.dry_run:
                    print(f"    [DRY] {code}.remark: \"{remark[:40]}\" → \"{new_remark[:40]}\"")
                else:
                    mysql_exec(f"UPDATE sys_params SET remark='{esc(new_remark)}' "
                               f"WHERE param_code='{code}'")

        # ── param_value ──
        if code in SKIP_VALUE_PARAMS:
            continue
        if not value or not CHINESE.search(value):
            continue

        if code in ARRAY_PARAMS:
            # Split por ;, traduz cada item, rejunta
            items     = [i.strip() for i in value.split(";") if i.strip()]
            new_items = []
            changed   = False
            for item in items:
                t = p.resolve(item, f"db:sys_params:{code}:value")
                if t:
                    new_items.append(t)
                    changed = True
                else:
                    new_items.append(item)
            if changed:
                new_value = ";".join(new_items)
                if p.dry_run:
                    print(f"    [DRY] {code}: \"{value[:50]}\" → \"{new_value[:50]}\"")
                else:
                    mysql_exec(f"UPDATE sys_params SET param_value='{esc(new_value)}' "
                               f"WHERE param_code='{code}'")
        else:
            # Valor inteiro
            new_value = p.resolve(value, f"db:sys_params:{code}:value")
            if new_value:
                if p.dry_run:
                    print(f"    [DRY] {code}: \"{value[:50]}\" → \"{new_value[:50]}\"")
                else:
                    mysql_exec(f"UPDATE sys_params SET param_value='{esc(new_value)}' "
                               f"WHERE param_code='{code}'")


def patch_sys_dict_data(p: DBPatcher):
    """sys_dict_data: labels e remarks de dispositivos/firmware."""
    print("\n  [sys_dict_data]")

    raw = mysql_json(
        "SELECT JSON_ARRAYAGG(JSON_OBJECT("
        "'id',id,'label',dict_label,'remark',remark"
        ")) FROM sys_dict_data"
    )
    try:
        rows = json.loads(raw)
    except Exception as e:
        print(f"    [PARSE ERR] {e}"); return

    if not rows or rows == [None]:
        return

    for row in rows:
        if row is None:
            continue
        rec_id = row["id"]
        for col, db_col in [("label", "dict_label"), ("remark", "remark")]:
            value = row.get(col) or ""
            if not value or not CHINESE.search(value):
                continue
            new_val = p.resolve(value, f"db:sys_dict_data:{rec_id}:{db_col}")
            if new_val:
                if p.dry_run:
                    print(f"    [DRY] id={rec_id}.{db_col}: \"{value[:40]}\" → \"{new_val[:40]}\"")
                else:
                    mysql_exec(f"UPDATE sys_dict_data SET {db_col}='{esc(new_val)}' "
                               f"WHERE id={rec_id}")


def patch_ai_model_provider(p: DBPatcher):
    """ai_model_provider: name + fields[].label (JSON array)."""
    print("\n  [ai_model_provider]")

    raw = mysql_json(
        "SELECT JSON_ARRAYAGG(JSON_OBJECT("
        "'id',id,'name',name,'fields',fields"
        ")) FROM ai_model_provider"
    )
    try:
        rows = json.loads(raw)
    except Exception as e:
        print(f"    [PARSE ERR] {e}"); return

    if not rows or rows == [None]:
        return

    for row in rows:
        if row is None:
            continue
        rec_id = row["id"]
        name   = row.get("name") or ""
        fields = row.get("fields")  # já lista (MySQL JSON)

        # ── name ──
        if name and CHINESE.search(name):
            new_name = p.resolve(name, f"db:ai_model_provider:{rec_id}:name")
            if new_name:
                if p.dry_run:
                    print(f"    [DRY] id={rec_id}.name: \"{name}\" → \"{new_name}\"")
                else:
                    mysql_exec(f"UPDATE ai_model_provider SET name='{esc(trunc(new_name, 50))}' "
                               f"WHERE id='{rec_id}'")

        # ── fields[].label ──
        if not fields:
            continue
        if isinstance(fields, str):
            try:
                fields = json.loads(fields)
            except Exception:
                continue
        if not isinstance(fields, list):
            continue

        fields_changed = False
        for field in fields:
            label = field.get("label", "")
            if not label or not CHINESE.search(label):
                continue
            new_label = p.resolve(label, f"db:ai_model_provider:{rec_id}:fields.label")
            if new_label:
                field["label"] = new_label
                fields_changed = True
                if p.dry_run:
                    print(f"    [DRY] id={rec_id}.fields[{field.get('key','')}].label: "
                          f"\"{label}\" → \"{new_label}\"")

        if fields_changed and not p.dry_run:
            fields_json = json.dumps(fields, ensure_ascii=False)
            mysql_exec(f"UPDATE ai_model_provider SET fields='{esc(fields_json)}' "
                       f"WHERE id='{rec_id}'")


def patch_ai_model_config(p: DBPatcher):
    """ai_model_config: model_name + remark (instruções de setup)."""
    print("\n  [ai_model_config]")

    # MySQL 9.x JSON serialização quebra com aspas/newlines em TEXT —
    # HEX(remark) evita o problema; decodifica no Python.
    raw = mysql_json(
        "SELECT JSON_ARRAYAGG(JSON_OBJECT("
        "'id',id,'name',model_name,'remark',HEX(remark)"
        ")) FROM ai_model_config"
    )
    try:
        rows = json.loads(raw)
    except Exception as e:
        print(f"    [PARSE ERR] {e}"); return

    if not rows or rows == [None]:
        return

    for row in rows:
        if row is None:
            continue
        rec_id = row["id"]

        # ── model_name ──
        name = row.get("name") or ""
        if name and CHINESE.search(name):
            new_name = p.resolve(name, f"db:ai_model_config:{rec_id}:model_name")
            if new_name:
                if p.dry_run:
                    print(f"    [DRY] id={rec_id}.model_name: \"{name}\" → \"{new_name}\"")
                else:
                    mysql_exec(f"UPDATE ai_model_config SET model_name='{esc(trunc(new_name, 50))}' "
                               f"WHERE id='{rec_id}'")

        # ── remark (decodifica HEX) ──
        remark_hex = row.get("remark") or ""
        remark = bytes.fromhex(remark_hex).decode("utf-8") if remark_hex else ""
        if remark and CHINESE.search(remark):
            new_remark = p.resolve(remark, f"db:ai_model_config:{rec_id}:remark")
            if new_remark:
                if p.dry_run:
                    print(f"    [DRY] id={rec_id}.remark: \"{remark[:45]}...\" → \"{new_remark[:45]}...\"")
                else:
                    mysql_exec(f"UPDATE ai_model_config SET remark='{esc(new_remark)}' "
                               f"WHERE id='{rec_id}'")


def patch_ai_agent_template(p: DBPatcher):
    """ai_agent_template: APENAS agent_name. system_prompt mantém chinês."""
    print("\n  [ai_agent_template]")

    raw = mysql_json(
        "SELECT JSON_ARRAYAGG(JSON_OBJECT("
        "'id',id,'name',agent_name"
        ")) FROM ai_agent_template"
    )
    try:
        rows = json.loads(raw)
    except Exception as e:
        print(f"    [PARSE ERR] {e}"); return

    if not rows or rows == [None]:
        return

    for row in rows:
        if row is None:
            continue
        rec_id = row["id"]
        name   = row.get("name") or ""
        if not name or not CHINESE.search(name):
            continue
        new_name = p.resolve(name, f"db:ai_agent_template:{rec_id}:agent_name")
        if new_name:
            if p.dry_run:
                print(f"    [DRY] id={rec_id}.agent_name: \"{name}\" → \"{new_name}\"")
            else:
                mysql_exec(f"UPDATE ai_agent_template SET agent_name='{esc(trunc(new_name, 64))}' "
                           f"WHERE id='{rec_id}'")


# ─── Main ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Patch do banco MySQL via Docker")
    parser.add_argument("--dry-run", action="store_true", help="Mostra sem aplicar")
    parser.add_argument("--no-api",  action="store_true", help="Sem chamadas a API")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  PATCH DO BANCO DE DADOS — xiaozhi-esp32-server")
    print("=" * 60)

    if not container_alive(DB_CONTAINER):
        print(f"\n  [ERRO] Container '{DB_CONTAINER}' não está rodando!")
        print("  Inicie com: docker compose -f docker-compose_all.yml up -d")
        sys.exit(1)

    translations, pending = load_db()
    print(f"\n  Traduções no banco : {len(translations)}")
    print(f"  Pendentes          : {len(pending)}")
    print(f"  Modo               : {'DRY-RUN' if args.dry_run else 'APLICAR'}")
    print(f"  API automática     : {'NÃO' if args.no_api else 'SIM'}")

    p = DBPatcher(translations, pending,
                  use_api=not args.no_api, dry_run=args.dry_run)

    patch_sys_params(p)
    patch_sys_dict_data(p)
    patch_ai_model_provider(p)
    patch_ai_model_config(p)
    patch_ai_agent_template(p)

    print(f"\n{'=' * 60}")
    print(f"  Traduzidos  : {p.stats['translated']}")
    print(f"  Pendentes   : {p.stats['pending']}")
    print(f"  Sem chinês  : {p.stats['skipped']}")
    print(f"{'=' * 60}")

    if not args.dry_run:
        save_db(translations, pending)
        print("\n  Banco de traduções atualizado.")

    if p.stats["pending"] > 0:
        print(f"\n  Dica: {p.stats['pending']} strings sem tradução.")
        print("  Rode sem --no-api para tentar via API, ou use:")
        print("  python3 scripts/translate_pending.py")


if __name__ == "__main__":
    main()
