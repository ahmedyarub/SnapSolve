# Remote Screen and Audio Capture Guide

Since SnapSolve captures the local screen and audio, it does not natively provide a server endpoint to receive network media streams. To use SnapSolve with a remote computer (like a Mac or a secondary Windows laptop), you must route the remote computer's screen and audio to your main Windows PC running SnapSolve.

This guide covers the best methods to accomplish this, ranging from zero-software hardware solutions to lightweight network scripts.

## Table of Contents
1. [Hardware: HDMI Capture Card (Recommended)](#1-hardware-hdmi-capture-card-recommended)
2. [Software: Network Streaming from macOS](#2-software-network-streaming-from-macos)
3. [Software: Network Streaming from Windows](#3-software-network-streaming-from-windows)

---

## 1. Hardware: HDMI Capture Card (Recommended)

A generic USB 3.0 HDMI Video Capture Card (usually $15-$20) is the most robust and hassle-free solution. It requires zero admin rights or drivers on either the host or client machine. The remote computer simply thinks it is connected to an external monitor, and your main PC sees it as a standard USB Webcam and Microphone.

### Setting Up the Windows PC (Receiver)

**1. Reproducing the Video (Screen)**
* **Option A: Windows Camera App (Built-in)**: Open the Start Menu, type "Camera", and open the built-in app. Click the "Change Camera" icon until it switches to the Mac/Laptop's screen. Point SnapSolve to this window.
* **Option B: OBS Studio (Best Quality)**: Open OBS, add a "Video Capture Device" for your USB Capture Card. Right-click the video preview and select "Windowed Projector (Preview)". This creates a clean, borderless window for SnapSolve to capture.

**2. Reproducing the Audio**
You can use Windows' native features to forward the capture card's audio to your speakers, allowing SnapSolve's system loopback to hear it automatically.
1. Press `Win + R`, type `mmsys.cpl` to open the classic Sound Control Panel.
2. Go to the **Recording** tab and double-click your USB Capture Card.
3. Go to the **Listen** tab, check **"Listen to this device"**, and select your default playback device.
*Note: If you use OBS Studio, you can alternatively use OBS's Audio Monitoring feature instead of Windows settings.*

### Setting Up a macOS Client (Sender)

macOS natively allows sending system audio over HDMI, but handling Bluetooth microphones (like AirPods Max) requires some specific routing.

**1. Forwarding System Audio (What you hear)**
To hear audio in your Bluetooth headphones *and* send it to the HDMI capture card simultaneously:
1. Open **Audio MIDI Setup** (`Applications > Utilities`).
2. Click the **+** button -> **Create Multi-Output Device**.
3. Check the boxes for your Bluetooth Headphones and your HDMI Capture Card.
4. Right-click the new Multi-Output Device and select **Use This Device For Sound Output**.

> [!NOTE]
> When using a Multi-Output Device, the physical volume keys on your Mac keyboard are disabled by macOS. However, if your headphones have independent hardware volume controls (like the **Digital Crown on AirPods Max**), those physical buttons will continue to work perfectly for adjusting your personal listening volume!

**2. Forwarding Microphone Audio (What you speak)**
To send your Bluetooth microphone's input down the HDMI cable *without* hearing an echo:
* **Option A: LadioCast (Free on Mac App Store)**: Open LadioCast. Set **Input 1** to your Bluetooth Headphones, and **Main Output** to your HDMI Capture Card. Click the **Main** button under Input 1.
* **Option B: GarageBand (Pre-installed)**: Create an empty project with a Microphone track. Go to Settings > Audio/MIDI. Set Output to HDMI, and Input to Bluetooth Headphones. Click the "Input Monitoring" button on the track.

### Setting Up a Windows Client (Sender)

If the remote machine is a Windows laptop, you can route the audio natively.

**1. Forwarding System Audio**
1. Open Sound Control Panel (`mmsys.cpl`) -> **Recording** tab.
2. Right-click an empty space and check **"Show Disabled Devices"**.
3. Enable **Stereo Mix**, double-click it, go to the **Listen** tab.
4. Check **"Listen to this device"** and point it to your HDMI Capture Card.

**2. Forwarding Microphone Audio**
1. In the same **Recording** tab, double-click your Headset Microphone.
2. Go to the **Listen** tab, check **"Listen to this device"**, and select the HDMI Capture Card.

---

## 2. Software: Network Streaming from macOS

If you do not have an HDMI capture card, you can stream the screen and audio over your local network.

### Option A: VLC Media Player (Ready App)
VLC can capture your desktop and stream it without needing admin rights.
1. Open VLC on Mac -> **File > Open Capture Device** -> select "Screen".
2. Check **Stream output** -> Settings -> Output Type: **UDP**, enter your Windows PC's IP and a port (e.g., `1234`).
3. On Windows, open VLC and open network stream `udp://@:1234`. Point SnapSolve to this window.

### Option B: Python Flask Web Stream (Minimal Script)
This broadcasts the Mac's screen as an MJPEG webpage.
1. Install dependencies: `pip3 install --user Flask mss Pillow`
2. Run the following script:
```python
from flask import Flask, Response
import mss
import io
from PIL import Image

app = Flask(__name__)

def generate_frames():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        while True:
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            img_io = io.BytesIO()
            img.save(img_io, 'JPEG', quality=50)
            img_io.seek(0)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + img_io.read() + b'\r\n')

@app.route('/')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```
3. Open `http://<MAC_IP>:5000` in a web browser on Windows.

### Option C: FFmpeg (Standalone Binary)
Download the FFmpeg binary for macOS. To stream video:
```bash
./ffmpeg -f avfoundation -i "1:none" -c:v libx264 -preset ultrafast -tune zerolatency -f mpegts udp://<WINDOWS_IP>:1234
```

---

## 3. Software: Network Streaming from Windows

If both machines are Windows, you can use the built-in "Wireless Display" feature to stream the screen and audio over Wi-Fi natively.

1. **On your main PC:** Go to Settings -> System -> **Projecting to this PC**. Set it to "Available everywhere". Open the **Connect** app.
2. **On your Windows laptop:** Press **Windows Key + K**. Click on your main PC in the list.
3. Your main PC will display a window containing your laptop's screen and audio. Point SnapSolve to that window.
