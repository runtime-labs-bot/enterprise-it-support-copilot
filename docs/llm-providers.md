# Switch LLM providers

The app now has one provider boundary in `app/services/llm_provider.py`. Internal
answers, web answers, relevance graders, classification and the asynchronous MCP
tool loop all use it. LangGraph routing, ticket permissions, admin confirmations,
idempotency and citation validation are unchanged.

| Profile | Credentials | Model | Endpoint |
| --- | --- | --- | --- |
| `groq` | `GROQ_API_KEY` | `LLM_MODEL`, falling back to existing `GROQ_MODEL` | Fixed Groq endpoint |
| `openai` | `OPENAI_API_KEY` | Explicit `--model` | Fixed OpenAI Chat Completions endpoint |
| `gemini` | `GEMINI_API_KEY` | Explicit `--model` | Fixed Google Gemini OpenAI-compatible endpoint |
| `ollama` | Optional `OLLAMA_API_KEY` for local server | An already installed model | Local `/v1` endpoint |
| `compatible` | `LLM_API_KEY` (optional only for local servers) | Explicit `--model` | Explicit `--base-url` |

If `LLM_PROVIDER` is absent, the existing Groq configuration continues to work.
No additional package installation is required: the adapter uses the existing
HTTPX dependency. No provider is contacted by the switch command or `--show`.

## Commands from CMD

```bat
cd /d C:\ITSupportCopilot
.venv\Scripts\python.exe scripts\switch_llm.py --show
.venv\Scripts\python.exe scripts\switch_llm.py groq
```

Configure a provider's API key once in your private `.env` before selecting it.
Replace `YOUR_MODEL` with an exact model ID available to your account:

```bat
.venv\Scripts\python.exe scripts\switch_llm.py openai --model YOUR_MODEL
.venv\Scripts\python.exe scripts\switch_llm.py gemini --model YOUR_GEMINI_MODEL
.venv\Scripts\python.exe scripts\switch_llm.py ollama --model YOUR_INSTALLED_MODEL
.venv\Scripts\python.exe scripts\switch_llm.py compatible --model YOUR_MODEL --base-url https://your-provider.example/v1
```

The command validates configuration first and atomically updates the selection,
preserving other settings and credentials. Keys are never supplied as command
arguments or printed. Local clients read the file on each new call, so an existing
local server need not restart for these selector changes. Local `.env` selector
values take precedence over copies previously loaded into `os.environ` by dotenv;
nonempty process environment credentials take precedence over file credentials.
Finish active requests before switching, so a multi-step request does not straddle
two selections. An asynchronous MCP loop snapshots its selection when it starts.

## Your Docker deployment

Your app runs in Docker, so use `--docker`. Configure the selected key in private
`.env.docker` once (for example `OPENAI_API_KEY` for OpenAI):

```bat
.venv\Scripts\python.exe scripts\switch_llm.py --show --docker
.venv\Scripts\python.exe scripts\switch_llm.py groq --docker
.venv\Scripts\python.exe scripts\switch_llm.py openai --model YOUR_MODEL --docker
.venv\Scripts\python.exe scripts\switch_llm.py gemini --model YOUR_GEMINI_MODEL --docker
```

This single command updates `.env.docker`, rebuilds/recreates only the Copilot
service and waits for its health check. PostgreSQL, Meridian, Streamlit and data
volumes are not recreated by the command. They must already be running; initial
stack startup still uses the usual full `docker compose up` command. No new model
request is made by the service health check. A successful restart verifies process
health, not model access or capabilities.

For Gemini, set `GEMINI_API_KEY` in **`.env.docker`** before using the Docker
command (or `.env` for a local Python server). Replace `YOUR_GEMINI_MODEL` with an
available model ID that supports JSON output and function calling. The profile
uses `https://generativelanguage.googleapis.com/v1beta/openai`, Bearer API-key
authentication, and the shared sync/async adapter. It does not require a Google
SDK, an OpenAI key, or a custom base URL. The existing Groq selection is not
changed merely by adding Gemini support.

Gemini can attach an opaque `extra_content.google.thought_signature` to tool
calls. That value is preserved in the exact tool call and returned on subsequent
requests within the in-memory MCP tool loop. It is not inserted into final chat
answers, tool traces or evaluation reports; signatures are never fabricated or
used to bypass validation. Sequential-call regression tests verify that both
earlier and newer signatures survive subsequent steps.

For Ollama on Windows Docker Desktop, start Ollama separately and ensure the
selected model is installed before switching:

```bat
.venv\Scripts\python.exe scripts\switch_llm.py ollama --model YOUR_INSTALLED_MODEL --docker
```

The command sets `http://host.docker.internal:11434/v1`, so the container can reach
the host. Without `--docker`, the default is `http://127.0.0.1:11434/v1`. No model
download or Ollama installation is started automatically.

## Compatibility and safeguards

This adapter implements the non-streaming Chat Completions protocol. The model
must support JSON-object mode for graders and function tools for MCP. “Compatible”
does not guarantee every model supports both. Responses-only models and native
Anthropic protocols are not implemented; an explicitly configured compatible
endpoint may be used if it implements this protocol. The Gemini profile uses
Google's compatibility API, not native GenerateContent/Interactions requests or
Vertex AI OAuth authentication.

- Groq/Gemini/Ollama/compatible profiles use `max_tokens` by default. OpenAI uses
  `max_completion_tokens`, and omits `temperature` by default to accommodate
  models that reject that parameter.
- Override differences explicitly with `--token-parameter max_completion_tokens`
  or `--temperature-mode send` / `--temperature-mode omit`.
- `LLM_TIMEOUT_SECONDS` defaults to 30 (1–300 supported).
- The adapter does not retry, fall back to another model/provider, or automatically
  restart live evaluations. A 429 remains an evaluation error; the runner stops
  and preserves reports. Allowed reset headers are retained without provider bodies.
- Provider errors omit raw response bodies and credentials. Cloud profile URLs
  are pinned; use `compatible` with its own `LLM_API_KEY` for custom endpoints.
- Existing citation safeguards still reject incomplete or unsupported attribution.
  Switching models does not relax evaluation expectations or backend permissions.

Evaluation provenance now records both provider and model. Offline scorecard
workers force dummy Groq configuration with external connections blocked. The
manual GitHub live workflow can select providers using repository `LLM_*`
variables and the corresponding provider secret; a hosted runner must be able to
reach its endpoint. Live evaluation remains stopped in this implementation task.

Mocked tests cover text/JSON response normalization, token/temperature mapping,
tool-only messages, asynchronous MCP round trips, key isolation, sanitized rate
errors, and atomic CLI/Docker selection. Other providers have **not** been tested
against paid/live accounts. Verify one relevant case after configuring a model
and confirming quota availability; preserve its baseline.

Implementation verification: **126 unit tests** and **20/20 offline scorecard
checks** passed. The actual `groq --docker` switch rebuilt/restarted Copilot and
passed its health check without changing the active Groq model. Deployed ticket
idempotency/employee isolation and all 10 mocked citation checks passed afterward.
Docker Desktop was started after the first restart attempt reported an unavailable
engine; failed restarts return nonzero and do not claim activation. These checks
made zero live provider requests. Source changes are local until committed/pushed.

Protocol references: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[Groq compatibility](https://console.groq.com/docs/openai), and
[Ollama compatibility](https://docs.ollama.com/api/openai-compatibility).
Gemini behavior follows [Google's compatibility documentation](https://ai.google.dev/gemini-api/docs/openai)
and [thought-signature guidance](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures#openai).
