
import sys
import os
import time
from translator import TranslationDatabase, TranslatorService, TranslationEntry
from datetime import datetime

def translate_pending():
    project_path = "/home/bigfriend/Documentos/bora/translation_patch"
    sys.path.append(os.path.join(project_path, "scripts"))
    
    db = TranslationDatabase("translations/translations.json", "translations/pending.json")
    service = TranslatorService()
    
    pending_items = list(db.pending.items())
    print(f"Found {len(pending_items)} pending items.")
    
    count = 0
    for hash_key, entry in pending_items:
        original = entry.original
        print(f"Translating ({count+1}/{len(pending_items)}): {original[:50]}...")
        
        # Translate
        translated, method = service.translate(original, 'zh')
        
        if translated:
            print(f"  -> {translated[:50]}")
            
            # Add to translations
            new_entry = TranslationEntry(
                original=original,
                translated=translated,
                source_lang='zh',
                translator=method,
                file_path=entry.file_path,
                line_number=entry.line_number,
                context=entry.context,
                date_added=datetime.now().isoformat(),
                verified=False
            )
            db.add_translation(new_entry)
            
            # Save every 10 items
            if count % 10 == 0:
                db.save()
        else:
            print("  -> Failed")
            
        count += 1
        # Sleep to be nice to API
        time.sleep(1)

    db.save()
    print("Done.")

if __name__ == "__main__":
    translate_pending()
