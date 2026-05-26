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

### Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| **JDK** | 17+ | Android Studio / IntelliJ bundles one; verify via `java -version` |
| **Android SDK** | API 35 (compileSdk) | Install via **SDK Manager** inside your IDE |
| **Kotlin plugin** | 1.9.24 | Bundled with Android Studio; install separately in IntelliJ IDEA |
| **Gradle** | 8.x | The project ships a Gradle wrapper (`gradlew.bat`), no manual install needed |

### Opening the Project (JetBrains IDEs on Windows)

**Android Studio** (recommended):

1. **File → Open…** → navigate to the `android_remote_control` directory and click **OK**.
2. Wait for the Gradle sync to finish (progress shown in the bottom status bar).
3. If prompted to update the Android Gradle Plugin or Gradle wrapper, accept the defaults.

**IntelliJ IDEA Ultimate / Community**:

1. Make sure the **Android** plugin is installed (**File → Settings → Plugins → Marketplace** → search *Android*).
2. **File → Open…** → select the `android_remote_control` directory.
3. IntelliJ will detect it as a Gradle project and import it automatically.

### Running on a Physical Device via USB

1. **Enable Developer Options** on your Android phone:
   *Settings → About phone → tap **Build number** 7 times.*
2. **Enable USB Debugging**:
   *Settings → Developer options → toggle **USB debugging** on.*
3. Connect the phone to your PC with a USB cable and accept the "Allow USB debugging?" prompt on the phone.
4. In your IDE, select the device from the **target device dropdown** in the toolbar.
5. Click the **Run ▶** button (or press <kbd>Shift + F10</kbd>). The IDE builds the APK, installs it, and launches the app.

### Running on a Physical Device via Wi-Fi (Android 11+)

1. **Enable Wireless debugging**:
   *Settings → Developer options → toggle **Wireless debugging** on.*
2. Tap **Wireless debugging** → **Pair device with pairing code** to get an IP, port, and pairing code.
3. In your IDE's **Terminal** (or a Windows terminal), run:
   ```powershell
   adb pair <ip>:<pairing-port> <pairing-code>
   adb connect <ip>:<port>
   ```
4. The device now appears in the **target device dropdown**. Click **Run ▶** as usual.

> **Tip:** After the initial pairing, the device reconnects automatically as long as both PC and phone are on the same Wi-Fi network.

### Building a Release APK

1. **Build → Build Bundle(s) / APK(s) → Build APK(s)** in the IDE menu.
2. The unsigned APK is generated at:
   ```
   android_remote_control\app\build\outputs\apk\debug\app-debug.apk
   ```
3. Transfer it to your Android device (USB, cloud storage, etc.) and install it.
   You may need to enable *Settings → Install unknown apps* for the app you used to open the file.

---

## Running on a Device (Same-Network Setup)

Follow these steps **after** the app is installed on your phone and SnapSolve is running on your PC.

### 1. Enable the Remote Control Server in SnapSolve

Add (or verify) the following in `config/config.json`:

```json
{
  "enable_remote_control": true,
  "remote_control_host": "0.0.0.0",
  "remote_control_port": 8080
}
```

You can also toggle this from the SnapSolve **Config UI** (right-click the tray icon → *Settings* → *Remote Control* tab).

### 2. Allow the Port Through Windows Firewall

Run **once** in an elevated PowerShell:

```powershell
New-NetFirewallRule -DisplayName "SnapSolve Remote Control" `
    -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow
```

### 3. Find Your PC's Local IP Address

```powershell
ipconfig
```

Look for the **IPv4 Address** under your active Wi-Fi or Ethernet adapter (e.g., `192.168.1.100`).

### 4. Connect from the Android App

1. Open **SnapSolve Remote Control** on your phone.
2. Enter your PC's IP address and port (`8080` by default).
3. Tap **Connect**.
4. A successful connection enables the touchpad and all action buttons.

### 5. Verify

Open a browser on your phone and navigate to `http://<your-pc-ip>:8080/status`. You should see a JSON response confirming the server is running.

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