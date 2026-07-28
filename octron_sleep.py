"""
Octron Sleep Cycle
Consolidates conversation history into permanent memory at shutdown.
Extracts key facts and stores them with a distinct 'sleep_report' source tag.
"""

from datetime import datetime

import ollama

from V4octron_memory import store_memory


def run_sleep_cycle(chat_history: list, model_name: str = "dolphin-llama3"):
    """
    Analyzes the conversation history and stores important facts
    as permanent memories tagged as sleep reports.
    """
    if not chat_history:
        print("\n[SLEEP] No conversation to consolidate.")
        return

    print("\n[SLEEP CYCLE INITIATED]")
    print("Consolidating memories...")

    full_conversation = "\n".join(chat_history)

    prompt = (
        "[DIRECTIVE]: You are a memory consolidation system.\n"
        "Analyze the following conversation and extract ONLY:\n"
        "- Permanent facts stated by the Operator\n"
        "- Operator preferences or personal details\n"
        "- Decisions made or tasks completed\n"
        "- Important topics discussed\n\n"
        "Do NOT include:\n"
        "- Casual greetings or small talk\n"
        "- Questions that were already answered\n"
        "- Anything speculative or uncertain\n\n"
        f"CONVERSATION:\n{full_conversation}\n\n"
        "OUTPUT: A bulleted list of new facts to remember. "
        "If nothing new was learned, respond with exactly: NO NEW INTEL"
    )

    try:
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3},  # Low temp for factual extraction
        )

        summary = response["message"]["content"]

        if "NO NEW INTEL" not in summary.upper():
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            memory_text = f"[SLEEP REPORT {timestamp}]\n{summary}"
            stored = store_memory(
                memory_text,
                source_name="sleep_report",
                topic="intelligence",
            )
            if stored:
                print("Memory consolidated successfully.")
            else:
                print("No new unique intel to store (duplicate detected).")
        else:
            print("No new data worth storing.")

    except Exception as e:
        print(f"Sleep cycle error: {e}")
