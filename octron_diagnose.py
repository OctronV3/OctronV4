"""
Octron Self-Diagnosis Module
Allows Octron to inspect his own code, explain modules, and flag potential issues.
"""

import os
import ast

# Files that make up Octron's codebase
OCTRON_MODULES = {
    "CLI": "octron_cli.py",
    "Memory": "V4octron_memory.py",
    "Reasoning": "V4octron_reasoning.py",
    "Injector": "octron_injector.py",
    "Emotions": "emotion_core.py",
    "Sleep": "octron_sleep.py",
    "Firewall": "ctx_firewall.py",
    "Soulbind": "octron_soulbind.py",
    "Diagnosis": "octron_diagnose.py",
    "API": "octron_api.py",
    "Mobile UI": "octron_mobile_ui.py",
    "Devtool": "octron_devtool.py",
    "Launcher": "launch_octron.py",
}


def _read_module(filepath: str) -> str:
    """Read a module file and return its contents."""
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def _analyze_module(filepath: str) -> dict:
    """Parse a Python file and extract structure info."""
    code = _read_module(filepath)
    if code is None:
        return {"status": "MISSING", "file": filepath}

    result = {
        "status": "OK",
        "file": filepath,
        "lines": len(code.splitlines()),
        "functions": [],
        "classes": [],
        "imports": [],
        "issues": [],
    }

    try:
        tree = ast.parse(code)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                doc = ast.get_docstring(node) or "No docstring"
                result["functions"].append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "doc": doc[:80],
                    }
                )
            elif isinstance(node, ast.ClassDef):
                result["classes"].append(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        result["imports"].append(alias.name)
                else:
                    result["imports"].append(node.module or "unknown")

        # Flag potential issues
        if "except:" in code or "except Exception:" in code:
            bare_excepts = code.count("except:")
            if bare_excepts > 0:
                result["issues"].append(
                    f"Found {bare_excepts} bare except clause(s) — may hide bugs"
                )

        if "global " in code:
            result["issues"].append("Uses global variables — can cause state bugs")

        if result["lines"] > 300:
            result["issues"].append(
                f"Module is {result['lines']} lines — consider splitting"
            )

    except SyntaxError as e:
        result["status"] = "SYNTAX_ERROR"
        result["issues"].append(f"Syntax error at line {e.lineno}: {e.msg}")

    return result


def get_module_code(module_name: str) -> str:
    """Get the source code of a specific module by name."""
    # Try exact match first
    for name, filepath in OCTRON_MODULES.items():
        if module_name.lower() in name.lower() or module_name.lower() in filepath.lower():
            code = _read_module(filepath)
            if code:
                return f"=== {name} ({filepath}) ===\n\n{code}"
            return f"Module '{name}' not found at {filepath}"

    return f"Unknown module: {module_name}. Available: {', '.join(OCTRON_MODULES.keys())}"


def run_full_diagnosis() -> str:
    """Run a complete diagnostic scan of all Octron modules."""
    lines = [
        "",
        "=" * 50,
        "  OCTRON SELF-DIAGNOSIS REPORT",
        "=" * 50,
        "",
    ]

    total_lines = 0
    total_functions = 0
    total_issues = 0
    missing = []

    for name, filepath in OCTRON_MODULES.items():
        analysis = _analyze_module(filepath)

        if analysis["status"] == "MISSING":
            missing.append(name)
            lines.append(f"  [{name}] {filepath} — MISSING")
            continue

        total_lines += analysis["lines"]
        total_functions += len(analysis["functions"])
        total_issues += len(analysis["issues"])

        status_icon = "OK" if not analysis["issues"] else f"{len(analysis['issues'])} ISSUE(S)"
        lines.append(f"  [{name}] {filepath}")
        lines.append(f"    Status: {status_icon}")
        lines.append(f"    Lines: {analysis['lines']} | Functions: {len(analysis['functions'])}")

        if analysis["functions"]:
            func_names = [f["name"] for f in analysis["functions"]]
            lines.append(f"    Functions: {', '.join(func_names)}")

        if analysis["issues"]:
            for issue in analysis["issues"]:
                lines.append(f"    >> {issue}")

        lines.append("")

    # Summary
    lines.append("-" * 50)
    lines.append("  SUMMARY")
    lines.append(f"  Total modules: {len(OCTRON_MODULES)}")
    lines.append(f"  Active: {len(OCTRON_MODULES) - len(missing)}")
    if missing:
        lines.append(f"  Missing: {', '.join(missing)}")
    lines.append(f"  Total lines of code: {total_lines}")
    lines.append(f"  Total functions: {total_functions}")
    lines.append(f"  Total issues flagged: {total_issues}")
    lines.append("-" * 50)

    # Dependency check
    lines.append("\n  DEPENDENCY CHECK")
    deps = ["ollama", "qdrant_client", "tqdm"]

    for dep in deps:
        try:
            __import__(dep)
            lines.append(f"    {dep}: INSTALLED")
        except ImportError:
            lines.append(f"    {dep}: MISSING (required)")

    # PDF support has two independent paths, each needing a SPECIFIC package.
    # A bare `import pdfminer` can succeed even with the wrong (legacy,
    # non-.six) package installed, which has no `.high_level` submodule —
    # so check the actual entry point each module uses, not just the name.
    try:
        from pdfminer.high_level import extract_text  # noqa: F401
        lines.append("    pdfminer.six: INSTALLED (PDF injection via octron_injector.py OK)")
    except ImportError:
        lines.append(
            "    pdfminer.six: MISSING (optional — needed for octron_injector.py PDF support; "
            "if `import pdfminer` succeeds elsewhere, you likely have the legacy `pdfminer` "
            "package instead — run `pip uninstall pdfminer` then `pip install pdfminer.six`)"
        )

    try:
        __import__("PyPDF2")
        lines.append("    PyPDF2: INSTALLED (PDF soulbind via octron_soulbind.py OK)")
    except ImportError:
        lines.append("    PyPDF2: MISSING (optional — needed for octron_soulbind.py)")

    # Mobile/devtool stack — not needed to run octron_cli.py itself.
    mobile_deps = ["fastapi", "uvicorn", "pydantic", "streamlit", "requests"]
    for dep in mobile_deps:
        try:
            __import__(dep)
            lines.append(f"    {dep}: INSTALLED")
        except ImportError:
            lines.append(
                f"    {dep}: MISSING (optional — needed for octron_api.py / "
                "octron_mobile_ui.py / octron_devtool.py)"
            )

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(run_full_diagnosis())
