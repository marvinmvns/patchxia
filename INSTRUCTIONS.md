# Xiaozhi Server Translation Patch (Brazilian Portuguese)

This patch system allows you to translate the Xiaozhi ESP32 Server to Brazilian Portuguese (pt-BR).

## Directory Structure
- `translation_patch/`: Contains the patch engine and glossary.
  - `manager.py`: The main CLI tool.
  - `glossary.json`: The dictionary containing translations.
  - `processors/`: Logic for patching Frontend and Backend.

## How to use

### 1. Apply Translations
To apply the existing translations (from `glossary.json`) to the codebase:

```bash
python translation_patch/manager.py apply
```

This will:
- Generate `main/manager-web/src/i18n/pt_BR.js` with translations.
- Update `main/manager-web/src/i18n/index.js` to enable the new locale.
- Scan `main/xiaozhi-server/` Python files and replace known Chinese strings with Portuguese ones.

### 2. Add New Translations
If you want to improve the translation:
1. Run scan to find new strings:
   ```bash
   python translation_patch/manager.py scan
   ```
2. Edit `translation_patch/glossary.json`. Find entries marked as `"TODO"` (or empty strings) and add your translation.
3. Run `apply` again to update the code.

## Notes
- The Python backend translation uses **direct string replacement**. It is designed to be safe but always verify if the server starts correctly after patching.
- Original files are modified directly. If you need to revert, use `git checkout .`.
