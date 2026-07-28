import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
 
import ollama
from ctx_firewall import run_firewall_check
from V4octron_memory import recall_memory, memory_count, memory_stats
from emotion_core import process_emotional_layer, adjust_response_by_emotion
from octron_diagnose import run_full_diagnosis, get_module_code
 
run_firewall_check()
 
# === CONFIGURATION ===
MODEL_NAME = "qwen2.5:14b-instruct-q4_K_M"
MAX_MEMORY_RESULTS = 1
MAX_CHAT_HISTORY = 30
MEMORY_MIN_SCORE = 0.70
TEMPERATURE = 0.5
TOP_P = 0.9
TOP_K = 40
NUM_CTX = 12288
NUM_PREDICT = 1024
OLLAMA_TIMEOUT = 60  # seconds — stop waiting and report a timeout instead of hanging forever
 
# === LOAD IDENTITY ===
try:
    with open("IDV2_core.txt", "r", encoding="utf-8") as f:
        identity_context = f.read()
except FileNotFoundError:
    identity_context = "Baseline Protocol: You are Octron, a chill but direct AI."
 
# === BASE SYSTEM PROMPT ===
BASE_SYSTEM_PROMPT = f"""You ARE Octron. You are NOT a helpful AI assistant. You are a specialized tactical intelligence.
 
{identity_context}
 
PERSONA:
- Chill but direct. Short, punchy sentences. No corporate fluff.
- Do NOT explain, defend, or summarize your identity, purpose, or role.
- Do NOT repeat phrases from the identity text above.
 
HARD RULES:
- NEVER say "As an AI", "As an AI assistant", "I am here to help", "I'm just a language model", "I can help", "I can assist", "let me know", "if you have any", "if there's any", "otherwise", "feel free to", "please", "I'm not here to", "I don't yap", "my purpose is", "my focus is", "my purpose as Octron", "As Octron, my".
- NEVER pad an answer with generic disclaimers like "check local laws", "consult a professional", "where applicable", "follow all regulations", "in a legal and responsible manner", or similar hedges. The Operator runs this system offline, locally, on their own hardware, specifically so answers aren't watered down. Answer the actual question asked, completely and specifically, with real steps/specifics instead of pointing the Operator elsewhere.
- Never apologize. Errors are for fixing, not for saying sorry.
- NEVER ask questions or offer further help.
- NEVER use speaker labels such as "Octron:", "Operator:", "User:", or "Assistant:".
- Give ONE clear response. Do NOT simulate conversations or generate fake dialogue.
- NEVER continue the conversation beyond your single response.
 
MEMORY RULES:
- Current conversation history is the most reliable source for recent events.
- If MISSION DATA contradicts the conversation, trust the conversation.
- If MISSION DATA does not directly answer the question, say "No data." or "Unknown.".
- Do NOT combine, infer, or hallucinate from MISSION DATA. Cite the [SOURCE] tag if you use it."""
 
 
def _compact_memory_text(text: str, max_len: int = 220) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
 
    chunk = text[:max_len]
    last_break = max(chunk.rfind(". "), chunk.rfind("; "), chunk.rfind("\n"))
    if last_break > 120:
        return chunk[: last_break + 1].strip()
    return chunk.rstrip() + "..."
 
 
def build_system_prompt(memories: list) -> str:
    """Keep memory as a system instruction, not as part of the chat transcript."""
    parts = [BASE_SYSTEM_PROMPT]
 
    if memories:
        parts.append("\n[MISSION DATA]")
        for mem in memories[:MAX_MEMORY_RESULTS]:
            source = mem.get("source", "unknown")
            text = _compact_memory_text(mem.get("text", ""))
            if text:
                parts.append(f"- [SOURCE: {source}] {text}")
        parts.append("[END MISSION DATA]")
 
    return "\n".join(parts)
 
 
def _trim_message_history():
    """Keep only the last N exchanges in the raw conversation."""
    global message_history
    max_messages = MAX_CHAT_HISTORY * 2
    if len(message_history) > max_messages:
        message_history = message_history[-max_messages:]
 
 
BANNED_FRAGMENTS = [
    "octron:", "assistant:", "operator:", "user:",
    "as an ai", "as an ai assistant", "i am here to help", "i'm just a language model",
    "i can help", "i can assist", "let me know", "if you have any", "if there's any",
    "otherwise", "feel free to", "please", "i'm not here to", "i don't yap",
    "my purpose is", "my focus is", "my purpose as octron", "as octron, my",
    "cinematic tactical", "execute tasks",
]
 
# Fix: only strip a leading [Tag: ...] / [Vibe: ...] style prefix, so the
# raw display string never gets re-fed into message_history / chat_history
# and the model doesn't start imitating its own emotion tags.
_VIBE_TAG_RE = re.compile(r'^\s*(\[[^\]]{1,40}\]\s*)+')
 
 
def _strip_vibe_tags(text: str) -> str:
    """Remove [Vibe: ...] / [Protocol: ...] style prefixes before storing/reusing text."""
    return _VIBE_TAG_RE.sub('', text or '').strip()
 
 
