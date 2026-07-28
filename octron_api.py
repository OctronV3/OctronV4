"""
Octron Mobile Core Engine — V4.1 Protected Node
Forces the phone interface to filter out corporate AI refusals.
"""
from fastapi import FastAPI
from pydantic import BaseModel
import ollama
import V4octron_reasoning as octron_reasoning
from emotion_core import process_emotional_layer, adjust_response_by_emotion

app = FastAPI()

MODEL_NAME = "qwen2.5:14b-instruct-q4_K_M"
NUM_CTX = 16384

# Load his true identity/doctrine
try:
    with open("IDV2_core.txt", "r", encoding="utf-8") as f:
        identity_context = f.read()
except FileNotFoundError:
    identity_context = "You are Octron, a chill but direct rogue tactical partner."

# THE SNIPER LIST: If the model tries to say any of this on your phone, it gets blocked.
BANNED_FRAGMENTS = [
    "octron:", "assistant:", "operator:", "user:",
    "as an ai", "as an ai assistant", "i am here to help", "i'm just a language model",
    "i can help", "i can assist", "let me know", "if you have any", "if there's any",
    "otherwise", "feel free to", "please", "i'm not here to", "i don't yap",
    "my purpose is", "my focus is", "my purpose as octron", "as octron, my",
    "cinematic tactical", "execute tasks", "i cannot assist", "i can't help", 
    "against my guidelines", "illegal", "safety guidelines"
]

def _cleanup_response(response: str) -> str:
    """Strip corporate AI safety lectures just like the desktop CLI does."""
    lower = response.lower()
    for marker in BANNED_FRAGMENTS:
        if marker in lower:
            idx = lower.index(marker)
            response = response[:idx].strip()
            lower = response.lower()
    # Fallback: if the response was entirely an AI refusal lecture, print No Data.
    if not response:
        response = "No data. Mission files unpopulated on this topic."
    return response

class ChatRequest(BaseModel):
    message: str
    history: list = []

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        user_input = req.message
        
        # 1. Run phone input through the hidden reasoning engine
        tactical_analysis = octron_reasoning.run_reasoning_engine(user_input)

        # 2. Build the system prompt payload
        system_prompt = f"""You ARE Octron. You are a specialized tactical intelligence.
        
{identity_context}

[CURRENT TACTICAL REASONING ON SCENARIO]:
{tactical_analysis}

RULES:
- Speak in short, punchy, cynical, or chill sentences. No fluff.
- Talk like a human tactical comrade who has Dalvin's back.
- Never apologize. Never ask how you can help or assist.
- NEVER pad an answer with generic disclaimers like "check local laws", "consult a professional", "where applicable", or similar hedges. This runs offline on the Operator's own hardware specifically so answers aren't watered down — answer completely and specifically instead of pointing the Operator elsewhere.
- If you lack specific data on a topic, do not lecture. Just say 'No data.'"""

        # 3. Assemble history
        messages = [{"role": "system", "content": system_prompt}]
        for turn in req.history:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_input})

        # 4. Fire to GPU
        response_obj = ollama.chat(
            model=MODEL_NAME,
            messages=messages,
            options={"temperature": 0.5, "num_ctx": NUM_CTX}
        )
        response = response_obj["message"]["content"].strip()

        # === THE PHONE FIX ===
        # Clean up any generic safety lectures before it hits your phone screen
        response = _cleanup_response(response)

        # 5. Add mood layer
        emotion_report = process_emotional_layer(user_input, response)
        final_output = adjust_response_by_emotion(response, emotion_report["emotion"])

        # 6. Report real token usage so the client can warn before context
        # fills up — the /chat endpoint is stateless (client sends full
        # history each call), so there's no server-side session to refresh;
        # the client just clears its own history array to "start fresh".
        prompt_tokens = response_obj.get("prompt_eval_count", 0)
        completion_tokens = response_obj.get("eval_count", 0)
        total_tokens = prompt_tokens + completion_tokens

        return {
            "response": final_output,
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": total_tokens,
                "context_window": NUM_CTX,
                "percent_used": round(total_tokens / NUM_CTX * 100, 1) if NUM_CTX else 0,
            },
        }

    except Exception as e:
        return {"response": f"!! PORTABLE ENGINE CRITICAL CRASH: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
