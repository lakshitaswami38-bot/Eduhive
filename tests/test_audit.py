import ast
import glob
import re


def test_url_for_endpoints(app):
    """Audits every url_for() call in app templates and python files to ensure no broken endpoints exist."""
    endpoints = set(app.view_functions.keys())
    pattern = re.compile(r"url_for\(\s*['\"]([a-zA-Z0-9_.]+)['\"]")

    missing = set()

    for filepath in glob.glob("app/**/*", recursive=True):
        if filepath.endswith(".html"):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # Strip Jinja comments
                content = re.sub(r"\{#.*?#\}", "", content, flags=re.DOTALL)
                for ep in pattern.findall(content):
                    if ep != "static" and ep not in endpoints:
                        missing.add((ep, filepath))
        elif filepath.endswith(".py"):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                try:
                    tree = ast.parse(content, filename=filepath)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            if (isinstance(node.func, ast.Name) and node.func.id == "url_for") or (
                                isinstance(node.func, ast.Attribute) and node.func.attr == "url_for"
                            ):
                                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
                                    node.args[0].value, str
                                ):
                                    ep = node.args[0].value
                                    if ep != "static" and ep not in endpoints:
                                        missing.add((ep, filepath))
                except Exception:
                    pass

    assert not missing, f"Found broken url_for endpoints: {missing}"
