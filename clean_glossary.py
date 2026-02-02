import json
import os
import re

GLOSSARY_PATH = "translation_patch/glossary.json"

def is_likely_code(text):
    # If it has multiple lines, semicolons, and common code patterns, it's likely code
    if len(text) > 200:
        return True
    if "return " in text or "public " in text or "private " in text or "String " in text:
        if ";" in text or "{" in text:
            return True
    return False

def clean_glossary():
    if not os.path.exists(GLOSSARY_PATH):
        print("Glossary not found")
        return

    with open(GLOSSARY_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    zh_cn = data.get("zh_CN", {})
    cleaned_zh_cn = {}
    removed_count = 0
    
    for key, val in zh_cn.items():
        if is_likely_code(key):
            removed_count += 1
            continue
        cleaned_zh_cn[key] = val
    
    data["zh_CN"] = cleaned_zh_cn
    
    with open(GLOSSARY_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Removed {removed_count} likely code/garbage entries from glossary.")

if __name__ == "__main__":
    clean_glossary()
