# JioPhone F90M // Optical Ground Station & Telemetry Hub v3.0

Professional optical streaming, real-time BMS battery telemetry, remote process control, and virtual keypad ground station for the **LYF JioPhone F90M** (Qualcomm Snapdragon 205 MSM8909) running **KaiOS 2.5 / Nokia 8110 4G** firmware.

---

## 📸 Architecture & Overview

```
                      ┌─────────────────────────────────────────┐
                      │            LYF JioPhone F90M            │
                      │  Snapdragon 205 (Dual Cortex-A7 1.1GHz) │
                      │       KaiOS 2.5 (Nokia 8110 base)       │
                      └───────────────────┬─────────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  │ Wireless ADB (:5555) / USB Composite (9039)    │
                  │ Gecko RDP Debugger Socket (:6000)             │
                  │ Frame Uploads (POST /api/camera/upload)       │
                  └───────────────────────┬───────────────────────┘
                                          │
                                          ▼
                      ┌─────────────────────────────────────────┐
                      │       PC Telemetry Server (Python)      │
                      │      telemetry/server.py (Ports 80/8000)│
                      │   - VM-BMS Fuel Gauge Analytics         │
                      │   - Dynamic Hardware Key Injector       │
                      │   - Gecko RDP Remote App Launcher       │
                      └───────────────────┬─────────────────────┘
                                          │
                                          ▼
                      ┌─────────────────────────────────────────┐
                      │    Modern Browser Mission Control UI    │
                      │   - Right 50%: Optical Viewfinder (ISP) │
                      │   - Left 50%: BMS & Thermal Telemetry   │
                      │   - Video Recording & Chunking Engine   │
                      │   - Bottom: Keypad + PC Typing Bridge   │
                      └─────────────────────────────────────────┘
```

---

## 🛠️ Prerequisites & Hardware Specifications

* **Target Device**: LYF JioPhone F90M (Qualcomm Snapdragon 205 MSM8909, 512 MB RAM, 4 GB eMMC).
* **Firmware**: Nokia 8110 4G (KaiOS 2.5, Build `17.00.17.01 dev-keys`) + GerdaOS File Manager.
* **Sensors**: 2.0 MP Rear Camera (`/dev/video0`, `/dev/video1`), 0.3 MP Front Camera (`/dev/video2`).
* **Battery**: Foxconn FIH 2000 mAh Li-ion (`FIH2000-lb4105`) with Qualcomm PM8909 VM-BMS fuel gauge.
* **Host PC Environment**:
  * Windows 10/11 or Linux.
  * Python 3.8+ (`http.server`, `socketserver`, `threading`, `ssl`, `json`).
  * Android Platform Tools (`adb.exe`).

---

## 🚀 Setup & Installation Guide

### Step 1: Establish Device Connection (USB or Wireless)

1. Connect the phone to your PC via a micro-USB cable.
2. Verify ADB detects the device:
   ```bash
   adb devices
   # Output: f94e529    device
   ```
3. Enable Wireless ADB mode:
   ```bash
   adb tcpip 5555
   ```
4. Query the phone's local Wi-Fi IP and connect wirelessly:
   ```bash
   adb shell getprop dhcp.wlan0.ipaddress
   # Example output: 192.168.1.8

   adb connect 192.168.1.8:5555
   ```
   *(Once connected over Wi-Fi, the physical USB cable can be unplugged).*

---

### Step 2: Sideload & Install the Camera App (`cam_app.zip`)

The custom camera streamer is a certified KaiOS packaged webapp located in `cam_app/` and bundled as `cam_app.zip`. It acquires hardware permissions for Qualcomm camera sensors, high-FPS canvas capture, and CPU wake locks.

#### Method A: Direct Sideloading via Gecko RDP (Fastest & Automated)
```bash
# 1. Forward the phone's Gecko debugger socket
adb forward tcp:6000 localfilesystem:/data/local/debugger-socket

# 2. Stage package on device
adb push cam_app.zip /data/local/tmp/b2g/cam_app.zip
adb shell "mkdir -p /data/local/tmp/b2g/cam_app && busybox unzip -o /data/local/tmp/b2g/cam_app.zip -d /data/local/tmp/b2g/cam_app"

# 3. Run installation helper
python scratch/reinstall_app.py
```

