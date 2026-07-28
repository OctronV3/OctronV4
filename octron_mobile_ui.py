"""
Octron Portable Interface — Streamlit
A "living neural network" chat surface: an ambient synapse mesh drifts behind
the conversation, and each message renders as a signal node + bubble instead
of a flat terminal line.

Same backend contract as before — POSTs {message, history} to
http://localhost:8000/chat and expects {"response": "..."} back — only the
presentation layer changed.
"""

import math
import random

import requests
import streamlit as st

st.set_page_config(page_title="OCTRON", page_icon="🧠", layout="centered")

# ============================================================
# Design tokens
# ============================================================
BG = "#060a12"          # near-black void
PANEL = "#0c121d"        # bubble / input panel
CYAN = "#5eead4"         # assistant signal
VIOLET = "#a78bfa"       # operator (user) signal
AMBER = "#fbbf24"        # status accent, used sparingly
TEXT = "#e7ecf5"
DIM = "#647089"

API_URL = "http://localhost:8000/chat"


# ============================================================
# Ambient synapse network — generated server-side once per session,
# rendered as a single inline SVG so it needs no JS to animate (pure CSS
# keyframes drive the pulse/drift).
# ============================================================
def _build_network_svg(seed: int, width: int = 1200, height: int = 1800, n_nodes: int = 46) -> str:
    rnd = random.Random(seed)
    nodes = [(rnd.uniform(0, width), rnd.uniform(0, height)) for _ in range(n_nodes)]

    lines = []
    for i, (x1, y1) in enumerate(nodes):
        neighbors = sorted(
            ((math.hypot(x1 - x2, y1 - y2), j) for j, (x2, y2) in enumerate(nodes) if j != i)
        )[: rnd.randint(2, 3)]
        for _, j in neighbors:
            x2, y2 = nodes[j]
            lines.append((x1, y1, x2, y2))

    line_svg = "\n".join(
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'class="synapse-line" style="animation-delay:{rnd.uniform(0, 7):.2f}s" />'
        for x1, y1, x2, y2 in lines
    )
    node_svg = "\n".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rnd.uniform(1.5, 3.0):.1f}" '
        f'class="synapse-node" style="animation-delay:{rnd.uniform(0, 6):.2f}s" />'
        for x, y in nodes
    )

    return (
        f'<svg class="neuron-bg" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">'
        f"{line_svg}{node_svg}</svg>"
    )


if "net_seed" not in st.session_state:
    st.session_state.net_seed = random.randint(0, 999_999)

NETWORK_SVG = _build_network_svg(st.session_state.net_seed)


