# AgentRoute

AgentRoute is an open-source routing platform. A request does not go straight to a model. A decision layer chooses an agent, the task is profiled, a model is selected for that agent, and a tool runs only when that agent needs one.

```
User
  → Laya (decision layer)
  → agent
  → task requirements
  → model selection
  → selected agent
  → tools, when required
  → execution
  → evaluation
  → retry or fallback
  → result
```

Laya is the decision layer. It is not a model, an agent, a provider, or a tool. It chooses which agent should handle the request. The model selector then chooses which model that agent should call.

## Agents

| Agent | What it handles |
| --- | --- |
| `GENERAL_AGENT` | Everyday requests that do not belong to a specialist |
| `CODING_AGENT` | Writing and changing code |
| `REASONING_AGENT` | Multi-step reasoning |
| `RESEARCH_AGENT` | Research that can use web search |
| `THREE_D_AGENT` | 3D scene work. It owns `BLENDER_TOOL` |
| `WEB_AGENT` | Live browser work. It owns `PLAYWRIGHT_TOOL` |

There is no Blender agent and no Playwright agent. Blender and Playwright are tools.

## Tools

| Tool | Owner |
| --- | --- |
| `BLENDER_TOOL` | `THREE_D_AGENT` |
| `PLAYWRIGHT_TOOL` | `WEB_AGENT` |
| `WEB_SEARCH_TOOL` | `RESEARCH_AGENT` |
| `CODE_EXECUTION_TOOL` | coding work |
| `FILESYSTEM_TOOL` | local files |
| `GITHUB_TOOL` | GitHub operations |

In the app, Blender and Playwright start off. Turn a plugin on in the left sidebar before asking for that kind of work. With Playwright off, a browser task stops with: “Playwright is disabled. Enable the Playwright plugin to execute this browser task.” With Blender off, a 3D task stops with: “Blender is disabled. Enable the Blender plugin to execute this 3D task.”

## Model providers

Agents call models through these providers. You supply your own keys. This repository does not include any keys.

| Provider | Key variable | Where to create a key |
| --- | --- | --- |
| Gemini | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| NVIDIA NIM | `NVIDIA_API_KEY` | https://build.nvidia.com/ |
| Groq | `GROQ_API_KEY` | https://console.groq.com/keys |
| OpenRouter | `OPENROUTER_API_KEY` | https://openrouter.ai/keys |

The default provider is Gemini (`AGENTROUTE_PROVIDER=gemini`). Models that this project treats as verified for display are:

- Gemini: `gemini-flash-latest`, `gemini-flash-lite-latest`
- NVIDIA: `nvidia/nemotron-3-ultra-550b-a55b`, `nvidia/nemotron-3-super-120b-a12b`, `nvidia/nemotron-3.5-lightning-30b-a3b`
- Groq: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`

A key only unlocks the models that account can call. If a model id 404s, change the model name in `agentroute/.env`. Do not hardcode a different id in Python.

## What you need

- Python 3.12 or newer (3.14 works on Windows for the API; 3.12 is the safer choice if you install the Laya/PyTorch stack)
- Node.js 20 or newer
- A Gemini key at minimum, if you keep the default provider
- Optional: [Blender](https://www.blender.org/download/) on this machine for “View in Blender”
- Optional: Playwright’s Chromium, installed by the setup steps below, for live browser tasks

Laya downloads a Hugging Face checkpoint on first use and installs PyTorch. That install is large. To run without it, set `DECISION_LAYER=baseline` in `agentroute/.env`. Baseline routing still picks an agent. It does not claim to be Laya.

## Setup

From the repository root:

### 1. Python environment and dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r agentroute\requirements.txt
pip install -r backend\requirements.txt
python -m playwright install chromium
```

On macOS or Linux, activate with `source .venv/bin/activate` and use forward slashes in the `pip` paths.

### 2. Your API keys

```powershell
copy agentroute\.env.example agentroute\.env
copy frontend\.env.example frontend\.env
```

Open `agentroute/.env` and paste your own keys. Leave unused providers blank.

```
GEMINI_API_KEY=your-gemini-key
NVIDIA_API_KEY=your-nvidia-key
GROQ_API_KEY=your-groq-key
OPENROUTER_API_KEY=
AGENTROUTE_PROVIDER=gemini
DECISION_LAYER=laya
```

`agentroute/.env` and `frontend/.env` are gitignored. Never commit them.

The full list of model, provider, and tool settings is in [`agentroute/.env.example`](agentroute/.env.example).

### 3. Frontend

```powershell
cd frontend
npm install
```

`frontend/.env` should point at the API:

```
VITE_API_URL=http://127.0.0.1:8010
```

### 4. Run it

API, from the repository root, in one terminal:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8010
```

UI, in a second terminal:

```powershell
cd frontend
npm run dev
```

Vite serves the UI at http://127.0.0.1:5173. The API health check is http://127.0.0.1:8010/api/health.

If port 5173 is already taken, Vite is configured with `strictPort` and will exit. Free that port, or change `server.port` in `frontend/vite.config.ts` and add the new origin to `CORS_ORIGINS` (see below).

Open the UI, choose **Launch AgentRoute**, and send a message. Refreshing the page returns to the landing page. Plugin toggles are not saved across refreshes.

## Browser and Blender

**Playwright.** With the Playwright plugin on, a request that names a live `http` or `https` page and asks to open, scrape, click, or screenshot it is handled by `WEB_AGENT`. Chromium opens in a visible window. Set this when you want headless mode (CI, a server with no display):

```
AGENTROUTE_PLAYWRIGHT_HEADLESS=1
```

**Blender.** Install Blender and either put `blender` on your `PATH` or set `BLENDER_PATH` to the executable. On Windows that is often:

```
BLENDER_PATH=C:\Program Files\Blender Foundation\Blender 5.2\blender.exe
```

Turn the Blender plugin on in the sidebar, then ask for a 3D scene. “View in Blender” opens the `.blend` file that the tool wrote on this machine. That path is local. It is not something a hosted website can open.

**Web search.** `SEARCH_API_KEY` in `agentroute/.env` is reserved for `WEB_SEARCH_TOOL`. Leave it blank until you connect a search backend.

## API access from another origin

The API allows these browser origins by default:

- `http://localhost:5173`
- `http://127.0.0.1:5173`
- `http://localhost:5174`
- `http://127.0.0.1:5174`

To allow another frontend origin, set `CORS_ORIGINS` in the environment before starting the API (comma-separated). The frontend build must use the same API address in `VITE_API_URL`. A static frontend deployed on the public internet cannot call `http://127.0.0.1:8010` from someone else’s browser. For that, run the API on a reachable host and set both values to that public API URL.

## Project layout

| Path | Role |
| --- | --- |
| `agentroute/` | Routing, agents, tools, model registry, provider clients |
| `backend/` | FastAPI app. Each chat request calls the router |
| `frontend/` | React + Vite UI: landing page, chat, plugin sidebar, routing inspector |

## Tests

From the repository root, with the virtualenv active and `DECISION_LAYER` left as you configured it:

```powershell
cd agentroute
python -m pytest
```

Frontend typecheck, from `frontend/`:

```powershell
npx tsc -b
```

## Design boundaries

Prompt-injection handling and human approval are design boundaries of the router. They are not a separate security product, and this repository does not ship one.

Context continuity matches a follow-up to the current task, a new task, or a previous task from the conversation itself. It does not use a list of domain keywords.

## License

MIT. See [LICENSE](LICENSE).
