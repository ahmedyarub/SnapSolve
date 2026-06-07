# API & Remote Control Configuration

To enable the local API and remote control functionality in SnapSolve, you need to configure the settings in your SnapSolve configuration file. This server provides both REST endpoints (similar to Screenpipe) and a WebSocket endpoint for the Android companion app.

## Configuration

Add the following settings to your SnapSolve configuration file (typically `config/config.json`):

```json
{
  "enable_api_server": true,
  "api_server_host": "0.0.0.0",
  "api_server_port": 3031,
  "api_server_key": "optional_secret_key"
}
```

### Configuration Options

- **enable_api_server** (boolean): Enable or disable the local API server
  - `true`: Server starts when SnapSolve launches
  - `false`: Server does not start (default)

- **api_server_host** (string): Host address to bind the server to
  - `"0.0.0.0"`: Listen on all available network interfaces (recommended for remote control)
  - `"127.0.0.1"`: Listen only on localhost (for local API usage)

- **api_server_port** (integer): Port number for the API server
  - Default: `3031` (aligned with Screenpipe for easier integration)

- **api_server_key** (string): Optional API key required for REST endpoints
  - Provide a secret key to authenticate REST API requests via the `Authorization` or `x-api-key` header.
  - Leave empty `""` to disable authentication. (Not recommended if bound to `0.0.0.0`)

## Network Setup

### Finding Your Computer's IP Address

**Windows**:
```cmd
ipconfig
```
Look for "IPv4 Address" under your active network adapter (e.g., `192.168.1.100`)

### Firewall Configuration

Make sure your firewall allows incoming connections on the configured port.

**Windows**:
```powershell
New-NetFirewallRule -DisplayName "SnapSolve API" -Direction Inbound -LocalPort 3031 -Protocol TCP -Action Allow
```

## Security Considerations

⚠️ **Important Security Notes**:

1. **Local Network Only**: This server is designed for local network use only. Do not expose it to the internet.
2. **Authentication**: If you bind the server to `0.0.0.0`, it is strongly recommended to set an `api_server_key` to prevent unauthorized access on your local network. Note: the WebSocket `/ws` endpoint does not enforce this key to maintain compatibility with the Android app.

## Usage

1. **Start SnapSolve**: The API server will start automatically if enabled in the configuration.
2. **Check Server Status**: You can verify the server is running by visiting `http://localhost:3031/health`.
3. **Connect Android App**: Use the SnapSolve Remote Control Android app to connect to your computer on port 3031.

## API Endpoints

The API server provides the following REST endpoints. If an API key is set, pass it via the `Authorization` or `x-api-key` header.

### Core Endpoints
- `GET /health` - Check if server is running and view downstream services status
- `GET /config` - Retrieve current configuration (sensitive keys redacted)
- `GET /search?q={query}&limit={limit}` - Search past sessions and transcription tags
- `GET /tags` - List all unique session tags
- `GET /sessions?limit={limit}&offset={offset}` - List recent sessions
- `GET /sessions/{session_id}` - Retrieve full session details and interaction history

### Actions & Configuration
- `POST /action` - Execute SnapSolve actions
  - Body: `{"action": "capture"}`
- `POST /response_image/ack` - Acknowledge receipt of the response image
- `POST /config/transcription_language` - Set active transcription language
  - Body: `{"language": "en"}`

### Mouse & Keyboard Control
- `POST /mouse/move` - Move mouse cursor
  - Body: `{"dx": 0.5, "dy": 0.5}` (relative coordinates)
- `POST /mouse/click` - Mouse click
  - Body: `{"button": "left"}`
- `POST /mouse/double_click` - Double click
  - Body: `{"button": "left"}`
- `POST /mouse/drag/start` - Start drag operation
- `POST /mouse/drag/end` - End drag operation
- `POST /mouse/scroll` - Scroll mouse wheel
  - Body: `{"delta": 1}`
- `POST /keyboard/type` - Type text
  - Body: `{"text": "Hello world"}`

### WebSocket
- `WS /ws` - JSON message loop used by the Android remote control app.

## Development

For development and testing, you can use tools like curl or Postman to test the API:

```bash
# Check server status (if api_server_key is set to "my_secret_key")
curl -H "Authorization: my_secret_key" http://localhost:3031/health

# Execute action
curl -X POST -H "Authorization: my_secret_key" -H "Content-Type: application/json" -d '{"action": "capture"}' http://localhost:3031/action
```