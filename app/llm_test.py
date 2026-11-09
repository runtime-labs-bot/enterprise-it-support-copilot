from app.services.llm_provider import LLMClient

client = LLMClient()

def ask_llm(question:str)->str:
    response = client.chat.completions.create(
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
        print(ask_llm(question))
    except Exception as exc:
        print(f"Request failed: {type(exc).__name__}: {exc}")