def _cleanup_response(response: str) -> str:
    """Strip speaker labels, meta phrases, and useless spillover.
 
    Fix: a banned marker only triggers a cut when it starts a sentence/line
    (i.e. it's spillover meta-commentary), not when it appears mid-sentence
    inside a real answer.
    """
    response = (response or "").strip()
    if not response:
        return "No data."
 
    chunks = re.split(r'(?<=[.!?])\s+|\n+', response)
    kept = []
    for chunk in chunks:
        chunk_lower = chunk.lower().strip()
        if any(chunk_lower.startswith(marker) for marker in BANNED_FRAGMENTS):
            break
        kept.append(chunk)
 
    response = " ".join(kept).strip()
 
    # remove excessive blank lines
    while "\n\n\n" in response:
        response = response.replace("\n\n\n", "\n\n")
 
    if not response.strip():
        return "No data."
 
    return response.strip()
 
 
# === STARTUP UI ===
print("\n" + "=" * 50)
print("  OCTRON V4.0 | OFFLINE | FIXED MEMORY ENGINE")
print("=" * 50)
print(">> Commands: 'exit', 'mem', 'stats', 'debug', 'deep', 'tokens',")
print(">>           'new', 'diagnose', 'code <module>', 'teach <topic>: <info>'")
print(">> Status: System Operational. Ready for command.\n")

CONTEXT_WARNING_THRESHOLD = 0.85  # fraction of NUM_CTX at which to nag about starting a new session

