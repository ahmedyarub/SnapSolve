# Remote Control Configuration

To enable remote control functionality in SnapSolve, you need to configure the settings in your SnapSolve configuration file.

## Configuration

Add the following settings to your SnapSolve configuration file (typically `config/config.json`):

```json
{
  "enable_remote_control": true,
  "remote_control_host": "0.0.0.0",
  "remote_control_port": 8080
}
```

### Configuration Options

- **enable_remote_control** (boolean): Enable or disable the remote control server
  - `true`: Server starts when SnapSolve launches
  - `false`: Server does not start (default)

- **remote_control_host** (string): Host address to bind the server to
  - `"0.0.0.0"`: Listen on all available network interfaces (recommended)
  - `"127.0.0.1"`: Listen only on localhost (for local testing only)
  - Specific IP: Listen only on a specific network interface

- **remote_control_port** (integer): Port number for the remote control server
  - Default: `8080`
  - Choose a port that's not used by other applications
  - Make sure the port is allowed through your firewall

## Network Setup

### Finding Your Computer's IP Address

**Windows**:
```cmd
ipconfig
```
Look for "IPv4 Address" under your active network adapter (e.g., `192.168.1.100`)

**Mac**:
```bash
ifconfig | grep "inet "
```
Look for the IP address (e.g., `192.168.1.100`)

**Linux**:
```bash
ip addr show | grep "inet "
```
Look for the IP address (e.g., `192.168.1.100`)

### Firewall Configuration

Make sure your firewall allows incoming connections on the configured port.

**Windows**:
```powershell
New-NetFirewallRule -DisplayName "SnapSolve Remote Control" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
```

**Mac**:
```bash
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add /path/to/python
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp /path/to/python
```

**Linux (UFW)**:
```bash
sudo ufw allow 8080/tcp
```

## Security Considerations

⚠️ **Important Security Notes**:

1. **Local Network Only**: This server is designed for local network use only. Do not expose it to the internet.

2. **No Authentication**: The current implementation does not include authentication. Anyone on your local network can control SnapSolve if they know the IP address and port.

3. **Network Isolation**: Consider using a separate network or VLAN for sensitive operations.

4. **Firewall Rules**: Use firewall rules to restrict access to specific IP addresses if needed.

## Usage

1. **Start SnapSolve**: The remote control server will start automatically if enabled in the configuration.

2. **Check Server Status**: You can verify the server is running by checking the SnapSolve logs or by visiting `http://your-ip:8080/status` in a web browser.

3. **Connect Android App**: Use the SnapSolve Remote Control Android app to connect to your computer.

## Troubleshooting

### Server Won't Start

- Check if the port is already in use: `netstat -an | grep 8080`
- Try a different port number
- Check SnapSolve logs for error messages

### Can't Connect from Android Device

- Verify both devices are on the same network
- Check firewall settings
- Ensure SnapSolve is running
- Try pinging the computer from your Android device
- Check the IP address is correct

### Connection Drops

- Check network stability
- Ensure your computer doesn't go to sleep
- Verify power saving settings don't disable network adapter

## Advanced Configuration

### Custom Host Binding

If you want to bind to a specific network interface:

```json
{
  "remote_control_host": "192.168.1.100"
}
```

### Dynamic DNS

For easier access, consider setting up dynamic DNS if your IP changes frequently.

### Port Forwarding (Not Recommended)

⚠️ **Warning**: Port forwarding exposes the server to the internet and is not recommended for security reasons.

If you must use port forwarding:
- Set up a VPN instead
- Use strong authentication
- Consider using a reverse proxy with SSL/TLS

## API Endpoints

The remote control server provides the following endpoints:

### Server Status
- `GET /status` - Check if server is running
- `GET /` - Server information and available endpoints

### Actions
- `POST /action` - Execute SnapSolve actions
  - Body: `{"action": "capture"}`

### Mouse Control
- `POST /mouse/move` - Move mouse cursor
  - Body: `{"x": 0.5, "y": 0.5}` (relative coordinates 0-1)

- `POST /mouse/click` - Mouse click
  - Body: `{"button": "left"}`

- `POST /mouse/double_click` - Double click
  - Body: `{"button": "left"}`

- `POST /mouse/drag_start` - Start drag operation
  - Body: `{"x": 0.5, "y": 0.5}`

- `POST /mouse/drag_end` - End drag operation
  - Body: `{"x": 0.5, "y": 0.5}`

- `POST /mouse/scroll` - Scroll mouse wheel
  - Body: `{"delta": 1}`

## Development

For development and testing, you can use tools like curl or Postman to test the API:

```bash
# Check server status
curl http://localhost:8080/status

# Execute action
curl -X POST http://localhost:8080/action -H "Content-Type: application/json" -d '{"action": "capture"}'

# Move mouse
curl -X POST http://localhost:8080/mouse/move -H "Content-Type: application/json" -d '{"x": 0.5, "y": 0.5}'
```

## Support

For issues or questions about remote control functionality:
1. Check this configuration guide
2. Review the Android app README
3. Check SnapSolve logs for error messages
4. Verify network and firewall settings