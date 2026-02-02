import os
import re

class ApiProcessor:
    def __init__(self, root_dir, glossary):
        self.root_dir = root_dir
        self.glossary = glossary
        self.api_root = os.path.join(root_dir, "main/manager-api")

    def run(self):
        print(f"Processing Java API at {self.api_root}...")
        for root, dirs, files in os.walk(self.api_root):
            for file in files:
                if file.endswith(".java") or file.endswith(".properties"):
                    self.process_file(os.path.join(root, file))

    def process_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Simple regex for Java strings or Properties
        # For Java: "string"
        # For Properties: key=value
        
        found = False
        new_content = content
        
        # This is a bit brute force for Java, but user wants it all.
        # We can try to find quotes with Chinese characters.
        matches = re.findall(r'"([^"]*[\u4e00-\u9fff][^"]*)"', content)
        for original in set(matches):
            translation = self.glossary.get("zh_CN", {}).get(original)
            if translation:
                new_content = new_content.replace(f'"{original}"', f'"{translation}"')
                found = True

        if found:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated {file_path}")

    def scan(self):
        print(f"Scanning Java API at {self.api_root}...")
        found = {}
        for root, dirs, files in os.walk(self.api_root):
            for file in files:
                if file.endswith(".java") or file.endswith(".properties"):
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                        try:
                            content = f.read()
                            matches = re.findall(r'"([^"]*[\u4e00-\u9fff][^"]*)"', content)
                            for m in matches:
                                found[m] = ""
                        except:
                            pass
        return found