#### Method B: Installation via GerdaOS File Manager
1. Push the archive to storage:
   ```bash
   adb push cam_app.zip /sdcard/cam_app.zip
   ```
2. Open the **"Files"** app on the phone.
3. Select `cam_app.zip` and press **Open** to install.

---

### Step 3: Launch the Ground Station Telemetry Server

Run the unified telemetry server from the project directory:

```powershell
python telemetry/server.py
```

The server binds to:
* **Port 8000**: Main Web Dashboard (`http://localhost:8000` or `http://192.168.1.15:8000`).
* **Port 80**: Default HTTP listener (`http://192.168.1.15` redirects mobile visitors directly to `/c`).
* **Port 8443**: Self-signed SSL listener for W3C Secure Context camera streaming.

---

### Step 4: Stream Video & Control Phone Remotely

1. Open `http://localhost:8000` in any modern desktop browser (Chrome, Edge, Firefox).
2. Click **"🚀 Launch Cam App"** on the header bar.
   * *The server uses Gecko RDP (Port 6000) to automatically launch the camera app on the phone screen!*
3. The live optical feed will immediately stream into the viewfinder on the right half of the screen.

---

## 🎛️ Key Features & Operational Guide

### 1. 50/50 Screen Layout (Camera in Main Focus)
* **Right Half (Main Focus)**:
  * Optical Viewfinder rendering 320x240 frames from Qualcomm VFE pipeline.
  * Real-time FPS indicator and orientation rotation controls (`🔄 90°` steps: `0°`, `90°`, `180°`, `270°`).
  * Configurable camera dispatch rate (`~25 FPS (0.04s)`, `10 FPS (0.1s)`, `0.5s`, `1s`, `2s`).
* **Left Half (Telemetry Stack)**:
  * **Qualcomm VM-BMS Fuel Gauge**: Cell Voltage, OCV, Current Draw (mA), Remaining Capacity (mAh), Internal Resistance (152 mΩ healthy baseline).
  * **Dynamic Active Runtime**: Computes live battery life under instantaneous load ($T = C_{rem} / I_{discharge}$) and 60-sample rolling average.
  * **Hardware Thermals**: Snapdragon 205 CPU core, PMIC power controller, PA radio, and cell temperature.
  * **RAM & Compute**: 405 MB total RAM utilization gauge and system uptime.
* **Down-Below (Control Deck)**:
  * **Virtual Remote Keypad**: Full tactile Softkeys, D-Pad, Number keys, Call, and unified End/Wake (key 116 on `event1`).
  * **Interactive PC Keyboard Bridge**: Click and type directly with your physical computer keyboard. Letters are dynamically mapped to T9 sequences, Backspace sends DEL, and Enter sends OK.

---

### 2. Video Recording & Size Chunking Engine
The dashboard includes an enterprise-grade client-side video recording system using HTML5 canvas capture and the W3C `MediaRecorder` API:

1. **Configurable Size Chunking**:
   * Set chunk threshold (e.g. `5 MB`, `10 MB`, `25 MB`).
   * The recorder monitors frame accumulation in real time. As soon as the accumulated video data reaches the threshold, the chunk is automatically finalized into a standalone `.webm` / `.mp4` file.
2. **Auto-Download or Batch Save**:
   * Enable **"Auto-download chunks"** to automatically save each chunk to your computer's Downloads directory as it completes.
   * All finalized chunks are listed in the **Finalized Chunks Table** with individual `▶ Play` preview and `⬇ Save` buttons.
3. **Orientation Preservation**:
   * Rotation applied in the UI (`0°`, `90°`, `180°`, `270°`) is rendered directly to the underlying canvas, guaranteeing recorded video files are properly oriented.

---

### 3. Power Optimization & Background Stripping
* **Headless Linux Server Mode (`stop b2g`)**:
  * Terminates the KaiOS user interface.
  * Recovers **~250 MB of RAM** immediately.
  * Drops idle battery draw from ~200 mA to **~30 mA**.
