
import os
import subprocess

def find_and_revert_broken_files(root_dir):
    print(f"Scanning {root_dir}...")
    broken_files = []
    
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                try:
                    subprocess.check_call(["python3", "-m", "py_compile", full_path], 
                                          stdout=subprocess.DEVNULL, 
                                          stderr=subprocess.DEVNULL)
                except subprocess.CalledProcessError:
                    print(f"Syntax Error: {full_path}")
                    broken_files.append(full_path)

    if broken_files:
        print(f"Found {len(broken_files)} broken files. Reverting...")
        for file in broken_files:
            try:
                subprocess.check_call(["git", "checkout", file], cwd=root_dir)
                print(f"Reverted: {file}")
            except Exception as e:
                print(f"Failed to revert {file}: {e}")
    else:
        print("No broken files found.")

if __name__ == "__main__":
    find_and_revert_broken_files("/home/bigfriend/Documentos/bora/xiaozhi-esp32-server")
