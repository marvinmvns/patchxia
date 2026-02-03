# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A patch system that translates the [xiaozhi-esp32-server](https://github.com/xiaozhi-esp32-server) project from Chinese/English into Brazilian Portuguese. It does **not** live inside that project — it is applied *onto* a local clone of it at runtime.

## Key commands

```bash
# Simulate a patch run without modifying anything
./apply-patch.sh --dry-run

# Apply translations (incremental by default — only new strings)
./apply-patch.sh

# Force re-translate every string
./apply-patch.sh --full

# Translate pending strings via MyMemory/Google APIs
python3 scripts/translate_pending.py

# Export pending strings to CSV for manual review
python3 scripts/translate_pending.py --export-csv

# Import manually-translated CSV back into pending.json
python3 scripts/translate_pending.py --import-csv pending_translated.csv

# Validate translated code syntax (Python / JSON / YAML)
./apply-patch.sh --validate

# Roll back to a previous backup
./apply-patch.sh --rollback

# Run the test suite (creates an isolated test project)
bash tests/test_translation.sh

# Remove garbage / code-like patterns from pending & translations JSONs
python3 scripts/clean_pending_list.py

# Quality-check translations.json for bad patterns
python3 clean_translations.py

# Revert any xiaozhi source files that have syntax errors (uses git)
python3 revert_broken.py
```

## Docker mode — live container patches

The Docker mode patches running containers directly (DB + compiled web assets) in addition to source files. Requires all 4 xiaozhi containers running.

```bash
# Analyse what still needs translation (server files, web JS, MySQL tables)
python3 scripts/extract_docker.py
python3 scripts/extract_docker.py --save        # persist to extractions/summary.json
python3 scripts/extract_docker.py --db-only     # MySQL tables only

# Patch MySQL default data (sys_params, sys_dict_data, ai_model_provider, etc.)
python3 scripts/patch_database.py               # apply + auto-translate via API
python3 scripts/patch_database.py --dry-run     # preview only
python3 scripts/patch_database.py --no-api      # use local DB only, no API calls

# Patch compiled JS bundles inside the web container
python3 scripts/patch_web_assets.py             # apply + auto-translate via API
python3 scripts/patch_web_assets.py --dry-run   # preview only
python3 scripts/patch_web_assets.py --no-api    # use local DB only

# Full Docker orchestration via apply-patch.sh
./apply-patch.sh --docker                       # source + DB + web (auto-translate)
./apply-patch.sh --docker --use-llm             # same, with LLM fallback for source files
./apply-patch.sh --docker --dry-run             # preview everything
./apply-patch.sh --extract                      # analysis only (no writes)
```

### What gets translated in each layer

| Layer | Script | Tables / Files | Intentionally skipped |
|---|---|---|---|
| Source files | `translator.py` via `apply-patch.sh` | `.py .yaml .yml .json .sh .md .txt` in the project tree | `node_modules`, `.git`, `__pycache__` |
| MySQL | `patch_database.py` | `sys_params`, `sys_dict_data`, `ai_model_provider`, `ai_model_config`, `ai_agent_template` | `ai_agent_template.system_prompt` (LLM prompt), keys/secrets/URLs, `xiaozhi` & `system-web.menu` JSON configs |
| Web JS | `patch_web_assets.py` | All `*.js` under `/usr/share/nginx/html` in the web container | URLs, file paths, code fragments, strings < 2 or > 500 chars |

### MySQL 9.x quirks

MySQL 9.6 `JSON_ARRAYAGG` double-escapes newlines and quotes in TEXT columns, and outputs `base64:type15:…` for binary expressions. Workarounds applied in the scripts:
- `sys_params`: excluded `xiaozhi` and `system-web.menu` params (contain embedded JSON) via `NOT IN`
- `ai_model_config.remark`: uses `HEX(remark)` in the query and decodes in Python to avoid broken JSON serialization

### Docker patch persistence

Web JS patches are **ephemeral** — they are lost if the container is recreated (e.g. after `docker pull` + restart). Run `patch_web_assets.py` again after any container recreation. MySQL UPDATE statements are durable.

No external Python packages are required — everything uses the standard library. `jq` must be installed for `apply-patch.sh`.

## Architecture overview

```
apply-patch.sh                  ← CLI entry point; orchestrates backup → translate → validate
│
├── scripts/translator.py       ← Core engine (called by apply-patch.sh)
│     ├── TranslationDatabase   ← Load/save translations.json & pending.json
│     ├── TranslatorService     ← API calls (MyMemory, Google Translate)
│     ├── FileProcessor         ← Regex extraction of Chinese strings, safe substitution
│     └── PatchTranslator       ← Top-level orchestration class
│
├── scripts/translate_pending.py    ← Batch-translate pending.json via APIs (ThreadPoolExecutor, 4 workers)
├── scripts/translate_pending_group.py ← Simpler single-threaded pending translator
├── scripts/clean_pending_list.py      ← Strip code-like garbage from pending.json
├── scripts/extract_docker.py          ← Scan live containers for untranslated strings (analysis)
├── scripts/patch_database.py          ← Patch MySQL tables via docker exec (DBPatcher class)
├── scripts/patch_web_assets.py        ← Patch compiled JS bundles via docker cp
├── clean_translations.py             ← Quality audit of translations.json
└── revert_broken.py                  ← git-checkout any file that fails py_compile
```

### Translation data flow

1. `FileProcessor.find_chinese_strings()` scans source files with regex for Chinese text (triple-quoted strings, single-line strings, comments, HTML/Vue templates, backtick strings).
2. Each extracted string is hashed (first 12 chars of MD5) and looked up in `translations.json`.
3. **Hit** → substitution is queued. **Miss** → entry is added to `pending.json`; if `--use-llm` is set, an API call is attempted immediately.
4. Substitutions are applied **in reverse index order** so that byte offsets remain valid.
5. After all files are patched, `apply-patch.sh --validate` checks Python/JSON/YAML syntax.

### Translation database schema

`translations.json` keys are 12-character MD5 hashes of the original string. Each value contains: `original`, `translated`, `source_lang`, `translator` (manual | mymemory | google), `file_path`, `line_number`, `context`, `date_added`, `verified`.

`pending.json` has the same hash-key structure but stores untranslated strings with an empty or suggested `suggested_translation`.

### Safety & rate-limiting conventions

- Backups are created automatically before any file modification (timestamped folders under `backups/`).
- API calls have a 0.5 s minimum delay; `translate_pending.py` uses a circuit breaker that disables MyMemory after 5 consecutive HTTP 429 errors.
- `pending.json` is saved incrementally every 10 translations to avoid data loss on interruption.
- `verify_interpolation()` ensures Python f-string / template placeholders survive translation.

## Common pitfalls

- **Backup files in `translations/`** (`*.bak`, `*.backup_*`) are local-only artifacts — they are not tracked by git and should not be committed.
- `scripts/__pycache__/` and `logs/` are in `.gitignore`; don't worry about them.
- The test suite (`tests/test_translation.sh`) creates and cleans up a temporary `tests/test_project/` directory — it is also gitignored.
- `dry_run_improved.txt` and `dry_run_output.txt` are ad-hoc output logs, not part of the automation.
