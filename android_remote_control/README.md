# SnapSolve Remote Control Android App

An Android application that allows you to remotely control SnapSolve from your phone or tablet over your local network.

## Features

- **Touchpad Control**: Large touch area for mouse control
  - Single tap: Left click
  - Double tap: Double click
  - Two-finger tap: Right click
  - Three-finger tap: Middle click
  - Long press: Drag start/end

- **Action Buttons**: All buttons from the SnapSolve overlay panel
  - 📸 Capture
  - 🎯 Reselect
  - ➕ Multi-select
  - ✅ End Multi
  - 🧵 Toggle Stitching
  - 🔄 Cycle Source
  - 🖥️ Toggle Panel
  - 💬 New Chat
  - ❌ Cancel

## Requirements

- Android 5.0 (API level 21) or higher
- Local network connection to the computer running SnapSolve

## Installation

### Prerequisites

1. Make sure SnapSolve is running on your computer with remote control enabled
2. Enable remote control in SnapSolve config:
   ```json
   {
     "enable_remote_control": true,
     "remote_control_host": "0.0.0.0",
     "remote_control_port": 8080
   }
   ```

### Building the App

1. Open Android Studio
2. Import the project from the `android_remote_control` directory
3. Wait for Gradle sync to complete
4. Build and run on your device or emulator

### Installing APK

1. Build the APK in Android Studio: Build > Build Bundle(s) / APK(s) > Build APK(s)
2. Transfer the APK to your Android device
3. Install the APK (you may need to enable "Install from unknown sources")

## Usage

1. **Find your computer's IP address**:
   - Windows: Open Command Prompt and run `ipconfig`
   - Mac/Linux: Open Terminal and run `ifconfig` or `ip addr`

2. **Connect the app**:
   - Open SnapSolve Remote Control on your Android device
   - Enter your computer's IP address (e.g., `192.168.1.100`)
   - Enter the port (default: `8080`)
   - Tap "Connect"

3. **Use the touchpad**:
   - Move your finger on the touchpad to control the mouse cursor
   - Tap to click, double-tap for double-click
   - Use two fingers for right-click, three fingers for middle-click
   - Long press and drag to drag items

4. **Use action buttons**:
   - Tap any button to execute the corresponding SnapSolve action
   - Buttons are disabled until you connect to the server

## Network Configuration

### Firewall Settings

Make sure your firewall allows incoming connections on port 8080:

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

### Troubleshooting

**Can't connect to server**:
- Make sure SnapSolve is running
- Check that remote control is enabled in config
- Verify your computer's IP address
- Check firewall settings
- Ensure both devices are on the same network

**Touchpad not working**:
- Make sure you're connected to the server
- Check that the touchpad area is not covered by other UI elements
- Try adjusting touch sensitivity in the app settings

**Buttons not responding**:
- Verify server connection is active
- Check SnapSolve logs for errors
- Make sure SnapSolve is not processing another action

## Development

### Project Structure

```
android_remote_control/
├── app/
│   ├── src/
│   │   └── main/
│   │       ├── java/com/snapsolve/remotecontrol/
│   │       │   ├── MainActivity.kt          # Main activity
│   │       │   ├── RemoteControlClient.kt   # HTTP client
│   │       │   └── TouchpadView.kt          # Custom touchpad view
│   │       ├── res/
│   │       │   ├── layout/
│   │       │   │   └── activity_main.xml     # UI layout
│   │       │   └── values/
│   │       └── AndroidManifest.xml          # App manifest
│   └── build.gradle                         # App-level build config
├── build.gradle                             # Project-level build config
└── settings.gradle                          # Gradle settings
```

### Key Components

**MainActivity.kt**: Main activity that handles UI setup and button clicks

**RemoteControlClient.kt**: HTTP client that communicates with SnapSolve server

**TouchpadView.kt**: Custom view that handles touch events and mouse control

## API Reference

The app communicates with SnapSolve via HTTP endpoints:

### Status
- `GET /status` - Check if server is running

### Actions
- `POST /action` - Execute SnapSolve action
  ```json
  {
    "action": "capture"
  }
  ```

### Mouse Control
- `POST /mouse/move` - Move mouse cursor
  ```json
  {
    "x": 0.5,
    "y": 0.5
  }
  ```

- `POST /mouse/click` - Mouse click
  ```json
  {
    "button": "left"
  }
  ```

- `POST /mouse/double_click` - Double click
  ```json
  {
    "button": "left"
  }
  ```

- `POST /mouse/drag_start` - Start drag
  ```json
  {
    "x": 0.5,
    "y": 0.5
  }
  ```

- `POST /mouse/drag_end` - End drag
  ```json
  {
    "x": 0.5,
    "y": 0.5
  }
  ```

- `POST /mouse/scroll` - Scroll
  ```json
  {
    "delta": 1
  }
  ```

## License

This project is part of SnapSolve and follows the same license.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review SnapSolve logs for error messages
3. Ensure both devices are on the same network
4. Verify firewall and network settings