# Antigravity SDK Service

A lightweight FastAPI service that wraps the [Google Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python) and exposes it over HTTP with SSE (Server-Sent Events) streaming.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check — returns `{"status": "ok"}` |
| `POST` | `/chat` | Send a prompt, receive SSE-streamed tokens |
| `POST` | `/reset` | Close current agent session and start fresh |

### `POST /chat` Request Body

```json
{
  "prompt": "What files are in the current directory?",
  "cwd": "C:\\Projects\\my-project",
  "system_instructions": "You are a helpful coding assistant.",
  "new_session": false
}
```

- **`prompt`** (required): The user's message.
- **`cwd`** (optional): Project folder for the agent to operate in.
- **`system_instructions`** (optional): System prompt for the agent.
- **`new_session`** (optional): Set `true` to close the current agent and start a new one.

### SSE Response Format

```
data: {"token": "Hello"}
data: {"token": " world!"}
data: [DONE]
```

---

## Setup & Running

### Prerequisites

```bash
pip install -r requirements.txt
```

Set your API key as an environment variable:

```powershell
# PowerShell
$env:GEMINI_API_KEY = "your_api_key_here"
```

```bash
# CMD
set GEMINI_API_KEY=your_api_key_here
```

### Start the Service

```bash
python services/antigravity/antigravity_service.py
```

The service starts on `http://0.0.0.0:8200`.

### PyCharm Run Configuration

1. Open **Run → Edit Configurations...**.
2. Create a new **Python** run configuration:
   - **Name**: `Antigravity Service`
   - **Script path**: `services/antigravity/antigravity_service.py`
   - **Working directory**: Project root
3. Under **Environment variables**, add:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```
4. Click **OK**, then **Run ▶** or **Debug 🐛**.

### Troubleshooting

- **`ModuleNotFoundError: google.antigravity`**: The SDK isn't installed. Run `pip install google-antigravity`.
- **Port already in use**: Change the port via the `ANTIGRAVITY_PORT` environment variable (e.g. `ANTIGRAVITY_PORT=8201`).

---

## Verify

```powershell
curl http://localhost:8200/health
# Expected: {"status":"ok"}
```

From SnapSolve: Select an **Antigravity** profile and send a prompt. The response should stream in real-time.
