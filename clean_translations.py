
import json
import re
import shutil
from datetime import datetime

def clean_translations(file_path):
    print(f"Cleaning {file_path}...")
    
    # Backup
    backup_path = file_path + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(file_path, backup_path)
    print(f"Backup created at {backup_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    translations = data.get('translations', {})
    
    kept = {}
    removed_count = 0
    
    keywords_to_preserve = [
        "async", "await", "def", "class", "return", "import", "from", 
        "try", "except", "finally", "if", "else", "elif", "while", "for", 
        "in", "is", "not", "and", "or", "None", "True", "False", "lambda",
        "global", "nonlocal", "assert", "del", "pass", "break", "continue",
        "yield", "raise", "with", "as"
    ]
    
    bad_map = {
        "None": "Nenhum",
        "async": "assíncrono",
        "await": "aguarde",
        "return": "retornar",
        "class": "classe",
        "import": "importar",
        "False": "falso",
        "True": "verdadeiro",
        "try": "tente",
        "except": "exceto"
    }

    garbage_substrs = ["sconhecido", "exemploOKEN"]

    for key, entry in translations.items():
        original = entry.get('original', '')
        translated = entry.get('translated', '')
        
        is_bad = False
        reason = ""

        # Check 0: Garbage substrings
        if not is_bad:
            for garbage in garbage_substrs:
                if garbage in translated and garbage not in original:
                    is_bad = True
                    reason = f"Contains garbage '{garbage}'"
                    break

        # Check 1: Explicit bad Portuguese translations of keywords
        if not is_bad:
            for en_kw, pt_bad in bad_map.items():
                 if en_kw in original and pt_bad in translated:
                     is_bad = True
                     reason = f"Translates keyword {en_kw} -> {pt_bad}"
                     break
        
        # Check 2: Missing keywords (Code Corruption)
        if not is_bad:
            for kw in keywords_to_preserve:
                # Use regex to find whole word matches
                if re.search(r'\b' + re.escape(kw) + r'\b', original):
                    if not re.search(r'\b' + re.escape(kw) + r'\b', translated):
                        is_bad = True
                        reason = f"Missing keyword '{kw}' in translation"
                        break
        
        # Check 3: Structure mismatches (Braces, Brackets, Parens)
        # This is very effective for f-strings and code blocks
        if not is_bad:
            chars = ['{', '}', '[', ']', '(', ')']
            for char in chars:
                if original.count(char) != translated.count(char):
                    is_bad = True
                    reason = f"Structure mismatch: Count of '{char}' differs (Orig: {original.count(char)}, Trans: {translated.count(char)})"
                    break

        if is_bad:
            removed_count += 1
            # print(f"Removing {key[:8]}: {reason}")
        else:
            kept[key] = entry

    data['translations'] = kept
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Finished. Removed {removed_count} entries. Remaining: {len(kept)}")

if __name__ == "__main__":
    clean_translations("translations/translations.json")