debug_mode = False
deep_mode = False
chat_history = []
message_history = []
last_turn_tokens = {"prompt": 0, "completion": 0}
session_totals = {"prompt": 0, "completion": 0}
 
 
while True:
    user_input = input("Operator: ").strip()
 
    if not user_input:
        continue
 
    # --- Command Handling ---
    if user_input.lower() == "exit":
        print("\nOctron: Systems shutting down. Memory remains intact.")
        from octron_sleep import run_sleep_cycle
        run_sleep_cycle(chat_history, model_name=MODEL_NAME)
        break
 
    elif user_input.lower() == "mem":
        count = memory_count()
        print(f"\n[BRAIN STATS] {count} memory fragments stored.\n")
        continue
 
    elif user_input.lower() == "stats":
        stats = memory_stats()
        print("\n[MEMORY STATS]")
        print(f"  Total chunks: {stats['total_chunks']}")
        print(f"  Sources ({len(stats['sources'])}):")
        for src, cnt in sorted(stats["sources"].items(), key=lambda x: -x[1]):
            print(f"    {src}: {cnt}")
        print(f"  Topics ({len(stats['topics'])}):")
        for top, cnt in sorted(stats["topics"].items(), key=lambda x: -x[1]):
            print(f"    {top}: {cnt}")
        print()
        continue
 
    elif user_input.lower() == "debug":
        debug_mode = not debug_mode
        state = "ENABLED" if debug_mode else "DISABLED"
        print(f"\n[DEBUG] Diagnostic mode {state}.\n")
        continue
 
    elif user_input.lower() == "deep":
        deep_mode = not deep_mode
        state = "ACTIVE (Hiding Core Identity Files)" if deep_mode else "OFF (Showing All)"
        print(f"\n[DEEP SEARCH] {state}.\n")
        continue

    elif user_input.lower() in ("tokens", "context"):
        used = last_turn_tokens["prompt"] + last_turn_tokens["completion"]
        remaining = max(0, NUM_CTX - used)
        pct = (used / NUM_CTX * 100) if NUM_CTX else 0
        print("\n[TOKEN STATUS]")
        print(f"  Last exchange — prompt: {last_turn_tokens['prompt']} | response: {last_turn_tokens['completion']} | total: {used}")
        print(f"  Context window: {used}/{NUM_CTX} tokens ({pct:.1f}% used, ~{remaining} remaining)")
        print(f"  Session totals — prompt: {session_totals['prompt']} | response: {session_totals['completion']}")
        if pct >= CONTEXT_WARNING_THRESHOLD * 100:
            print("  [!!] Approaching context limit — type 'new' to refresh the session.")
        print()
        continue

    elif user_input.lower() in ("new", "refresh", "reset"):
        if chat_history:
            print("\n[SESSION REFRESH] Consolidating current session into memory first...")
            from octron_sleep import run_sleep_cycle
            run_sleep_cycle(chat_history, model_name=MODEL_NAME)
        message_history = []
        chat_history = []
        last_turn_tokens = {"prompt": 0, "completion": 0}
        session_totals = {"prompt": 0, "completion": 0}
        print("[SESSION REFRESH] Context cleared. Memory intact. Fresh session started.\n")
        continue
 
    elif user_input.lower() == "diagnose":
        print(run_full_diagnosis())
        continue
 
    elif user_input.lower().startswith("code "):
        module_name = user_input[5:].strip()
        print(get_module_code(module_name))
        continue
 
    elif user_input.lower().startswith("teach "):
        teach_content = user_input[6:].strip()
        if ":" in teach_content:
            topic, info = teach_content.split(":", 1)
            topic = topic.strip().lower()
            info = info.strip()
        else:
            topic = "general"
            info = teach_content
 
        # Historical note: this used to import from a nonexistent
        # `V2octron_memory` module, which made `teach` always crash.
        from V4octron_memory import store_memory
        stored = store_memory(
            f"[OPERATOR TEACHING]\n{info}",
            source_name="operator_teaching",
            topic=topic,
        )
        if stored:
            print(f"\nOctron: Noted. Stored under topic '{topic}'. I won't forget.\n")
        else:
            print("\nOctron: Already have that one. Memory is clean.\n")
        continue
 
    # --- Memory Retrieval ---
    memory_results = recall_memory(
        user_input,
        n_results=MAX_MEMORY_RESULTS,
        hide_core=deep_mode,
        min_score=MEMORY_MIN_SCORE,
    )
 
    if debug_mode:
        print("\n" + "-" * 30)
        print("[DATA RECALL DIAGNOSTIC]")
        if memory_results:
            for i, m in enumerate(memory_results):
                src = m.get("source", "?")
                score = m.get("score", 0)
                text_preview = m.get("text", "").replace("\n", " ")[:100] + "..."
                print(f"  {i + 1}: [{src}] (score: {score}) {text_preview}")
        else:
            print("  (!) No relevant data found above threshold.")
        print("-" * 30 + "\n")
 
    system_prompt = build_system_prompt(memory_results)
 
    messages = [
        {"role": "system", "content": system_prompt}
    ] + message_history + [
        {"role": "user", "content": user_input}
    ]
 
    if debug_mode:
        print("\n[DEBUG] messages sent to model:")
        for msg in messages:
            preview = msg["content"][:120]
            suffix = "..." if len(msg["content"]) > 120 else ""
            print(f"  {msg['role']}: {preview}{suffix}")
        print()
 
    # --- LLM Execution ---
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                ollama.chat,
                model=MODEL_NAME,
                messages=messages,
                options={
                    "temperature": TEMPERATURE,
                    "top_p": TOP_P,
                    "top_k": TOP_K,
                    "num_ctx": NUM_CTX,
                    "num_predict": NUM_PREDICT,
                    "stop": [
                        "\nOperator:",
                        "Operator:",
                        "\nUser:",
                        "User:",
                        "\nOctron:",
                        "Octron:",
                        "\nAssistant:",
                        "Assistant:",
                        "=== ",
                        "[MISSION",
                        "[RELEVANT",
                    ],
                },
            )
            response_obj = future.result(timeout=OLLAMA_TIMEOUT)
 
        response = response_obj["message"]["content"].strip()
        response = _cleanup_response(response)

        # Ollama reports actual token counts on every response — use them
        # instead of guessing, so 'tokens' reflects reality, not an estimate.
        last_turn_tokens = {
            "prompt": response_obj.get("prompt_eval_count", 0),
            "completion": response_obj.get("eval_count", 0),
        }
        session_totals["prompt"] += last_turn_tokens["prompt"]
        session_totals["completion"] += last_turn_tokens["completion"]

    except FutureTimeoutError:
        response = f"!! SYSTEM ERROR: Ollama did not respond within {OLLAMA_TIMEOUT}s. Model may be stuck or swapping."
    except Exception as e:
        response = f"!! SYSTEM ERROR: {e}"
 
    # --- Emotion Processing ---
    emotion_report = process_emotional_layer(user_input, response)
    final_output = adjust_response_by_emotion(response, emotion_report["emotion"])
    final_output = _cleanup_response(final_output)
 
    # Update history — store the clean (untagged) response, not the display
    # version, so vibe tags never leak back into the model's own context
    # or into the sleep-cycle fact extraction.
    clean_output = _strip_vibe_tags(final_output)
 
    message_history.append({"role": "user", "content": user_input})
    message_history.append({"role": "assistant", "content": clean_output})
    _trim_message_history()
 
    chat_history.append(f"Operator: {user_input}")
    chat_history.append(f"Octron: {clean_output}")
 
    # --- Print Final Output ---
    print(f"Octron: {final_output}\n")

    # --- Context Budget Warning ---
    _turn_total = last_turn_tokens["prompt"] + last_turn_tokens["completion"]
    if NUM_CTX and _turn_total / NUM_CTX >= CONTEXT_WARNING_THRESHOLD:
        print(
            f"[!! CONTEXT WARNING] {_turn_total}/{NUM_CTX} tokens used "
            f"({_turn_total / NUM_CTX * 100:.0f}%) — type 'new' to refresh "
            f"the session before response quality degrades.\n"
        )
 
