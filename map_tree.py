"""
Octron Auto-Mapper
Reads the directory and automatically draws the code dependency family tree.
"""
import os
import re

print("\n" + "=" * 50)
print("     OCTRON ECOSYSTEM AUTOMATIC FAMILY TREE MAP")
print("=" * 50)

# 1. Scan the folder for all Python files
files = [f for f in os.listdir('.') if f.endswith('.py') and f != 'map_tree.py']

# 2. Build a family relationship dictionary
family_tree = {}
for file in files:
    family_tree[file] = []
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
            # Regex to find 'import x' or 'from x import y'
            imports = re.findall(r'(?:from|import)\s+([a-zA-Z0-9_]+)', content)
            for imp in imports:
                target_file = f"{imp}.py"
                if target_file in files and target_file not in family_tree[file]:
                    family_tree[file].append(target_file)
    except Exception:
        pass

# 3. Print the Tree out cleanly
for parent, children in family_tree.items():
    if parent == "octron_cli.py":
        print(f"👑 {parent} (The Master Core Control)")
    else:
        print(f"📦 {parent}")
        
    if not children:
        print("    └── 🛑 No sub-dependencies (Terminal Leaf)")
    for child in children:
        print(f"    └── 🧬 Inherits/Calls -> {child}")
    print("-" * 50)
