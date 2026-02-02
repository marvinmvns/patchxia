import os
import re
import ast

class ServerProcessor:
    def __init__(self, root_dir, glossary):
        self.root_dir = root_dir
        self.glossary = glossary
        self.server_root = os.path.join(root_dir, "main/xiaozhi-server")
        
    def run(self):
        print(f"Processing Server Backend at {self.server_root}...")
        
        # Traverse all python files
        for root, dirs, files in os.walk(self.server_root):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    self.process_file(full_path)

    def process_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Parse AST to find string literals
        try:
            tree = ast.parse(content)
        except SyntaxError:
            print(f"Syntax error in {file_path}, skipping.")
            return

        # Collect strings to replace
        replacements = {}
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant): # Python 3.8+
                if isinstance(node.value, str):
                    s = node.value
                    if self.has_chinese(s):
                        # It's a candidate
                        translation = self.get_translation(s)
                        if translation:
                            replacements[s] = translation

        if not replacements:
            return

        # Apply replacements
        # We use simple string replacement here. checking for quote styles is tricky.
        # This is the "risky" part where we might replace a key instead of a value if they are identical.
        # But for Chinese strings, collisions are low risk compared to short English words.
        
        new_content = content
        for original, translated in replacements.items():
            # We must be careful not to replace partial matches if not intended, 
            # but usually Chinese strings are unique enough.
            
            # Simple replace:
            new_content = new_content.replace(original, translated)
            
        if new_content != content:
            # Backup original
            # os.rename(file_path, file_path + ".bak") 
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated {file_path}")

    def has_chinese(self, text):
        return bool(re.search(r'[\u4e00-\u9fff]', text))

    def get_translation(self, text):
        return self.glossary.get("zh_CN", {}).get(text)

    def scan(self):
        print(f"Scanning Server Backend at {self.server_root}...")
        found = {}
        # Traverse all python files
        for root, dirs, files in os.walk(self.server_root):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    with open(full_path, 'r', encoding='utf-8') as f:
                        try:
                            content = f.read()
                            tree = ast.parse(content)
                            for node in ast.walk(tree):
                                if isinstance(node, ast.Constant):
                                    if isinstance(node.value, str):
                                        s = node.value
                                        if self.has_chinese(s):
                                            found[s] = ""
                        except Exception as e:
                            # print(f"Error scanning {file}: {e}")
                            pass
        return found
