"""
Octron Devtool — one dashboard for troubleshooting and editing the project.
Run this FROM THE PROJECT FOLDER (same place as octron_cli.py) so relative
imports and the qdrant_data path resolve the same way they do for the CLI:

    streamlit run octron_devtool.py

WHAT THIS DOES:
- Diagnose tab: runs your existing octron_diagnose.run_full_diagnosis()
- Family Tree tab: same dependency scan as map_tree.py, shown inline
- System tab: checks Ollama version, GPU offload status (`ollama ps`),
  and memory DB stats (chunk count, sources, topics)
- Code Editor tab: pick any .py/.txt file in the folder, edit, save

SAFE BY DEFAULT:
- Every save makes a timestamped backup first (backups/<file>.<timestamp>.bak)
  — nothing is ever overwritten without a recovery copy sitting next to it.
- This tool only ever touches files in the folder you launch it from. It
  doesn't scan or write anywhere else on disk.
- Subprocess calls (ollama -v, ollama ps) are read-only status checks —
  nothing here restarts services or kills processes for you.

WHAT COULD BREAK:
- If you edit a file here WHILE octron_cli.py is also running, the CLI
  won't pick up the change until you restart it — Python has already
  loaded the old version into memory. Editing here doesn't hot-reload
  a running CLI session.
- Saving a file with a syntax error won't be caught until something
  tries to import it — this editor doesn't lint. If you're unsure,
  use "Diagnose" after saving; it'll flag a SYNTAX_ERROR status for
  any module that fails to parse.
- The Qdrant stats panel opens its OWN connection to ./qdrant_data as a
  separate process. Qdrant's local/embedded mode takes an EXCLUSIVE lock
  on the storage folder — it does NOT support two processes touching it
  at once, reads included. If octron_cli.py (or octron_api.py) is already
  running, clicking "Check memory stats" here will fail with a
  "storage folder already accessed by another instance" error. Close
  the other process first, or expect this tab to error out while it's
  running.
"""

import os
import re
import ast
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

import streamlit as st

PROJECT_DIR = Path(__file__).parent.resolve()
BACKUP_DIR = PROJECT_DIR / "backups"

st.set_page_config(page_title="Octron Devtool", page_icon="🛠", layout="wide")
st.title("🛠 Octron Devtool")
st.caption(f"Working directory: `{PROJECT_DIR}`")

tab_diagnose, tab_tree, tab_system, tab_editor = st.tabs(
    ["Diagnose", "Family Tree", "System", "Code Editor"]
)

# ---------------------------------------------------------------------
# Diagnose tab — reuses your existing octron_diagnose.py, no reimplementation
# ---------------------------------------------------------------------
with tab_diagnose:
    st.subheader("Self-diagnosis")
    st.caption("Runs octron_diagnose.run_full_diagnosis() — same as the `diagnose` CLI command.")
    if st.button("Run diagnosis", key="run_diag"):
        try:
            import octron_diagnose
            report = octron_diagnose.run_full_diagnosis()
            st.code(report, language=None)
        except Exception as e:
            st.error(f"Couldn't run diagnosis: {e}")
            st.caption("Common cause: launched from the wrong folder, or a module has a syntax error.")

# ---------------------------------------------------------------------
# Family Tree tab — same regex-based import scan as map_tree.py
# ---------------------------------------------------------------------
with tab_tree:
    st.subheader("Dependency map")
    st.caption("Which modules import which — same logic as map_tree.py.")
    if st.button("Scan dependencies", key="run_tree"):
        files = [f.name for f in PROJECT_DIR.glob("*.py") if f.name != "octron_devtool.py"]
        tree = {}
        for fname in files:
            tree[fname] = []
            try:
                content = (PROJECT_DIR / fname).read_text(encoding="utf-8", errors="ignore")
                imports = re.findall(r"(?:from|import)\s+([a-zA-Z0-9_]+)", content)
                for imp in imports:
                    target = f"{imp}.py"
                    if target in files and target not in tree[fname]:
                        tree[fname].append(target)
            except Exception:
                pass

        for parent, children in sorted(tree.items()):
            crown = "👑 " if parent == "octron_cli.py" else "📦 "
            st.markdown(f"**{crown}{parent}**")
            if children:
                for c in children:
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;🧬 → {c}")
            else:
                st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;🛑 no local dependencies")

