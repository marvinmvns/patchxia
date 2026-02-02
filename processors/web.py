import re
import os

class WebProcessor:
    def __init__(self, root_dir, glossary):
        self.root_dir = root_dir
        self.glossary = glossary
        self.web_root = os.path.join(root_dir, "main/manager-web")
        self.i18n_file = os.path.join(self.web_root, "src/i18n/zh_CN.js")
        self.target_file = os.path.join(self.web_root, "src/i18n/pt_BR.js")
        self.index_file = os.path.join(self.web_root, "src/i18n/index.js")

    def run(self):
        print(f"Processing Web Frontend at {self.web_root}...")
        if not os.path.exists(self.i18n_file):
            print(f"Error: Source file {self.i18n_file} not found.")
            return

        with open(self.i18n_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Simple regex strategy to parse the JS object
        # It assumes the format: 'key': 'value',
        
        qt_pattern = re.compile(r"'([^']+)'\s*:\s*'([^']*)'")
        
        # We will build a new content string for pt_BR
        new_lines = []
        new_lines.append("export default {")
        
        matches = qt_pattern.findall(content)
        print(f"Found {len(matches)} strings in zh_CN.js")
        
        for key, zh_text in matches:
            # Try to get translation from glossary
            pt_text = self.glossary.get("zh_CN", {}).get(zh_text)
            
            if not pt_text:
                # Fallback: maintain original or mark as TODO
                # For now, let's just keep the original as fallback or use a placeholder
                # print(f"Missing translation for: {zh_text}")
                pt_text = zh_text + " (PT)" # meaningful fallback for testing
            
            new_lines.append(f"  '{key}': '{pt_text}',")

        new_lines.append("}")
        
        with open(self.target_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(new_lines))
        
        print(f"Generated {self.target_file}")
        self.register_locale()

    def register_locale(self):
        # We need to modify src/i18n/index.js to include the new locale
        if not os.path.exists(self.index_file):
             print(f"Error: Index file {self.index_file} not found.")
             return

        with open(self.index_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if "import pt_BR from './pt_BR'" in content:
            print("Locale already registered.")
            return

        # Handle import with semicolon and variable name mismatch
        if "import zhCN from './zh_CN';" in content:
             content = content.replace("import zhCN from './zh_CN';", "import zhCN from './zh_CN';\nimport ptBR from './pt_BR';")
        elif "import zhCN from './zh_CN'" in content:
             content = content.replace("import zhCN from './zh_CN'", "import zhCN from './zh_CN'\nimport ptBR from './pt_BR'")

        # Handle messages object
        if "'zh_CN': zhCN," in content:
            content = content.replace("'zh_CN': zhCN,", "'zh_CN': zhCN,\n    'pt_BR': ptBR,")
        
        with open(self.index_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Registered pt_BR locale in index.js")

    def scan(self):
        print(f"Scanning Web Frontend at {self.web_root}...")
        if not os.path.exists(self.i18n_file):
            return {}

        with open(self.i18n_file, 'r', encoding='utf-8') as f:
            content = f.read()

        qt_pattern = re.compile(r"'([^']+)'\s*:\s*'([^']*)'")
        matches = qt_pattern.findall(content)
        
        found = {}
        for key, zh_text in matches:
            found[zh_text] = "" # Empty translation initially
            
        return found
