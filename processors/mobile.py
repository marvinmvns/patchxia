import os
import re

class MobileProcessor:
    def __init__(self, root_dir, glossary):
        self.root_dir = root_dir
        self.glossary = glossary
        self.mobile_root = os.path.join(root_dir, "main/manager-mobile")
        self.i18n_file = os.path.join(self.mobile_root, "src/i18n/zh_CN.ts")
        self.target_file = os.path.join(self.mobile_root, "src/i18n/pt_BR.ts")
        self.index_file = os.path.join(self.mobile_root, "src/i18n/index.ts")

    def run(self):
        print(f"Processing Mobile App at {self.mobile_root}...")
        if not os.path.exists(self.i18n_file):
            return

        with open(self.i18n_file, 'r', encoding='utf-8') as f:
            content = f.read()

        qt_pattern = re.compile(r"'([^']+)'\s*:\s*'([^']*)'")
        new_lines = ["export default {"]
        matches = qt_pattern.findall(content)
        for key, zh_text in matches:
            translation = self.glossary.get("zh_CN", {}).get(zh_text)
            pt_text = translation if translation else zh_text + " (PT)"
            new_lines.append(f"  '{key}': '{pt_text}',")
        new_lines.append("}")

        with open(self.target_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(new_lines))
        print(f"Generated {self.target_file}")
        self.register_locale()

    def register_locale(self):
        if not os.path.exists(self.index_file):
             return
        with open(self.index_file, 'r', encoding='utf-8') as f:
            content = f.read()
        if "import ptBR from './pt_BR'" in content:
            return
        
        content = content.replace("import zhCN from './zh_CN'", "import zhCN from './zh_CN'\nimport ptBR from './pt_BR'")
        content = content.replace("'zh_CN': zhCN,", "'zh_CN': zhCN,\n    'pt_BR': ptBR,")
        
        with open(self.index_file, 'w', encoding='utf-8') as f:
            f.write(content)

    def scan(self):
        if not os.path.exists(self.i18n_file):
            return {}
        with open(self.i18n_file, 'r', encoding='utf-8') as f:
            content = f.read()
        qt_pattern = re.compile(r"'([^']+)'\s*:\s*'([^']*)'")
        matches = qt_pattern.findall(content)
        return {v: "" for k, v in matches}

