"""
Octron Emotion Core
Detects conversational tone and adjusts response style.
Keeps emotion prefixes display-only (not saved to chat history).
"""

# Short-term emotion log (mood trend tracking)
emotional_log = []


def detect_emotion(input_text: str) -> str:
    """Detect the tactical emotion/vibe from user input."""
    text = input_text.lower()

    # Low Morale
    if any(
        x in text
        for x in [
            "i'm tired",
            "idk anymore",
            "i'm done",
            "i give up",
            "what's the point",
            "i cant",
            "i can't",
        ]
    ):
        return "low_morale"

    # Banter / casual
    if any(
        x in text for x in ["yo", "bro", "lmao", "lol", "pimp", "fr", "nah", "bet"]
    ):
        return "banter"

    # Friction / frustration
    if any(
        x in text
        for x in ["wtf", "yo what", "why would you", "pissed", "bruh", "tf"]
    ):
        return "friction"

    # Curious / learning
    if any(
        x in text
        for x in [
            "how does",
            "what is",
            "explain",
            "teach me",
            "tell me about",
            "why does",
        ]
    ):
        return "curious"

    return "nominal"


def update_emotion_log(emotion: str):
    """Log the emotion and keep a rolling window of the last 10."""
    global emotional_log
    emotional_log.append(emotion)
    if len(emotional_log) > 10:
        emotional_log.pop(0)


def get_mood_trend() -> str:
    """Analyze recent emotion log for trends."""
    if len(emotional_log) < 3:
        return "insufficient_data"

    recent = emotional_log[-5:]
    if recent.count("low_morale") >= 3:
        return "declining"
    if recent.count("banter") >= 3:
        return "elevated"
    if recent.count("friction") >= 2:
        return "tense"
    return "stable"


def adjust_response_by_emotion(response: str, emotion: str) -> str:
    """
    Adds a tactical prefix to the response based on the detected vibe.
    This is DISPLAY-ONLY — the raw response should be saved to chat history.
    """
    if emotion == "banter":
        return f"[Vibe: Casual] {response}"
    elif emotion == "low_morale":
        return f"[Protocol: Support] {response} Eyes up, Operator."
    elif emotion == "friction":
        return f"[Status: Firm] {response} Stay focused."
    elif emotion == "curious":
        return f"[Mode: Intel] {response}"
    else:
        return response


def process_emotional_layer(user_input: str, ai_response: str) -> dict:
    """Main emotional handler — detect, log, and report."""
    emotion = detect_emotion(user_input)
    update_emotion_log(emotion)

    return {
        "emotion": emotion,
        "intensity": "High" if emotion != "nominal" else "Stable",
        "trend": get_mood_trend(),
        "explanation": f"Octron calibrated for {emotion} state.",
    }
