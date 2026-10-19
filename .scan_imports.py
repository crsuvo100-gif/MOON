import ast
import os

root = "/home/meow/Projects/MOON-AI"
py_files = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in (".git", ".ori", "__pycache__", ".pytest_cache", ".pre_commit_checkpoint")]
    for f in filenames:
        if f.endswith(".py"):
            py_files.append(os.path.join(dirpath, f))

imports = {}
for path in py_files:
    try:
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if mod:
                    imports.setdefault(mod, set()).add(path)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.setdefault(node.module, set()).add(path)

for mod in sorted(imports):
    print(mod, "->", len(imports[mod]), "files")
print("TOTAL FILES:", len(py_files))
