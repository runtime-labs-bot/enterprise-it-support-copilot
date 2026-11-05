import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

api_key= os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

if not api_key:
    raise ValueError("GROQ_API_KEY is missing from .env")

client = Groq(api_key=api_key)

def ask_groq(question:str)->str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role":"system",
                "content":(
                    "You are an enterprise IT support assistant. "
                    "Give clear, practical and safe troubleshooting steps. "
                    "Never advise disabling security software such as firewalls, antivirus, or endpoint protection; "
                    "instead, suggest checking logs or contacting IT to verify allowlist rules. "
                    "Never claim to have performed actions on the user's computer. "
                    "Keep answers concise and use a numbered list."
                    "Keep answers under 250 words. Use a short numbered list, not tables."
                )
            },
            {
                "role":"user",
                "content":question
            }
        ],
        temperature=0.2,
        max_completion_tokens=500
    )

    return (
        response.choices[0].message.content
        or "The model returned an empty response."
    )

if __name__ == "__main__":
    question = "What should I check if my company VPN will not connect?"

    try:
        print(ask_groq(question))
    except Exception as exc:
        print(f"Request failed: {type(exc).__name__}: {exc}")