* **Rootless 14-Daemon Bloat Stripper**:
  * Shuts down unnecessary background services (GPS `loc_launcher`, cellular modem daemons, OEM telemetry `tctd`, audio, keystore) via Android `init` property triggers (`ctl.stop`).
  * Requires **no root privileges**.
  * Frees 65 MB of RAM and reduces ZRAM swap to 7 MB, dedicating 100% of CPU cycles to video transmission.
* **Physical LCD Screen Blackout**:
  * Click **"🌑 Screen OFF"** or press Key `0` / Key `*` in the app.
  * Extinguishes the physical LCD backlight (`/sys/class/leds/lcd-backlight/brightness` = `0`), cutting power consumption without interrupting video streaming.

---

## 📁 Repository Structure

```
jio/
├── README.md                  # Master setup and operational guide
├── DEV_DIARY.md               # Chronological dev diary of all engineering milestones
├── KEYBOARD_ANALYSIS.md       # Hardware snap-dome oxidation & kernel debounce analysis
├── BATTERY_ANALYSIS.md        # Qualcomm BMS fuel gauge math & discharge formulas
├── CAMERA_SUBSYSTEM.md        # Qualcomm V4L2 device nodes & ISP diagnostic verification
├── SYSTEM_AND_STORAGE.md      # Memory architecture, ZRAM swap, thermals, debloating
├── ALTERNATIVE_OS_GUIDE.md    # OS comparison (Mainline Linux, GerdaOS, KaiOS 2.5)
├── cam_app/                   # Certified KaiOS Camera App Source Code
│   ├── manifest.webapp        # Certified app manifest (camera, power, systemXHR permissions)
│   ├── index.html             # Video viewport & softkey UI
│   ├── app.js                 # Qualcomm mozCameras HAL driver & HTTP frame uploader
│   ├── style.css              # Dark slate stylesheet
│   ├── icon56.png             # KaiOS application icon (56x56)
│   └── icon112.png            # KaiOS application icon (112x112)
├── cam_app.zip                # Sideloadable packaged application archive
├── telemetry/                 # Host PC Ground Station & Telemetry Hub
│   ├── server.py              # Multi-port server (80, 8000, 8443) & Web Dashboard
│   ├── cert.pem               # SSL certificate for HTTPS secure context
│   └── key.pem                # SSL private key
└── scratch/                   # Engineering scripts & RDP debugging utilities
    ├── launch_cam.py          # Standalone Gecko RDP app launcher
    ├── reinstall_app.py       # Automated Gecko RDP package deployer
    ├── query_rdp.py           # Gecko RDP actor inspection
    └── test_upload.py         # Standalone frame upload tester
```

---

## 📡 API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/telemetry` | `GET` | Returns full JSON telemetry payload (battery, thermals, memory, uptime, screen state). |
| `/api/telemetry/interval?sec=X` | `GET` | Dynamically updates the backend ADB telemetry sampling interval. |
| `/api/camera/stream` | `GET` | Returns the latest JPEG frame buffer from the phone. |
| `/api/camera/upload` | `POST` | Ingestion endpoint where the phone posts live JPEG frames. |
| `/api/camera/interval?sec=X` | `GET` | Synchronizes framerate sleep duration back to the phone. |
| `/api/camera/screen_toggle` | `GET` | Toggles the phone's physical LCD backlight on/off remotely. |
| `/api/app/launch` | `GET` | Remotely launches the camera app via Gecko RDP on port 6000. |
| `/api/keypad/press?code=X` | `GET` | Transmits an individual Linux hardware keycode to `/dev/input/eventX`. |
| `/api/keyboard/char?c=X` | `GET` | Bridges PC keystrokes to T9 multi-press sequences on the phone. |
| `/api/system/b2g?action=X` | `GET` | Controls the KaiOS GUI (`start` or `stop` for Ultra Eco Mode). |
| `/api/system/lean_mode?action=X`| `GET` | Strips or restores the 14 background bloat daemons. |
| `/api/network/scan` | `GET` | Probes local subnet (`/24`) concurrently on port 5555 to discover phone IP. |