# ============================================================
# Global styling
# ============================================================
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [data-testid="stAppViewContainer"], .stApp {{
        background: {BG} !important;
        color: {TEXT};
        font-family: 'Inter', sans-serif;
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    #MainMenu, footer {{ visibility: hidden; }}

    /* ambient network, fixed behind everything */
    .neuron-bg {{
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        z-index: 0;
        opacity: 0.55;
        pointer-events: none;
    }}
    .synapse-line {{
        stroke: {CYAN};
        stroke-width: 1;
        opacity: 0.08;
        animation: line-pulse 6s ease-in-out infinite;
    }}
    .synapse-node {{
        fill: {CYAN};
        opacity: 0.35;
        animation: node-pulse 4.5s ease-in-out infinite;
    }}
    @keyframes line-pulse {{
        0%, 100% {{ opacity: 0.05; }}
        50% {{ opacity: 0.22; }}
    }}
    @keyframes node-pulse {{
        0%, 100% {{ opacity: 0.25; transform: scale(1); }}
        50% {{ opacity: 0.85; transform: scale(1.5); }}
    }}
    @media (prefers-reduced-motion: reduce) {{
        .synapse-line, .synapse-node {{ animation: none !important; }}
    }}

    /* keep real content above the network */
    [data-testid="stVerticalBlock"], .block-container {{
        position: relative;
        z-index: 1;
    }}
    .block-container {{ padding-top: 2rem; max-width: 720px; }}

    /* ---- header ---- */
    .octron-header {{
        display: flex;
        align-items: center;
        gap: 12px;
        padding-bottom: 4px;
        border-bottom: 1px solid rgba(94,234,212,0.15);
        margin-bottom: 1.2rem;
    }}
    .octron-mark {{
        width: 30px; height: 30px;
        border-radius: 50%;
        background: radial-gradient(circle at 35% 30%, {CYAN}, transparent 70%);
        box-shadow: 0 0 16px {CYAN};
        animation: node-pulse 3s ease-in-out infinite;
        flex-shrink: 0;
    }}
    .octron-title {{
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 700;
        font-size: 1.35rem;
        letter-spacing: 0.04em;
        margin: 0;
        color: {TEXT};
    }}
    .octron-sub {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        letter-spacing: 0.08em;
        color: {DIM};
        margin: 0;
    }}
    .octron-sub .dot {{
        display: inline-block;
        width: 6px; height: 6px;
        border-radius: 50%;
        background: {CYAN};
        margin-right: 6px;
        box-shadow: 0 0 6px {CYAN};
    }}

    /* ---- message rows ---- */
    .msg-row {{
        display: flex;
        align-items: flex-end;
        gap: 10px;
        margin: 16px 0;
    }}
    .msg-row.user {{ flex-direction: row-reverse; }}
    .msg-node {{
        width: 12px; height: 12px;
        border-radius: 50%;
        flex-shrink: 0;
        margin-bottom: 8px;
    }}
    .msg-row.assistant .msg-node {{
        background: {CYAN};
        box-shadow: 0 0 10px {CYAN};
    }}
    .msg-row.user .msg-node {{
        background: {VIOLET};
        box-shadow: 0 0 10px {VIOLET};
    }}
    .msg-bubble {{
        max-width: 76%;
        padding: 11px 15px;
        border-radius: 14px;
        line-height: 1.5;
        font-size: 0.94rem;
        border: 1px solid;
    }}
    .msg-row.assistant .msg-bubble {{
        background: rgba(94,234,212,0.06);
        border-color: rgba(94,234,212,0.28);
        border-bottom-left-radius: 4px;
        color: {TEXT};
    }}
    .msg-row.user .msg-bubble {{
        background: rgba(167,139,250,0.08);
        border-color: rgba(167,139,250,0.30);
        border-bottom-right-radius: 4px;
        color: {TEXT};
    }}

    /* ---- chat input ---- */
    [data-testid="stChatInput"] {{
        background: {PANEL} !important;
        border: 1px solid rgba(94,234,212,0.25) !important;
        border-radius: 14px !important;
    }}
    [data-testid="stChatInput"]:focus-within {{
        border-color: {CYAN} !important;
        box-shadow: 0 0 14px rgba(94,234,212,0.25);
    }}
    [data-testid="stChatInput"] textarea {{
        color: {TEXT} !important;
        font-family: 'Inter', sans-serif;
    }}
    </style>

    {NETWORK_SVG}
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Chat state (declared before the header so the header can read it)
# ============================================================
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "last_tokens" not in st.session_state:
    st.session_state.last_tokens = None  # {"total": int, "context_window": int, "percent_used": float}

# ============================================================
# Header — identity + live context gauge + New Session control
# ============================================================
header_col, new_session_col = st.columns([5, 1])

with header_col:
    tok = st.session_state.last_tokens
    if tok:
        ctx_line = (
            f"SYNAPSE LINK · LOCAL NODE · "
            f"CTX {tok['total']}/{tok['context_window']} ({tok['percent_used']:.0f}%)"
        )
    else:
        ctx_line = "SYNAPSE LINK · LOCAL NODE"

    st.markdown(
        f"""
        <div class="octron-header">
            <div class="octron-mark"></div>
            <div>
                <p class="octron-title">OCTRON</p>
                <p class="octron-sub"><span class="dot"></span>{ctx_line}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with new_session_col:
    if st.button("New Session", help="Clear conversation context (memory is unaffected — Octron's stored facts stay intact)"):
        st.session_state.chat_history = []
        st.session_state.last_tokens = None
        st.rerun()

if st.session_state.last_tokens and st.session_state.last_tokens["percent_used"] >= 85:
    st.warning(
        f"Context window is {st.session_state.last_tokens['percent_used']:.0f}% full — "
        f"click **New Session** before responses start degrading."
    )


def render_message(role: str, content: str):
    st.markdown(
        f"""
        <div class="msg-row {role}">
            <div class="msg-node"></div>
            <div class="msg-bubble">{content}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


for message in st.session_state.chat_history:
    render_message(message["role"], message["content"])

# ============================================================
# Input + backend call
# ============================================================
if user_prompt := st.chat_input("Send transmission..."):
    render_message("user", user_prompt)

    with st.spinner("Signal propagating..."):
        try:
            payload = {"message": user_prompt, "history": st.session_state.chat_history}
            res = requests.post(API_URL, json=payload, timeout=30).json()
            output_text = res.get("response", "No data packet received.")
            if res.get("tokens"):
                st.session_state.last_tokens = res["tokens"]
        except Exception:
            output_text = "!! DISCONNECTED: Core Server Host offline or out of range."

    render_message("assistant", output_text)

    st.session_state.chat_history.append({"role": "user", "content": user_prompt})
    st.session_state.chat_history.append({"role": "assistant", "content": output_text})

    # Rerun so the header's context gauge picks up the token count we just
    # stored — without this the % shown stays one message behind.
    st.rerun()