# SnapSolve MCP Server

The SnapSolve Model Context Protocol (MCP) Server exposes SnapSolve's session history, captured OCR text, and transcription data to external AI tools such as Claude Desktop, Cursor, and VS Code. This allows AI assistants to query past SnapSolve sessions seamlessly as part of their context.

## Prerequisites

- Python 3.10+
- The `mcp` Python package (installed via `pip install -r requirements.txt`).

## Exposed Tools

The server exposes the following tools:

- `list_sessions(limit: int = 20, offset: int = 0)`: List lightweight metadata for recent SnapSolve sessions.
- `get_session(session_id: str)`: Get full details, OCR/audio transcriptions, and interaction history of a specific SnapSolve session.
- `search_sessions(query: str, limit: int = 10)`: Search for SnapSolve sessions containing the given text query across prompts, responses, OCR texts, or transcriptions.
- `get_tags()`: Get a list of all unique tags used across SnapSolve sessions.

## Setup Instructions

> [!IMPORTANT]
> The MCP server must be run with the SnapSolve repository root as its working directory so that it can locate the `sessions/` folder and `config.json` correctly.

### Claude Desktop Configuration

To use the SnapSolve MCP server in Claude Desktop, add the following to your `claude_desktop_config.json` (typically located at `%APPDATA%\Claude\claude_desktop_config.json` on Windows or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "snapsolve": {
      "command": "python",
      "args": [
        "services/mcp_server/server.py"
      ],
      "env": {
        "PYTHONPATH": "."
      },
      "cwd": "C:/path/to/your/SnapSolve"
    }
  }
}
```

*Replace `C:/path/to/your/SnapSolve` with the absolute path to your SnapSolve installation.*

### Cursor / VS Code Configuration

You can add an MCP server in Cursor settings:
1. Open Cursor Settings -> Features -> MCP Servers.
2. Add a new server.
3. Select `stdio` as the transport.
4. Set the command to `python services/mcp_server/server.py`.
5. Ensure the working directory for the command is the SnapSolve root.

## Testing

You can use the official MCP Inspector to test the server directly:

```bash
npx @modelcontextprotocol/inspector python services/mcp_server/server.py
```
