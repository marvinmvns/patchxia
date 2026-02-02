import sys
import os
import json
import argparse
from processors.web import WebProcessor
from processors.server import ServerProcessor
from processors.mobile import MobileProcessor
from processors.api import ApiProcessor

GLOSSARY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glossary.json")

def load_glossary():
    if not os.path.exists(GLOSSARY_FILE):
        return {"zh_CN": {}}
    with open(GLOSSARY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_glossary(data):
    with open(GLOSSARY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    parser = argparse.ArgumentParser(description="Xiaozhi Server Translation Patch Tool")
    parser.add_argument("action", choices=["apply", "scan"], help="Action to perform")
    
    args = parser.parse_args()
    
    root_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(root_dir)
    
    glossary = load_glossary()
    
    processors = [
        WebProcessor(repo_root, glossary),
        ServerProcessor(repo_root, glossary),
        MobileProcessor(repo_root, glossary),
        ApiProcessor(repo_root, glossary)
    ]
    
    if args.action == "apply":
        print("Applying translations to all components...")
        for p in processors:
            p.run()
        print("Done.")
        
    elif args.action == "scan":
        print("Scanning for strings in all components...")
        all_strings = {}
        for p in processors:
            strings = p.scan()
            all_strings.update(strings)
        
        if "zh_CN" not in glossary:
            glossary["zh_CN"] = {}
            
        new_entries = 0
        for s in all_strings:
            if s not in glossary["zh_CN"]:
                glossary["zh_CN"][s] = "TODO"
                new_entries += 1
        
        save_glossary(glossary)
        print(f"Scan complete. Added {new_entries} new entries to glossary.json")
        
if __name__ == "__main__":
    main()
