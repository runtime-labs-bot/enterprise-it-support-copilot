"""Generate isolated Docker credentials without changing the local environment."""
from pathlib import Path
import secrets
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("GROQ_API_KEY", "GROQ_MODEL", "PINECONE_API_KEY", "PINECONE_INDEX_NAME", "TAVILY_API_KEY")


def initialize(root=ROOT):
    destination = root / ".env.docker"
    if destination.exists():
        print(".env.docker already exists; left unchanged.")
        return
    local = dotenv_values(root / ".env", interpolate=False)
    values = {key: local.get(key) or "" for key in PROVIDERS}
    values["GROQ_MODEL"] = values["GROQ_MODEL"] or "openai/gpt-oss-20b"
    values["PINECONE_INDEX_NAME"] = values["PINECONE_INDEX_NAME"] or "it-support-knowledge"
    values.update({key: secrets.token_hex(32) for key in (
        "DOCKER_DB_PASSWORD", "DOCKER_AUTH_JWT_SECRET", "DOCKER_ADMIN_API_KEY", "DOCKER_SUPPORT_API_KEY")})
    values["COPILOT_PUBLIC_URL"] = "http://localhost:8501"
    # Single quotes prevent Compose expanding $ in provider credentials.
    if any("'" in value or "\n" in value or "\r" in value for value in values.values()):
        raise ValueError("Use single-line provider credentials without single quotes")
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("# Private Docker configuration. Do not commit.\n")
        stream.writelines(f"{key}='{value}'\n" for key, value in values.items())
    print("Created .env.docker with separate Docker credentials. No secrets displayed.")
    missing = [key for key in ("GROQ_API_KEY", "PINECONE_API_KEY", "TAVILY_API_KEY") if not values[key]]
    if missing:
        print("Set these in .env.docker before starting: " + ", ".join(missing))


if __name__ == "__main__":
    initialize()
