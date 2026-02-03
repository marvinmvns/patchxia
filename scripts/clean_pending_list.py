
import json
import re
import shutil
from datetime import datetime

def clean_pending_and_translations():
    pending_file = "translations/pending.json"
    translations_file = "translations/translations.json"
    
    # Backup
    shutil.copy(pending_file, pending_file + ".bak")
    shutil.copy(translations_file, translations_file + ".bak")
    
    # Code patterns to reject
    code_keywords = [
        "function", "return", "import", "export", "const", "var", "let", 
        "class", "if", "else", "try", "catch", "async", "await", "void", 
        "debugger", "console.", "window.", "document.", "=>", "DataView",
        "Uint8Array", "Promise"
    ]
    
    def is_code(text):
        # Specific structural checks
        if "${" in text: return "Contains template variable ${"
        if "//" in text and "\n" in text: return "Contains comment //"
        # if ";" in text and "\n" in text: return "Contains semicolon ;"
        
        # Keyword checks
        for kw in code_keywords:
            # Whole word check or specific context
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                return f"Contains keyword {kw}"
        return None

    def clean_dict(data_dict, dict_name):
        kept = {}
        removed = 0
        for key, entry in data_dict.items():
            original = entry.get('original', '')
            reason = is_code(original)
            if reason:
                # print(f"[{dict_name}] Removed: {original[:30]}... Reason: {reason}")
                removed += 1
            else:
                kept[key] = entry
        return kept, removed

    # Clean Pending
    with open(pending_file, 'r', encoding='utf-8') as f:
        p_data = json.load(f)
    
    p_entries = p_data.get('pending', {})
    clean_p_entries, p_removed = clean_dict(p_entries, "Pending")
    p_data['pending'] = clean_p_entries
    p_data['total_pending'] = len(clean_p_entries)
    
    with open(pending_file, 'w', encoding='utf-8') as f:
        json.dump(p_data, f, ensure_ascii=False, indent=2)
        
    print(f"Cleaned Pending: Removed {p_removed} items. Remaining: {len(clean_p_entries)}")

    # Clean Translations (Recent bad ones)
    with open(translations_file, 'r', encoding='utf-8') as f:
        t_data = json.load(f)
        
    t_entries = t_data.get('translations', {})
    
    # Also reuse the logic from clean_translations.py (braces check)
    clean_t_entries = {}
    t_removed = 0
    
    for key, entry in t_entries.items():
        original = entry.get('original', '')
        translated = entry.get('translated', '')
        
        reason = is_code(original)
        if not reason:
            # Check translation quality (keywords translated?)
            # Just relying on previous logic: if original has code keyword, it was likely bad
            pass
        
        if reason:
            t_removed += 1
        else:
            clean_t_entries[key] = entry
            
    t_data['translations'] = clean_t_entries
    t_data['total_translations'] = len(clean_t_entries)
    
    with open(translations_file, 'w', encoding='utf-8') as f:
        json.dump(t_data, f, ensure_ascii=False, indent=2)

    print(f"Cleaned Translations: Removed {t_removed} items. Remaining: {len(clean_t_entries)}")

if __name__ == "__main__":
    clean_pending_and_translations()
