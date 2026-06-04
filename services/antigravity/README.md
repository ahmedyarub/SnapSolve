# Antigravity SDK Service

A lightweight FastAPI service that wraps the [Google Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python) and exposes it over HTTP with SSE (Server-Sent Events) streaming.

**Why WSL?** The `google-antigravity` SDK only publishes platform-specific wheels for Linux and macOS — not Windows. This service runs inside WSL so the SDK can be installed normally via `pip`.

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
  "cwd": "E:\\Toptal\\my-project",
  "system_instructions": "You are a helpful coding assistant.",
  "new_session": false
}
```

- **`prompt`** (required): The user's message.
- **`cwd`** (optional): Project folder. Windows paths are auto-converted to WSL mounts (e.g. `E:\Toptal\project` → `/mnt/e/Toptal/project`).
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

### Option 1: WSL Terminal

```bash
# 1. Open WSL
wsl

# 2. Set your API key
export GEMINI_API_KEY="your_api_key_here"

# 3. Navigate to the service directory
cd /mnt/e/Python/SnapSolve/services/antigravity

# 4. Install dependencies (first time only)
pip install -r requirements.txt

# 5. Run the service
python antigravity_service.py
```

The service starts on `http://0.0.0.0:8200` (accessible from Windows as `http://localhost:8200`).

### Option 2: PyCharm with WSL Interpreter

PyCharm Professional supports running Python scripts directly on a WSL distribution. This gives you IDE debugging, breakpoints, and log viewing.

#### 1. Add a WSL Python Interpreter

1. Open **File → Settings → Project → Python Interpreter**.
2. Click the gear icon → **Add Interpreter → On WSL...**.
3. Select your WSL distribution (e.g. `Ubuntu`).
4. Choose **System Interpreter** or **Virtualenv** and point it to your WSL Python (e.g. `/usr/bin/python3` or `~/.venv/bin/python`).
5. Click **OK** to save.

#### 2. Install Dependencies in WSL

Open PyCharm's **Terminal** (it will use WSL if the interpreter is configured) or a regular WSL terminal:

```bash
pip install -r /mnt/e/Python/SnapSolve/services/antigravity/requirements.txt
```

#### 3. Set the GEMINI_API_KEY Environment Variable

1. Open **Run → Edit Configurations...**.
2. Create a new **Python** run configuration:
   - **Name**: `Antigravity Service`
   - **Script path**: `services/antigravity/antigravity_service.py`
   - **Python interpreter**: Select the WSL interpreter from step 1.
   - **Working directory**: `/mnt/e/Python/SnapSolve/services/antigravity`
3. Under **Environment variables**, add:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```
4. Click **OK**.

#### 4. Run / Debug

- Click **Run ▶** or **Debug 🐛** to start the service.
- The service will bind to `0.0.0.0:8200` inside WSL, which is accessible from Windows as `http://localhost:8200`.
- You can set breakpoints in `antigravity_service.py` and inspect variables during requests.

#### Troubleshooting

- **`ModuleNotFoundError: google.antigravity`**: The SDK isn't installed in the WSL Python environment. Run `pip install google-antigravity` in your WSL terminal.
- **Port already in use**: Change the port via the `ANTIGRAVITY_PORT` environment variable (e.g. `ANTIGRAVITY_PORT=8201`).
- **Connection refused from Windows**: Ensure WSL networking allows localhost forwarding. On Windows 11 with WSL2, `localhost` forwarding is automatic. On older setups, you may need to use the WSL IP address (run `hostname -I` in WSL).

---

## Verify

From Windows PowerShell or CMD:

```powershell
curl http://localhost:8200/health
# Expected: {"status":"ok"}
```

From SnapSolve: Select an **Antigravity** profile and send a prompt. The response should stream in real-time.
