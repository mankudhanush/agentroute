# AgentRoute — Setup

Environment setup for AgentRoute. Follow these steps in order. **Do not write any
code that calls Blender until the Blender verification step below prints a version
number.**

Requires **Python 3.12 or newer**. Python 3.14 can run the API; 3.12 is the safer choice for the Laya and PyTorch install. Check with:

```bash
python3 --version   # macOS / Linux
```

```powershell
python --version    # Windows
```

---

## 1. Create and activate the virtual environment

Run these from inside the `agentroute/` folder.

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### Windows (PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

> If PowerShell blocks the activation script, allow it for the current user once:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

### Windows (cmd.exe)

```bat
python -m venv venv
venv\Scripts\activate.bat
```

Your prompt should now be prefixed with `(venv)`. Deactivate anytime with
`deactivate`.

---

## 2. Install Python dependencies

With the virtual environment active:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Configure API keys

```bash
cp .env.example .env      # macOS / Linux
```

```powershell
Copy-Item .env.example .env   # Windows PowerShell
```

Then open `.env` and paste your own provider keys. The default provider is Gemini
(`GEMINI_API_KEY`). NVIDIA, Groq, and OpenRouter keys are optional. The full
self-host guide is in the repository root `README.md`. `.env` is git-ignored —
never commit real keys.

---

## 4. Install Blender (manual, system-level — NOT via pip)

Blender is **not** a Python package. It is a standalone application that AgentRoute
invokes as an external binary. Install it through your OS package manager or the
official installer.

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install blender
```

### macOS (Homebrew)

```bash
brew install --cask blender
```

### Windows

Download the installer from **https://www.blender.org/download/** and run it.
After installing, either add Blender to your `PATH`, or set `BLENDER_PATH` in your
`.env` to the full path of `blender.exe` (commonly
`C:\Program Files\Blender Foundation\Blender 4.x\blender.exe`).

---

## 5. Verify everything works

### 5a. Verify Blender

```bash
blender --version
```

This **must print a version number** (e.g. `Blender 4.2.0`) before you write any
code that calls Blender. If the command is not found, Blender is not on your PATH —
fix that (or set `BLENDER_PATH`) before continuing.

### 5b. Verify Python packages

With the virtual environment active:

```bash
python3 -c "import openai; import dotenv; print('ok')"
```

```powershell
python -c "import openai; import dotenv; print('ok')"
```

This should print `ok`. Chat models stay on Gemini, NVIDIA, Groq, or OpenRouter.
You enable them with API keys in `.env`. There is no weight download for those
providers. The full catalog and the animated architecture are in the repository
root `README.md` and `docs/architecture.html`.

Laya is installed by `requirements.txt`. Download its checkpoint once, with the
virtual environment active, before the first real decision:

```powershell
$env:LAYA_PRELOAD = "true"
python -c "from laya import Router; Router(preload=True); print('laya checkpoint ready')"
```

```bash
LAYA_PRELOAD=true python -c "from laya import Router; Router(preload=True); print('laya checkpoint ready')"
```

The checkpoint is `convaiinnovations/laya` on Hugging Face. Set
`DECISION_LAYER=baseline` in `.env` to run without it. Set `LAYA_PRELOAD=true`
if the API should load the checkpoint at startup.

### 5c. Run the pipeline offline (no API keys needed)

```bash
python demo.py --demo          # sample prompts through Classifier -> Router
python -m unittest discover -s tests -v
```

---

## 6. Run AgentRoute

Interactive mode makes real agent calls, so set the keys/models in `.env` first
(`GROQ_API_KEY`, `GROQ_MODEL`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`):

```bash
python demo.py
```

Once the offline steps pass, the environment is ready.