# ---------------------------------------------------------------------
# System tab — Ollama version/GPU status + memory DB stats, all read-only
# ---------------------------------------------------------------------
with tab_system:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Ollama")
        if st.button("Check Ollama status", key="run_ollama"):
            try:
                version = subprocess.run(
                    ["ollama", "-v"], capture_output=True, text=True, timeout=10
                )
                st.text(version.stdout.strip() or version.stderr.strip())
            except FileNotFoundError:
                st.error("`ollama` not found on PATH.")
            except Exception as e:
                st.error(f"Version check failed: {e}")

            try:
                ps = subprocess.run(
                    ["ollama", "ps"], capture_output=True, text=True, timeout=10
                )
                output = ps.stdout.strip() or "(no model currently loaded)"
                st.code(output, language=None)
                if "100%" in output and "GPU" in output:
                    st.success("Model is fully offloaded to GPU.")
                elif "CPU" in output:
                    st.warning("Some or all layers are on CPU — check ROCm/Vulkan setup.")
            except Exception as e:
                st.error(f"`ollama ps` failed: {e}")

    with col2:
        st.subheader("Memory database")
        if st.button("Check memory stats", key="run_mem"):
            try:
                import V4octron_memory as mem
                stats = mem.memory_stats()
                st.metric("Total chunks", stats["total_chunks"])
                st.write("**Sources:**")
                for src, cnt in sorted(stats["sources"].items(), key=lambda x: -x[1]):
                    st.write(f"- {src}: {cnt}")
                st.write("**Topics:**")
                for top, cnt in sorted(stats["topics"].items(), key=lambda x: -x[1]):
                    st.write(f"- {top}: {cnt}")
            except Exception as e:
                st.error(f"Couldn't read memory stats: {e}")
                st.caption("Common cause: qdrant_data isn't in this folder, or it's locked by a running CLI session.")

# ---------------------------------------------------------------------
# Code Editor tab — edit any project file, with automatic backup on save
# ---------------------------------------------------------------------
with tab_editor:
    st.subheader("Edit a file")

    editable_files = sorted(
        [f.name for f in PROJECT_DIR.glob("*.py")] +
        [f.name for f in PROJECT_DIR.glob("*.txt")]
    )
    editable_files = [f for f in editable_files if f != "octron_devtool.py"]

    chosen = st.selectbox("File", editable_files)

    if chosen:
        filepath = PROJECT_DIR / chosen
        original_text = filepath.read_text(encoding="utf-8", errors="ignore")

        edited_text = st.text_area(
            f"Editing {chosen}", value=original_text, height=500, key=f"editor_{chosen}"
        )

        col_save, col_status = st.columns([1, 3])
        with col_save:
            save_clicked = st.button("💾 Save (with backup)", key=f"save_{chosen}")

        if save_clicked:
            if edited_text == original_text:
                st.info("No changes to save.")
            else:
                # Backup first — never overwrite without a recovery copy.
                BACKUP_DIR.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = BACKUP_DIR / f"{chosen}.{timestamp}.bak"
                shutil.copy2(filepath, backup_path)

                # Syntax-check .py files before writing, so a typo doesn't
                # silently break the module until the next import.
                if chosen.endswith(".py"):
                    try:
                        ast.parse(edited_text)
                    except SyntaxError as e:
                        st.error(f"Syntax error at line {e.lineno}: {e.msg} — NOT saved.")
                        st.stop()

                filepath.write_text(edited_text, encoding="utf-8")
                st.success(f"Saved. Backup kept at {backup_path.relative_to(PROJECT_DIR)}")
                st.caption("Restart octron_cli.py (or any running process) to pick up this change.")
