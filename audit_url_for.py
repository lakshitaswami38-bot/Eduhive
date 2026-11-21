import ast
import glob
import re
from app import create_app
from config import TestConfig

app = create_app(TestConfig)
endpoints = set(app.view_functions.keys())

pattern = re.compile(r"url_for\(\s*['\"]([a-zA-Z0-9_.]+)['\"]")

missing = set()
found_total = 0

for filepath in glob.glob('app/**/*', recursive=True):
    if filepath.endswith('.html'):
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # Strip Jinja comments
            content = re.sub(r'\{#.*?#\}', '', content, flags=re.DOTALL)
            for ep in pattern.findall(content):
                found_total += 1
                if ep != 'static' and ep not in endpoints:
                    missing.add((ep, filepath))
    elif filepath.endswith('.py'):
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            try:
                tree = ast.parse(content, filename=filepath)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if (isinstance(node.func, ast.Name) and node.func.id == 'url_for') or \
                           (isinstance(node.func, ast.Attribute) and node.func.attr == 'url_for'):
                            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                                ep = node.args[0].value
                                found_total += 1
                                if ep != 'static' and ep not in endpoints:
                                    missing.add((ep, filepath))
            except Exception:
                pass

print(f"Total active url_for calls checked: {found_total}")
print(f"Missing endpoints ({len(missing)}):")
for ep, fp in sorted(missing):
    print(f"  {ep} -> referenced in {fp}")

if missing:
    exit(1)
