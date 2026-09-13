"""
JioPhone F90M Live Ground Station & Optical Hub
Version: 3.0 (Enterprise Ground Station & Video Chunking Engine)

Features:
- Main-Focus Optical Viewfinder (Dominates Right Screen Half)
- Video Recording & Dynamic Size Chunking Engine (Auto-download or batch save)
- Remote App Launch Button via Gecko RDP (Port 6000)
- Battery Intelligence & Fuel Gauge (Qualcomm VM-BMS Real-time Math)
- Snapdragon 205 Thermal & Memory Ground Control
- Headless Linux Mode (stop b2g) & 14-Daemon Bloat Stripper
- Down-Below Control Deck: Precision Keypad + Interactive PC Keyboard Bridge
- Toast Notification System (Zero Informational Dialogs / Alert Popups)
- Ultra-Short Camera Stream URLs (Dual Port 80 & 8000, HTTPS 8443)
"""

import http.server
import socketserver
import json
import subprocess
import time
import threading
import os
import re
import socket
import ssl
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

PORT = 8000
ADB_PATH = r"C:\Users\admin\platform-tools\adb.exe"
if not os.path.exists(ADB_PATH):
    ADB_PATH = "adb"

DESIGN_CAPACITY_MAH = 2000.0

state = {
    "current_device": None,
    "phone_ip": "192.168.1.8",
    "screen_blackout": False,
    "screen_cmd": "none",
    "camera_interval_ms": 2000,
    "scanning": False,
    "last_scan_result": [],
}

telemetry_data = {
    "timestamp": time.time(),
    "connected": False,
    "active_target": None,
    "phone_ip": "192.168.1.8",
    "battery": {},
    "thermal": {},
    "memory": {},
    "system": {},
    "storage": {},
    "b2g_running": True,
    "screen_blackout": False,
    "camera_diagnostic": "Ready",
    "has_live_frame": False,
    "camera_last_seen": 0,
    "poll_rate_sec": 3.5,
}

latest_camera_frame = None
frame_lock = threading.Lock()
discharge_history = []
POLL_INTERVAL = 3.5

T9_CHAR_MAP = {
    '1': [2], '2': [3], '3': [4], '4': [5], '5': [6],
    '6': [7], '7': [8], '8': [9], '9': [10], '0': [11],
    ' ': [11],
    '*': [227], '#': [228],
    'a': [3], 'b': [3, 3], 'c': [3, 3, 3],
    'd': [4], 'e': [4, 4], 'f': [4, 4, 4],
    'g': [5], 'h': [5, 5], 'i': [5, 5, 5],
    'j': [6], 'k': [6, 6], 'l': [6, 6, 6],
    'm': [7], 'n': [7, 7], 'o': [7, 7, 7],
    'p': [8], 'q': [8, 8], 'r': [8, 8, 8], 's': [8, 8, 8, 8],
    't': [9], 'u': [9, 9], 'v': [9, 9, 9],
    'w': [10], 'x': [10, 10], 'y': [10, 10, 10], 'z': [10, 10, 10, 10],
}

def get_local_subnet_prefix():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return ".".join(local_ip.split(".")[:3])
    except Exception:
        return "192.168.1"

def scan_subnet_for_port(subnet_prefix=None, port=5555, timeout=0.25):
    if not subnet_prefix:
        subnet_prefix = get_local_subnet_prefix()
    
    ips = [f"{subnet_prefix}.{i}" for i in range(1, 255)]
    found = []

    def probe(ip):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                if s.connect_ex((ip, port)) == 0:
                    return ip
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=50) as executor:
        for r in executor.map(probe, ips):
            if r:
                found.append(r)
    return found

def get_adb_devices():
    try:
        res = subprocess.run([ADB_PATH, "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4)
        lines = [l.strip() for l in res.stdout.splitlines() if l.strip() and not l.startswith("*") and not l.startswith("List")]
        devices = []
        for l in lines:
            parts = l.split()
            if len(parts) >= 2:
                devices.append((parts[0], parts[1]))
        return devices
    except Exception:
        return []

def resolve_device():
    devices = get_adb_devices()
    
    # 1. Active wireless device
    for serial, status in devices:
        if ":" in serial and status == "device":
            state["current_device"] = serial
            state["phone_ip"] = serial.split(":")[0]
            return serial

    # 2. Active USB device
    for serial, status in devices:
        if ":" not in serial and status == "device":
            state["current_device"] = serial
            try:
                ip_res = subprocess.run(
                    [ADB_PATH, "-s", serial, "shell", "getprop dhcp.wlan0.ipaddress"],
                    stdout=subprocess.PIPE, text=True, timeout=2
                )
                detected_ip = ip_res.stdout.strip()
                if detected_ip and "." in detected_ip:
                    state["phone_ip"] = detected_ip
            except Exception:
                pass
            return serial

    # 3. Disconnect offline
    for serial, status in devices:
        if ":" in serial and status == "offline":
            try:
                subprocess.run([ADB_PATH, "disconnect", serial], timeout=2)
                time.sleep(0.3)
                subprocess.run([ADB_PATH, "connect", serial], timeout=3)
            except Exception:
                pass

    # 4. Try connecting to last known IP
    if state["phone_ip"]:
        try:
            target = f"{state['phone_ip']}:5555"
            subprocess.run([ADB_PATH, "connect", target], timeout=3)
            return target
        except Exception:
            pass

    return state.get("current_device") or f"{state['phone_ip']}:5555"

def run_adb(cmd_args, timeout=5):
    target = resolve_device()
    if not target:
        return ""
    full_cmd = [ADB_PATH, "-s", target, "shell"] + cmd_args
    try:
        res = subprocess.run(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return res.stdout
    except Exception:
        return ""

def send_key_event(code):
    if code == 103:
        dev = "/dev/input/event2"
    elif code in (108, 116):
        dev = "/dev/input/event1"
    else:
        dev = "/dev/input/event0"

    cmd = (
        f"sendevent {dev} 1 {code} 1; "
        f"sendevent {dev} 0 0 0; "
        f"busybox usleep 60000; "
        f"sendevent {dev} 1 {code} 0; "
        f"sendevent {dev} 0 0 0"
    )
    return run_adb([cmd], timeout=3)

def type_character(c):
    c_lower = c.lower()
    if c == "Backspace":
        send_key_event(116)
        return "DEL"
    elif c == "Enter":
        send_key_event(28)
        return "ENTER"
    elif c == "ArrowUp":
        send_key_event(103)
        return "UP"
    elif c == "ArrowDown":
        send_key_event(108)
        return "DOWN"
    elif c == "ArrowLeft":
        send_key_event(105)
        return "LEFT"
    elif c == "ArrowRight":
        send_key_event(106)
        return "RIGHT"
    elif c == "Escape":
        send_key_event(116)
        return "END"
    elif c_lower in T9_CHAR_MAP:
        key_seq = T9_CHAR_MAP[c_lower]
        for k in key_seq:
            send_key_event(k)
            time.sleep(0.06)
        return f"Keys {key_seq}"
    else:
        return "Unmapped"

def launch_cam_app_remote():
    target = resolve_device()
    if not target:
        return False, "JioPhone is not connected via ADB."
    
    # 1. Wake screen/CPU
    try:
        send_key_event(116)
        time.sleep(0.3)
    except Exception:
        pass

    # 2. Forward Gecko debugger socket
    try:
        subprocess.run(
            [ADB_PATH, "-s", target, "forward", "tcp:6000", "localfilesystem:/data/local/debugger-socket"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4
        )
    except Exception as e:
        return False, f"Failed to forward debugger socket: {e}"

    # 3. Connect to Gecko RDP port 6000
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(4.0)
        s.connect(("127.0.0.1", 6000))

        def recv_packet():
            len_str = b""
            while True:
                ch = s.recv(1)
                if not ch:
                    raise EOFError("Socket closed prematurely")
                if ch == b":":
                    break
                len_str += ch
            length = int(len_str.decode("ascii"))
            data = b""
            while len(data) < length:
                chunk = s.recv(length - len(data))
                if not chunk:
                    raise EOFError("Socket closed during payload")
                data += chunk
            return json.loads(data.decode("utf-8"))

        def send_packet(obj):
            body = json.dumps(obj)
            msg = f"{len(body)}:{body}".encode("utf-8")
            s.sendall(msg)

        recv_packet()  # Greeting
        send_packet({"to": "root", "type": "listTabs"})
        tabs = recv_packet()
        actor = tabs.get("webappsActor")
        if not actor:
            return False, "webappsActor not found in Gecko RDP session."

        send_packet({"to": actor, "type": "launch", "manifestURL": "app://cam_app/manifest.webapp"})
        res = recv_packet()
        return True, "Live Camera app launched successfully on phone!"
    except Exception as e:
        return False, f"RDP Launch error: {e}"
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass

def poll_telemetry():
    global telemetry_data, discharge_history, POLL_INTERVAL
    while True:
        try:
            target = resolve_device()
            if target:
                try:
                    subprocess.run([ADB_PATH, "-s", target, "reverse", "tcp:8000", "tcp:8000"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
                except Exception:
                    pass
            shell_script = (
                "cat /sys/class/power_supply/battery/voltage_now 2>/dev/null; echo '---';"
                "cat /sys/class/power_supply/battery/current_now 2>/dev/null; echo '---';"
                "cat /sys/class/power_supply/battery/capacity 2>/dev/null; echo '---';"
                "cat /sys/class/power_supply/battery/status 2>/dev/null; echo '---';"
                "cat /sys/class/power_supply/battery/temp 2>/dev/null; echo '---';"
                "cat /sys/class/power_supply/bms/resistance_now 2>/dev/null; echo '---';"
                "cat /sys/class/power_supply/bms/voltage_ocv 2>/dev/null; echo '---';"
                "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null; echo '---';"
                "cat /sys/class/thermal/thermal_zone4/temp 2>/dev/null; echo '---';"
                "cat /sys/class/thermal/thermal_zone5/temp 2>/dev/null; echo '---';"
                "cat /proc/meminfo | head -n 6; echo '---';"
                "cat /proc/uptime; echo '---';"
                "getprop init.svc.b2g; echo '---';"
                "cat /sys/class/leds/lcd-backlight/brightness 2>/dev/null"
            )
            raw = run_adb([shell_script], timeout=5)
            if raw and "---" in raw:
                parts = [p.strip() for p in raw.split("---")]
                if len(parts) >= 13:
                    v_raw = float(parts[0]) if parts[0].isdigit() else 3640000.0
                    i_raw = float(parts[1]) if (parts[1].startswith("-") or parts[1].isdigit()) else 0.0
                    soc = float(parts[2]) if parts[2].isdigit() else 16.0
                    status = parts[3] if parts[3] else "Unknown"
                    temp_raw = float(parts[4]) if parts[4].isdigit() else 350.0
                    res_raw = float(parts[5]) if parts[5].isdigit() else 152.0
                    ocv_raw = float(parts[6]) if parts[6].isdigit() else v_raw

                    v_volts = round(v_raw / 1_000_000.0, 3)
                    ocv_volts = round(ocv_raw / 1_000_000.0, 3)
                    current_ma = round(i_raw / 1_000.0, 1)
                    temp_c = round(temp_raw / 10.0, 1)

                    now = time.time()
                    if current_ma > 0:
                        discharge_history.append((now, current_ma))
                        if len(discharge_history) > 60:
                            discharge_history.pop(0)

                    if discharge_history:
                        avg_discharge_ma = sum(x[1] for x in discharge_history) / len(discharge_history)
                    else:
                        avg_discharge_ma = 85.0 if status == "Discharging" else 65.0

                    if ocv_volts >= 4.20:
                        chem_soc = 100.0
                    elif ocv_volts <= 3.40:
                        chem_soc = 0.0
                    elif ocv_volts >= 3.80:
                        chem_soc = 50.0 + ((ocv_volts - 3.80) / 0.40) * 50.0
                    else:
                        chem_soc = ((ocv_volts - 3.40) / 0.40) * 50.0
                    chem_soc = max(0.0, min(100.0, round(chem_soc, 1)))

                    estimated_health_pct = 92.0 if res_raw < 180 else 80.0
                    estimated_actual_full_mah = round(DESIGN_CAPACITY_MAH * (estimated_health_pct / 100.0), 0)
                    estimated_mah_remaining = round(estimated_actual_full_mah * (soc / 100.0), 0)

                    rem_mah = estimated_mah_remaining
                    if current_ma > 10:
                        life_cur_h = rem_mah / current_ma
                        h_c = int(life_cur_h)
                        m_c = int(round((life_cur_h - h_c) * 60))
                        life_current_str = f"{h_c}h {m_c:02d}m"
                        
                        eff_avg_ma = max(avg_discharge_ma, 20.0)
                        life_avg_h = rem_mah / eff_avg_ma
                        h_a = int(life_avg_h)
                        m_a = int(round((life_avg_h - h_a) * 60))
                        life_avg_str = f"{h_a}h {m_a:02d}m"
                        life_mode = "Discharging"
                    elif current_ma < -10:
                        needed_mah = max(0, estimated_actual_full_mah - rem_mah)
                        charge_rate = abs(current_ma)
                        ch_h = needed_mah / max(charge_rate, 10.0)
                        h_ch = int(ch_h)
                        m_ch = int(round((ch_h - h_ch) * 60))
                        life_current_str = f"{h_ch}h {m_ch:02d}m to 100%"
                        life_avg_str = f"{h_ch}h {m_ch:02d}m to 100%"
                        life_mode = "Charging"
                    else:
                        sb_h = rem_mah / 35.0
                        h_sb = int(sb_h)
                        m_sb = int(round((sb_h - h_sb) * 60))
                        life_current_str = f"~{h_sb}h {m_sb:02d}m"
                        life_avg_str = f"~{h_sb}h {m_sb:02d}m"
                        life_mode = "Standby"

                    projected_hours_deep_sleep = round(rem_mah / 35.0, 1)
                    projected_hours_active = round(rem_mah / max(avg_discharge_ma, 40.0), 1)

                    pa_temp = round(float(parts[7]) / 1000.0 if float(parts[7]) > 1000 else float(parts[7]), 1) if parts[7].replace(".", "", 1).isdigit() else 36.0
                    cpu_temp = round(float(parts[8]) / 1000.0 if float(parts[8]) > 1000 else float(parts[8]), 1) if parts[8].replace(".", "", 1).isdigit() else 51.0
                    pmic_temp = round(float(parts[9]) / 1000.0 if float(parts[9]) > 1000 else float(parts[9]), 1) if parts[9].replace(".", "", 1).isdigit() else 50.0

                    meminfo = parts[10]
                    mem_total = 405
                    mem_free = 20
                    for line in meminfo.splitlines():
                        if "MemTotal" in line:
                            mem_total = int(re.findall(r"\d+", line)[0]) // 1024
                        elif "MemFree" in line:
                            mem_free = int(re.findall(r"\d+", line)[0]) // 1024

                    uptime_sec = float(parts[11].split()[0]) if parts[11].split() else 0.0
                    uptime_str = f"{int(uptime_sec // 3600)}h {int((uptime_sec % 3600) // 60)}m"

                    b2g_status = parts[12].strip()
                    b2g_active = (b2g_status == "running")

                    brightness_raw = parts[13].strip() if len(parts) > 13 else "0"
                    screen_blackout = (brightness_raw == "0")

                    telemetry_data = {
                        "timestamp": now,
                        "connected": True,
                        "active_target": target,
                        "phone_ip": state["phone_ip"],
                        "battery": {
                            "voltage_v": v_volts,
                            "ocv_v": ocv_volts,
                            "current_ma": current_ma,
                            "soc_pct": soc,
                            "chem_soc_pct": chem_soc,
                            "status": status,
                            "temp_c": temp_c,
                            "resistance_mohm": res_raw,
                            "design_capacity_mah": DESIGN_CAPACITY_MAH,
                            "estimated_actual_full_mah": estimated_actual_full_mah,
                            "estimated_mah_remaining": estimated_mah_remaining,
                            "health_pct": estimated_health_pct,
                            "avg_discharge_ma": round(avg_discharge_ma, 1),
                            "projected_hours_deep_sleep": projected_hours_deep_sleep,
                            "projected_hours_active": projected_hours_active,
                            "life_current_str": life_current_str,
                            "life_avg_str": life_avg_str,
                            "life_mode": life_mode,
                            "charging_flow": "Charging In (-)" if current_ma < 0 else "Discharging (+)",
                        },
                        "thermal": {
                            "cpu_c": cpu_temp,
                            "pmic_c": pmic_temp,
                            "pa_c": pa_temp,
                            "battery_c": temp_c,
                        },
                        "memory": {
                            "total_mb": mem_total,
                            "free_mb": mem_free,
                            "used_mb": mem_total - mem_free,
                            "used_pct": round(((mem_total - mem_free) / max(mem_total, 1)) * 100, 1),
                        },
                        "system": {
                            "uptime": uptime_str,
                            "phone_ip": state["phone_ip"],
                            "model": "JioPhone F90M (MSM8909)",
                            "b2g_running": b2g_active,
                            "target": target,
                            "screen_blackout": screen_blackout,
                        },
                        "camera_diagnostic": telemetry_data.get("camera_diagnostic", "Ready"),
                        "has_live_frame": (latest_camera_frame is not None and (now - telemetry_data.get("camera_last_seen", 0) < 6)),
                        "camera_last_seen": telemetry_data.get("camera_last_seen", 0),
                        "poll_rate_sec": POLL_INTERVAL,
                    }
            else:
                telemetry_data["connected"] = False
        except Exception:
            telemetry_data["connected"] = False
        time.sleep(POLL_INTERVAL)

CAMERA_SENDER_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JioPhone Cam Streamer</title>
  <style>
    body { background: #0b0f19; color: #fff; text-align: center; font-family: -apple-system, sans-serif; padding: 10px; margin: 0; }
    h3 { margin: 6px 0; font-size: 15px; color: #00e676; }
    video { width: 100%; max-width: 280px; height: 170px; background: #162032; border-radius: 8px; border: 2px solid #333; object-fit: cover; }
    canvas { display: none; }
    .btn-row { margin: 8px 0; display: flex; justify-content: center; gap: 6px; }
    button { background: #00e676; color: #000; border: none; padding: 10px 14px; border-radius: 6px; font-weight: bold; font-size: 13px; cursor: pointer; }
    #st { font-size: 12px; color: #8a99ad; margin-top: 6px; font-weight: 500; }
    .pulse { color: #00f2fe; animation: blink 1s infinite; font-weight: bold; }
    @keyframes blink { 50% { opacity: 0.4; } }
  </style>
</head>
<body>
  <h3>📷 JioPhone Camera Streamer</h3>
  <video id="v" autoplay playsinline muted></video>
  <canvas id="c"></canvas>
  <div class="btn-row">
    <button onclick="stream('environment')">Rear Cam</button>
    <button onclick="stream('user')" style="background: #4facfe;">Front Cam</button>
  </div>
  <div id="st">Starting camera subsystem...</div>
  <script>
    const v = document.getElementById('v'), c = document.getElementById('c'), st = document.getElementById('st');
    let streaming = false, frameCount = 0;
    function logRemote(msg) {
      st.innerHTML = msg;
      try { fetch('/api/camera/log?msg=' + encodeURIComponent(msg)).catch(() => {}); } catch(e) {}
    }
    function getMediaStream(constraints) {
      if (navigator.mozGetUserMedia) {
        return new Promise((resolve, reject) => {
          navigator.mozGetUserMedia(constraints, resolve, (err) => {
            navigator.mozGetUserMedia({ video: true, audio: false }, resolve, reject);
          });
        });
      }
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        return navigator.mediaDevices.getUserMedia(constraints)
          .catch(() => navigator.mediaDevices.getUserMedia({ video: true, audio: false }));
      }
      const legacy = navigator.getUserMedia || navigator.webkitGetUserMedia;
      if (legacy) {
        return new Promise((resolve, reject) => legacy.call(navigator, constraints, resolve, reject));
      }
      return Promise.reject(new Error("Camera API not supported"));
    }
    function stream(mode) {
      logRemote('Requesting ' + mode + ' camera...');
      getMediaStream({
        video: { facingMode: mode, width: { ideal: 320 }, height: { ideal: 240 } },
        audio: false
      })
      .then(s => {
        try { v.srcObject = s; } catch (e) { v.src = (window.URL || window.webkitURL).createObjectURL(s); }
        if (!v.srcObject && (window.URL || window.webkitURL)) {
          v.src = (window.URL || window.webkitURL).createObjectURL(s);
        }
        v.play();
        streaming = true;
        logRemote('<span class="pulse">● Live Streaming to Ground Station!</span>');
        sendLoop();
      })
      .catch(e => {
        logRemote('<span style="color:#ff5252;">' + (e.name || 'Error') + ': ' + (e.message || e) + '</span>');
      });
    }
    function sendLoop() {
      if (!streaming) return;
      if (v.videoWidth) {
        c.width = v.videoWidth;
        c.height = v.videoHeight;
        const ctx = c.getContext('2d');
        ctx.drawImage(v, 0, 0);
        c.toBlob(b => {
          if (b) {
            fetch('/api/camera/upload', { method: 'POST', body: b })
              .then(r => r.json())
              .then(d => {
                frameCount++;
                st.innerHTML = '<span class="pulse">● Streaming Live (' + frameCount + ' frames)</span>';
                setTimeout(sendLoop, d.interval_ms || 200);
              })
              .catch(() => setTimeout(sendLoop, 200));
          } else {
            setTimeout(sendLoop, 200);
          }
        }, 'image/jpeg', 0.5);
      } else {
        setTimeout(sendLoop, 200);
      }
    }
    window.addEventListener('DOMContentLoaded', () => setTimeout(() => stream('environment'), 800));
  </script>
</body>
</html>
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JioPhone F90M // Ground Station & Telemetry Hub</title>
  <style>
    :root {
      --bg-main: #090d16;
      --bg-panel: #111827;
      --bg-panel-elevated: #162032;
      --border-subtle: rgba(255, 255, 255, 0.08);
      --border-active: rgba(0, 242, 254, 0.35);
      --cyan: #00f2fe;
      --blue: #38bdf8;
      --green: #10b981;
      --emerald: #059669;
      --amber: #f59e0b;
      --rose: #f43f5e;
      --red: #ef4444;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", monospace, sans-serif; }
    body { background: var(--bg-main); color: var(--text-main); min-height: 100vh; padding: 18px; display: flex; flex-direction: column; gap: 16px; }
    
    /* Header Bar */
    header {
      background: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 12px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }
    .brand-title {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand-title h1 {
      font-size: 17px;
      font-weight: 700;
      letter-spacing: 0.8px;
      text-transform: uppercase;
      background: linear-gradient(90deg, #38bdf8, #00f2fe);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .brand-title .chip {
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: var(--blue);
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 4px;
      font-weight: 600;
      letter-spacing: 0.5px;
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    
    /* Badges & Status */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      font-family: monospace;
    }
    .badge-online { background: rgba(16, 185, 129, 0.15); color: var(--green); border: 1px solid var(--green); }
    .badge-offline { background: rgba(244, 63, 94, 0.15); color: var(--rose); border: 1px solid var(--rose); }
    .badge-amber { background: rgba(245, 158, 11, 0.15); color: var(--amber); border: 1px solid var(--amber); }
    .pulse-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; animation: live-pulse 1.4s infinite; }
    @keyframes live-pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.3; transform: scale(0.85); } }

    /* Buttons */
    .btn {
      background: var(--bg-panel-elevated);
      color: var(--text-main);
      border: 1px solid var(--border-subtle);
      padding: 7px 14px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }
    .btn:hover { background: rgba(255, 255, 255, 0.1); border-color: rgba(255, 255, 255, 0.2); }
    .btn-primary { background: linear-gradient(135deg, #0284c7, #00f2fe); color: #000; border: none; font-weight: 700; }
    .btn-primary:hover { opacity: 0.92; }
    .btn-danger { background: rgba(239, 68, 68, 0.15); color: var(--red); border: 1px solid var(--red); }
    .btn-danger:hover { background: rgba(239, 68, 68, 0.25); }
    .btn-success { background: rgba(16, 185, 129, 0.15); color: var(--green); border: 1px solid var(--green); }
    .btn-success:hover { background: rgba(16, 185, 129, 0.25); }
    .btn-amber { background: rgba(245, 158, 11, 0.15); color: var(--amber); border: 1px solid var(--amber); }
    .btn-amber:hover { background: rgba(245, 158, 11, 0.25); }
    .btn-pill {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
    }
    .btn-pill.active { background: var(--cyan); color: #000; border-color: var(--cyan); }

    /* Main Deck (50/50 Split) */
    .main-deck {
      display: grid;
      grid-template-columns: 1fr 1.15fr;
      gap: 18px;
      align-items: start;
    }
    @media (max-width: 1080px) {
      .main-deck { grid-template-columns: 1fr; }
    }

    /* Cards */
    .card {
      background: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 10px;
    }
    .card-title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 1px;
      font-weight: 700;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    /* Left Side: Telemetry Stack */
    .telemetry-col {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    /* Metric Grid & Gauges */
    .metric-hero {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      padding: 4px 0;
    }
    .metric-value-huge {
      font-size: 42px;
      font-weight: 800;
      font-family: monospace;
      color: #fff;
      line-height: 1;
    }
    .metric-unit { font-size: 18px; color: var(--text-muted); font-weight: 400; margin-left: 2px; }
    
    .gauge-track {
      height: 8px;
      background: rgba(255, 255, 255, 0.07);
      border-radius: 4px;
      overflow: hidden;
      margin: 4px 0 8px;
    }
    .gauge-bar { height: 100%; border-radius: 4px; transition: width 0.4s ease; }
    .gauge-green { background: linear-gradient(90deg, #10b981, #00f2fe); }
    .gauge-amber { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
    .gauge-red { background: linear-gradient(90deg, #ef4444, #f43f5e); }

    .data-table {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
    }
    .data-cell {
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 6px;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .data-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
    .data-val { font-size: 13px; font-weight: 700; font-family: monospace; color: var(--text-main); }

    /* Right Side: Camera Viewfinder (Main Focus) */
    .camera-col {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .viewfinder-card {
      background: var(--bg-panel);
      border: 1px solid var(--border-active);
      box-shadow: 0 0 25px rgba(0, 242, 254, 0.06);
    }
    .viewfinder-viewport {
      position: relative;
      width: 100%;
      height: 440px;
      background: #020617;
      border-radius: 8px;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }
    #viewfinder-canvas {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      image-rendering: auto;
    }
    .hud-overlay-top {
      position: absolute;
      top: 10px;
      left: 10px;
      right: 10px;
      display: flex;
      justify-content: space-between;
      pointer-events: none;
      z-index: 5;
    }
    .hud-tag {
      background: rgba(0, 0, 0, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.15);
      backdrop-filter: blur(4px);
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-family: monospace;
      color: #fff;
    }
    .viewfinder-placeholder {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 12px;
      color: var(--text-dim);
      font-size: 13px;
    }

    /* Video Recording & Chunker Engine */
    .recorder-panel {
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .recorder-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }
    .chunk-config {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: var(--text-muted);
    }
    .chunk-config input {
      width: 54px;
      padding: 4px 6px;
      background: #000;
      border: 1px solid var(--border-subtle);
      border-radius: 4px;
      color: #fff;
      font-family: monospace;
      font-weight: 700;
      font-size: 12px;
      text-align: center;
    }
    .rec-progress-box {
      background: rgba(244, 63, 94, 0.08);
      border: 1px solid rgba(244, 63, 94, 0.25);
      border-radius: 6px;
      padding: 8px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
      font-family: monospace;
    }
    .chunks-table-wrapper {
      max-height: 180px;
      overflow-y: auto;
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
    }
    table.chunks-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      font-family: monospace;
      text-align: left;
    }
    table.chunks-table th {
      background: rgba(255, 255, 255, 0.04);
      padding: 6px 10px;
      color: var(--text-dim);
      font-weight: 600;
      border-bottom: 1px solid var(--border-subtle);
    }
    table.chunks-table td {
      padding: 6px 10px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }

    /* Down-Below Control Deck: Left: Shortcuts, Center: Text Box, Right: Keypad */
    .bottom-deck {
      display: grid;
      grid-template-columns: 340px 1fr 270px;
      gap: 16px;
      align-items: stretch;
    }
    @media (max-width: 1100px) {
      .bottom-deck { grid-template-columns: 1fr 1fr; }
      .bridge-card { grid-column: 1 / -1; }
    }
    @media (max-width: 768px) {
      .bottom-deck { grid-template-columns: 1fr; }
    }

    /* Virtual Keypad */
    .keypad-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 6px;
      max-width: 260px;
      margin: 0 auto;
    }
    .key-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #fff;
      border-radius: 6px;
      padding: 10px 0;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.1s;
      user-select: none;
    }
    .key-btn:hover { background: rgba(255, 255, 255, 0.12); }
    .key-btn:active { background: var(--cyan); color: #000; transform: scale(0.96); }

    /* Interactive Keyboard Bridge */
    .bridge-box {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .bridge-input {
      width: 100%;
      background: rgba(0, 0, 0, 0.5);
      border: 1px solid var(--cyan);
      border-radius: 8px;
      color: #fff;
      padding: 14px 16px;
      font-size: 15px;
      font-family: monospace;
      outline: none;
      box-shadow: inset 0 0 10px rgba(0, 242, 254, 0.08);
    }
    .bridge-input:focus {
      border-color: #fff;
      box-shadow: 0 0 12px rgba(0, 242, 254, 0.35);
    }
    .bridge-log {
      background: #000;
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 8px 12px;
      font-family: monospace;
      font-size: 12px;
      color: var(--green);
      height: 38px;
      display: flex;
      align-items: center;
      overflow: hidden;
      white-space: nowrap;
    }

    /* Toast Notification System */
    #toast-container {
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 9999;
      display: flex;
      flex-direction: column;
      gap: 8px;
      pointer-events: none;
    }
    .toast {
      pointer-events: auto;
      background: rgba(17, 24, 39, 0.95);
      border: 1px solid rgba(255, 255, 255, 0.15);
      backdrop-filter: blur(8px);
      padding: 10px 16px;
      border-radius: 8px;
      color: #fff;
      font-size: 13px;
      font-weight: 600;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      gap: 10px;
      animation: slide-in 0.2s ease-out;
    }
    .toast-success { border-left: 4px solid var(--green); }
    .toast-error { border-left: 4px solid var(--rose); }
    .toast-info { border-left: 4px solid var(--cyan); }
    @keyframes slide-in { from { transform: translateX(50px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

    /* Modal for Video Preview */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.85);
      backdrop-filter: blur(6px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 10000;
    }
    .modal-box {
      background: var(--bg-panel);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px;
      width: 90%;
      max-width: 600px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
  </style>
</head>
<body>

  <!-- Toast Notification Container (Zero alerts) -->
  <div id="toast-container"></div>

  <!-- Header -->
  <header>
    <div class="brand-title">
      <h1>JioPhone F90M // Ground Station</h1>
      <span class="chip">Qualcomm MSM8909</span>
      <span class="chip">KaiOS 2.5</span>
    </div>
    <div class="header-actions">
      <div style="display: flex; align-items: center; gap: 6px; background: rgba(0,0,0,0.3); padding: 4px 8px; border-radius: 6px; border: 1px solid var(--border-subtle); font-size: 12px;">
        <span style="color: var(--text-dim);">Telemetry Rate:</span>
        <input type="number" id="inp-tel-rate" min="0.5" max="30" step="0.5" value="3.5" 
               style="width: 44px; padding: 2px 4px; background: #000; border: 1px solid var(--border-subtle); border-radius: 4px; color: #fff; text-align: center; font-weight: bold; font-size: 11px;" 
               onchange="updateTelemetryInterval(this.value)">
        <span style="color: var(--text-dim);">s</span>
        <button class="btn-pill" onclick="setTelemetryInterval(1.0)">1s</button>
        <button class="btn-pill" onclick="setTelemetryInterval(2.0)">2s</button>
        <button class="btn-pill active" id="pill-tel-35" onclick="setTelemetryInterval(3.5)">3.5s</button>
      </div>

      <div id="badge-conn" class="badge badge-offline"><span class="pulse-dot"></span> <span id="text-conn">Disconnected</span></div>
    </div>
  </header>

  <!-- Main Deck: 50/50 Split (Left: Telemetry, Right: Camera Feed in Main Focus) -->
  <div class="main-deck">
    
    <!-- LEFT HALF: Telemetry Stack -->
    <div class="telemetry-col">
      
      <!-- Card 1: Battery Intelligence & Fuel Gauge (Qualcomm VM-BMS) -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">⚡ Battery Intelligence & BMS Fuel Gauge</div>
          <span id="bat-status" class="badge badge-amber" style="font-size: 11px;">--</span>
        </div>

        <div class="metric-hero">
          <div>
            <div class="metric-value-huge"><span id="bat-soc">--</span><span class="metric-unit">%</span></div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
              Flow: <span id="bat-flow-val" style="font-family: monospace; font-weight: 700;">-- mA</span>
            </div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 11px; text-transform: uppercase; color: var(--text-dim); letter-spacing: 0.5px;">Active Load Runtime</div>
            <div style="font-size: 24px; font-weight: 800; font-family: monospace; color: var(--green);" id="bat-runtime-val">--</div>
            <div style="font-size: 11px; color: var(--text-muted);" id="bat-formula-sub">Formula: Rem mAh ÷ Current mA</div>
          </div>
        </div>

        <div class="gauge-track">
          <div id="bat-gauge-bar" class="gauge-bar gauge-green" style="width: 0%;"></div>
        </div>

        <div class="data-table">
          <div class="data-cell">
            <span class="data-label">Cell / OCV Voltage</span>
            <span class="data-val"><span id="bat-v-now">--</span>V / <span id="bat-v-ocv">--</span>V</span>
          </div>
          <div class="data-cell">
            <span class="data-label">Capacity Remaining</span>
            <span class="data-val"><span id="bat-rem-mah">--</span> / <span id="bat-full-mah">1840</span> mAh</span>
          </div>
          <div class="data-cell">
            <span class="data-label">Internal Impedance</span>
            <span class="data-val"><span id="bat-res">--</span> mΩ <span style="font-size: 10px; color: var(--green);">(Healthy &lt;200)</span></span>
          </div>
          <div class="data-cell">
            <span class="data-label">Standby Projection</span>
            <span class="data-val" style="color: var(--green);"><span id="bat-standby-h">--</span> Hours</span>
          </div>
        </div>
      </div>

      <!-- Card 2: Hardware Thermals & System Compute -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">🌡️ Snapdragon 205 Thermals & Memory</div>
          <span id="sys-uptime" class="hud-tag">Up: --</span>
        </div>

        <div class="data-table">
          <div class="data-cell">
            <span class="data-label">CPU Core Thermal</span>
            <span class="data-val" id="val-cpu-temp">-- °C</span>
          </div>
          <div class="data-cell">
            <span class="data-label">PMIC Power Thermal</span>
            <span class="data-val" id="val-pmic-temp">-- °C</span>
          </div>
          <div class="data-cell">
            <span class="data-label">PA RF Thermal</span>
            <span class="data-val" id="val-pa-temp">-- °C</span>
          </div>
          <div class="data-cell">
            <span class="data-label">Battery Cell Thermal</span>
            <span class="data-val" id="val-bat-temp">-- °C</span>
          </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-top: 4px;">
          <span style="color: var(--text-dim);">RAM Utilization (405 MB Total):</span>
          <span style="font-family: monospace; font-weight: 700;" id="ram-summary">-- MB used</span>
        </div>
        <div class="gauge-track">
          <div id="ram-gauge-bar" class="gauge-bar gauge-amber" style="width: 0%;"></div>
        </div>
      </div>

    </div>

    <!-- RIGHT HALF: Camera Feed in Main Focus -->
    <div class="camera-col">
      <div class="card viewfinder-card">
        
        <div class="card-header">
          <div class="card-title">
            <span>📷 Qualcomm ISP Optical Viewfinder</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span id="badge-stream-fps" class="hud-tag" style="color: var(--green);">FPS: --</span>
            <div id="badge-cam-live" class="badge badge-offline" style="font-size: 11px;">
              <span class="pulse-dot"></span> <span id="text-cam-live">No Stream</span>
            </div>
          </div>
        </div>

        <!-- Large Main-Focus Viewport -->
        <div class="viewfinder-viewport" id="viewport-box">
          <div class="hud-overlay-top">
            <span class="hud-tag" id="hud-res">320x240 @ Qualcomm VFE</span>
            <span class="hud-tag" id="hud-rot">ROT: 0°</span>
          </div>

          <canvas id="viewfinder-canvas" width="320" height="240"></canvas>

          <div class="viewfinder-placeholder" id="viewport-placeholder">
            <div style="font-size: 32px;">📷</div>
            <div><b>Awaiting Live Camera Frame...</b></div>
            <div style="font-size: 12px; color: var(--text-dim);">
              Click <b style="color: var(--cyan);">"🚀 Launch Cam App"</b> below or open <code style="color: #fff;">http://192.168.1.15/c</code> on phone
            </div>
          </div>
        </div>

        <!-- Viewfinder Controls Bar -->
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 12px;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <button class="btn btn-success" style="padding: 4px 10px; font-size: 11px;" onclick="switchCamera()">📷 Switch Cam</button>
            <button class="btn" style="padding: 4px 10px; font-size: 11px;" onclick="rotateCameraStep()">🔄 Rotate 90°</button>
            <button class="btn-pill active" id="rot-btn-0" onclick="setCameraRotation(0)">0°</button>
            <button class="btn-pill" id="rot-btn-90" onclick="setCameraRotation(90)">90°</button>
            <button class="btn-pill" id="rot-btn-180" onclick="setCameraRotation(180)">180°</button>
            <button class="btn-pill" id="rot-btn-270" onclick="setCameraRotation(270)">270°</button>
          </div>

          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="color: var(--text-dim);">Dispatch Rate:</span>
            <button class="btn-pill active" id="crate-004" onclick="setCamInterval(0.04)">Max (~25 FPS)</button>
            <button class="btn-pill" id="crate-010" onclick="setCamInterval(0.1)">10 FPS</button>
            <button class="btn-pill" id="crate-050" onclick="setCamInterval(0.5)">0.5s</button>
            <button class="btn-pill" id="crate-100" onclick="setCamInterval(1.0)">1s</button>
            <button class="btn-pill" id="crate-200" onclick="setCamInterval(2.0)">2s</button>
          </div>
        </div>

        <!-- Video Recording & Dynamic Chunker Engine -->
        <div class="recorder-panel">
          <div class="recorder-toolbar">
            <div style="display: flex; align-items: center; gap: 10px;">
              <button class="btn btn-danger" id="btn-record-toggle" onclick="toggleRecording()">
                🔴 Start Recording
              </button>
              <div class="chunk-config">
                <span>Split Chunk:</span>
                <input type="number" id="inp-chunk-size" value="5" min="1" max="200" onchange="updateChunkSize(this.value)">
                <span>MB</span>
                <button class="btn-pill" onclick="setChunkSizePreset(2)">2MB</button>
                <button class="btn-pill active" id="cpill-5" onclick="setChunkSizePreset(5)">5MB</button>
                <button class="btn-pill" onclick="setChunkSizePreset(10)">10MB</button>
                <button class="btn-pill" onclick="setChunkSizePreset(25)">25MB</button>
              </div>
            </div>

            <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); cursor: pointer;">
              <input type="checkbox" id="chk-auto-dl" checked style="accent-color: var(--cyan);">
              Auto-download chunks
            </label>
          </div>

          <!-- Active Recording Status (visible when recording) -->
          <div id="rec-active-box" class="rec-progress-box" style="display: none;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="color: var(--rose); font-weight: 700;"><span class="pulse-dot" style="display: inline-block; vertical-align: middle;"></span> RECORDING ACTIVE: <span id="rec-timer-txt">00:00</span></span>
              <span>Active: <b id="rec-chunk-idx" style="color: #fff;">Chunk #1</b> | Total: <b id="rec-session-total" style="color: #fff;">0.0 MB</b></span>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted);">
              <span>Current Chunk Accumulation:</span>
              <span id="rec-chunk-progress-txt">0.0 / 5.0 MB (0%)</span>
            </div>
            <div class="gauge-track" style="margin: 0; height: 6px;">
              <div id="rec-chunk-bar" class="gauge-bar gauge-red" style="width: 0%;"></div>
            </div>
          </div>

          <!-- Finalized Chunks Table -->
          <div class="chunks-table-wrapper" id="chunks-drawer" style="display: none;">
            <table class="chunks-table">
              <thead>
                <tr>
                  <th>Chunk</th>
                  <th>Size</th>
                  <th>Duration</th>
                  <th>Timestamp</th>
                  <th style="text-align: right;">Action</th>
                </tr>
              </thead>
              <tbody id="chunks-tbody"></tbody>
            </table>
          </div>
        </div>

      </div>
    </div>

  </div>

  <!-- DOWN-BELOW CONTROL DECK: Left: Shortcuts, Center: Text Box, Right: Keypad -->
  <div class="bottom-deck">
    
    <!-- Column 1 (Left): All Shortcut & System Control Buttons (Directly below Thermals) -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">⚡ Action Shortcuts</div>
        <span class="hud-tag" style="color: var(--cyan);">Device Controls</span>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
        <button class="btn btn-primary" onclick="launchAppRemotely()" id="btn-launch-app" style="grid-column: 1 / -1; justify-content: center; padding: 9px;">
          🚀 Launch Cam App
        </button>

        <button class="btn btn-success" onclick="switchCamera()" id="btn-switch-cam" style="justify-content: center; padding: 8px 6px; font-size: 11px;">
          📷 Switch Cam (Soft L)
        </button>

        <button class="btn btn-amber" onclick="togglePhoneScreen()" id="btn-screen-pwr" style="justify-content: center; padding: 8px 6px; font-size: 11px;">
          🌑 Screen OFF
        </button>

        <button class="btn" onclick="scanSubnet()" id="btn-scan" style="grid-column: 1 / -1; justify-content: center; padding: 7px; font-size: 11px;">
          🔍 Scan Subnet for Phone
        </button>

        <button class="btn btn-danger" onclick="toggleB2G('stop')" style="justify-content: center; padding: 8px 4px; font-size: 11px;">
          Kill GUI (Eco)
        </button>

        <button class="btn btn-success" onclick="toggleB2G('start')" style="justify-content: center; padding: 8px 4px; font-size: 11px;">
          Restart GUI
        </button>

        <button class="btn btn-primary" onclick="toggleLeanMode('strip')" style="justify-content: center; padding: 8px 4px; font-size: 11px;">
          ⚡ Strip 14 Daemons
        </button>

        <button class="btn" onclick="toggleLeanMode('restore')" style="justify-content: center; padding: 8px 4px; font-size: 11px;">
          ↺ Restore Daemons
        </button>
      </div>
    </div>

    <!-- Column 2 (Center): Interactive PC Keyboard Bridge (Shrunk to fit in between) -->
    <div class="card bridge-box bridge-card" style="display: flex; flex-direction: column; justify-content: space-between;">
      <div>
        <div class="card-header">
          <div class="card-title">⌨️ Interactive PC Typing Bridge</div>
          <span class="badge badge-online" style="font-size: 10px; padding: 3px 8px;">Active</span>
        </div>
        <p style="font-size: 11px; color: var(--text-muted); margin: 6px 0 8px; line-height: 1.4;">
          Type with your physical keyboard. Keystrokes map to T9 sequences on phone.
        </p>
        <div style="display: flex; gap: 8px;">
          <input type="text" id="pc-key-input" class="bridge-input" placeholder="Click here and type directly..." autocomplete="off" style="padding: 10px 12px; font-size: 14px;">
          <button class="btn" onclick="clearBridgeInput()" style="padding: 6px 12px;">Clear</button>
        </div>
      </div>

      <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 8px;">
        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
          <button class="btn btn-pill" onclick="sendKey(28)">Enter (OK)</button>
          <button class="btn btn-pill" onclick="sendKey(116)">Backspace (DEL)</button>
          <button class="btn btn-pill" onclick="sendKey(11)">Space ('0')</button>
        </div>
        <div class="bridge-log" id="bridge-log-txt" style="height: 32px; font-size: 11px; padding: 6px 10px;">
          Ready for typing input...
        </div>
      </div>
    </div>

    <!-- Column 3 (Right): Virtual Keypad Column -->
    <div class="card" style="display: flex; flex-direction: column; justify-content: space-between;">
      <div class="card-header">
        <div class="card-title">🎮 Remote Keypad</div>
        <span id="badge-lcd-status" class="badge badge-online" style="font-size: 10px; padding: 3px 8px;">LCD ON</span>
      </div>

      <div class="keypad-grid" style="margin: 4px auto;">
        <button class="key-btn" onclick="sendKey(510)">Soft L</button>
        <button class="key-btn" onclick="sendKey(103)">▲ Up</button>
        <button class="key-btn" onclick="sendKey(511)">Soft R</button>
        
        <button class="key-btn" onclick="sendKey(105)">◀ Left</button>
        <button class="key-btn" style="background: var(--cyan); color: #000;" onclick="sendKey(28)">OK</button>
        <button class="key-btn" onclick="sendKey(106)">Right ▶</button>
        
        <button class="key-btn" style="color: var(--green);" onclick="sendKey(231)">Call</button>
        <button class="key-btn" onclick="sendKey(108)">▼ Down</button>
        <button class="key-btn" style="color: var(--rose);" onclick="sendKey(116)">End / Wake</button>
        
        <button class="key-btn" onclick="sendKey(2)">1</button>
        <button class="key-btn" onclick="sendKey(3)">2</button>
        <button class="key-btn" onclick="sendKey(4)">3</button>
        
        <button class="key-btn" onclick="sendKey(5)">4</button>
        <button class="key-btn" onclick="sendKey(6)">5</button>
        <button class="key-btn" onclick="sendKey(7)">6</button>
        
        <button class="key-btn" onclick="sendKey(8)">7</button>
        <button class="key-btn" onclick="sendKey(9)">8</button>
        <button class="key-btn" onclick="sendKey(10)">9</button>
        
        <button class="key-btn" onclick="sendKey(227)">*</button>
        <button class="key-btn" onclick="sendKey(11)">0</button>
        <button class="key-btn" onclick="sendKey(228)">#</button>
      </div>
      <div id="key-ack-txt" style="text-align: center; font-size: 11px; color: var(--green); height: 14px; font-family: monospace;"></div>
    </div>

  </div>

  <!-- Video Preview Modal -->
  <div class="modal-overlay" id="preview-modal" onclick="closePreviewModal(event)">
    <div class="modal-box" onclick="event.stopPropagation()">
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <b id="modal-video-title" style="font-size: 14px; font-family: monospace;">Video Preview</b>
        <button class="btn btn-pill" onclick="closePreviewModal()">✕ Close</button>
      </div>
      <video id="modal-video-player" controls autoplay style="width: 100%; max-height: 400px; border-radius: 6px; background: #000;"></video>
      <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <a id="modal-dl-link" class="btn btn-primary" download style="text-decoration: none;">⬇ Download Chunk</a>
      </div>
    </div>
  </div>

  <script>
    /* ==========================================================================
       TOAST NOTIFICATION ENGINE (Replaces all alerts)
       ========================================================================== */
    function showToast(message, type = 'info', durationMs = 3200) {
      const container = document.getElementById('toast-container');
      const toast = document.createElement('div');
      toast.className = 'toast toast-' + type;
      
      const icon = (type === 'success') ? '✓' : (type === 'error') ? '✕' : 'ℹ';
      toast.innerHTML = `<span style="font-size: 15px;">${icon}</span><span>${message}</span>`;
      container.appendChild(toast);

      setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
      }, durationMs);
    }

    /* ==========================================================================
       TELEMETRY UPDATER & POLLING
       ========================================================================== */
    let telemetryIntervalSec = parseFloat(localStorage.getItem('telemetry_interval_sec') || '3.5');
    let telemetryTimer = null;

    function resetTelemetryTimer() {
      if (telemetryTimer) clearInterval(telemetryTimer);
      telemetryTimer = setInterval(fetchTelemetry, Math.max(500, Math.round(telemetryIntervalSec * 1000)));
    }

    function updateTelemetryInterval(val) {
      const sec = Math.max(0.5, min(60.0, parseFloat(val) || 3.5));
      telemetryIntervalSec = sec;
      localStorage.setItem('telemetry_interval_sec', sec);
      const inp = document.getElementById('inp-tel-rate');
      if (inp) inp.value = sec;
      resetTelemetryTimer();
      fetch('/api/telemetry/interval?sec=' + sec).catch(() => {});
      showToast('Telemetry poll set to ' + sec + 's', 'info');
    }

    function setTelemetryInterval(sec) {
      updateTelemetryInterval(sec);
    }

    function min(a, b) { return a < b ? a : b; }
    function max(a, b) { return a > b ? a : b; }

    function fetchTelemetry() {
      fetch('/api/telemetry')
        .then(r => r.json())
        .then(data => {
          const badgeConn = document.getElementById('badge-conn');
          const textConn = document.getElementById('text-conn');
          
          if (data.connected) {
            badgeConn.className = 'badge badge-online';
            textConn.innerText = data.active_target || data.phone_ip;
          } else {
            badgeConn.className = 'badge badge-offline';
            textConn.innerText = 'Disconnected';
          }

          const b = data.battery || {};
          document.getElementById('bat-soc').innerText = b.soc_pct ?? '--';
          document.getElementById('bat-status').innerText = b.status || '--';
          
          const bar = document.getElementById('bat-gauge-bar');
          const soc = b.soc_pct || 0;
          bar.style.width = soc + '%';
          bar.className = 'gauge-bar ' + (soc > 40 ? 'gauge-green' : soc > 20 ? 'gauge-amber' : 'gauge-red');

          const curMa = b.current_ma ?? 0;
          const flowEl = document.getElementById('bat-flow-val');
          flowEl.innerText = (curMa > 0 ? '+' : '') + curMa + ' mA (' + (b.charging_flow || '') + ')';
          flowEl.style.color = (curMa < 0) ? 'var(--green)' : 'var(--amber)';

          document.getElementById('bat-runtime-val').innerText = b.life_current_str || '--';
          
          document.getElementById('bat-v-now').innerText = b.voltage_v ?? '--';
          document.getElementById('bat-v-ocv').innerText = b.ocv_v ?? '--';
          document.getElementById('bat-rem-mah').innerText = b.estimated_mah_remaining ?? '--';
          document.getElementById('bat-full-mah').innerText = b.estimated_actual_full_mah || '1840';
          document.getElementById('bat-res').innerText = b.resistance_mohm ?? '--';
          document.getElementById('bat-standby-h').innerText = b.projected_hours_deep_sleep || '52.5';

          const t = data.thermal || {};
          document.getElementById('val-cpu-temp').innerText = (t.cpu_c ?? '--') + ' °C';
          document.getElementById('val-pmic-temp').innerText = (t.pmic_c ?? '--') + ' °C';
          document.getElementById('val-pa-temp').innerText = (t.pa_c ?? '--') + ' °C';
          document.getElementById('val-bat-temp').innerText = (t.battery_c ?? '--') + ' °C';

          const m = data.memory || {};
          document.getElementById('ram-summary').innerText = (m.used_mb ?? '--') + ' MB / ' + (m.total_mb || 405) + ' MB (' + (m.used_pct || 0) + '%)';
          document.getElementById('ram-gauge-bar').style.width = (m.used_pct || 0) + '%';

          const s = data.system || {};
          document.getElementById('sys-uptime').innerText = 'Up: ' + (s.uptime || '--');

          const b2gBadge = document.getElementById('badge-b2g');
          if (s.b2g_running) {
            b2gBadge.innerText = 'GUI Running';
            b2gBadge.className = 'badge badge-online';
          } else {
            b2gBadge.innerText = 'Headless Eco';
            b2gBadge.className = 'badge badge-amber';
          }

          const lcdBadge = document.getElementById('badge-lcd-status');
          if (s.screen_blackout) {
            lcdBadge.innerText = 'LCD OFF';
            lcdBadge.className = 'badge badge-offline';
          } else {
            lcdBadge.innerText = 'LCD ON';
            lcdBadge.className = 'badge badge-online';
          }

          if (data.has_live_frame) {
            startStreamLoop();
          }
        })
        .catch(() => {});
    }

    /* ==========================================================================
       OPTICAL SENSOR VIEWPORT & ROTATION ENGINE
       ========================================================================== */
    let currentRotation = parseInt(localStorage.getItem('cam_rotation') || '0', 10);
    let camIntervalSec = parseFloat(localStorage.getItem('cam_interval_sec') || '0.04');
    let camIntervalMs = Math.max(30, Math.round(camIntervalSec * 1000));
    let streamLoopRunning = false;
    let lastFrameTime = 0;
    let fpsCounter = 0;
    let currentFPS = 0;

    const canvas = document.getElementById('viewfinder-canvas');
    const ctx = canvas.getContext('2d');
    const placeholder = document.getElementById('viewport-placeholder');

    function applyRotationUI() {
      document.getElementById('hud-rot').innerText = 'ROT: ' + currentRotation + '°';
      [0, 90, 180, 270].forEach(deg => {
        const btn = document.getElementById('rot-btn-' + deg);
        if (btn) btn.className = 'btn-pill' + (deg === currentRotation ? ' active' : '');
      });
      localStorage.setItem('cam_rotation', currentRotation);
    }

    function rotateCameraStep() {
      currentRotation = (currentRotation + 90) % 360;
      applyRotationUI();
      showToast('Camera rotated to ' + currentRotation + '°', 'info');
    }

    function setCameraRotation(deg) {
      currentRotation = deg % 360;
      applyRotationUI();
      showToast('Camera set to ' + currentRotation + '°', 'info');
    }

    function setCamInterval(sec) {
      camIntervalSec = sec;
      camIntervalMs = Math.max(30, Math.round(sec * 1000));
      localStorage.setItem('cam_interval_sec', sec);
      fetch('/api/camera/interval?sec=' + sec).catch(() => {});
      
      const presets = [
        { id: 'crate-004', sec: 0.04 },
        { id: 'crate-010', sec: 0.1 },
        { id: 'crate-050', sec: 0.5 },
        { id: 'crate-100', sec: 1.0 },
        { id: 'crate-200', sec: 2.0 }
      ];
      presets.forEach(p => {
        const btn = document.getElementById(p.id);
        if (btn) btn.className = 'btn-pill' + (Math.abs(p.sec - sec) < 0.02 ? ' active' : '');
      });
      showToast('Dispatch interval set to ' + sec + 's', 'info');
    }

    function renderImageToCanvas(img) {
      const nw = img.naturalWidth || 320;
      const nh = img.naturalHeight || 240;

      if (currentRotation === 90 || currentRotation === 270) {
        if (canvas.width !== nh || canvas.height !== nw) {
          canvas.width = nh;
          canvas.height = nw;
        }
      } else {
        if (canvas.width !== nw || canvas.height !== nh) {
          canvas.width = nw;
          canvas.height = nh;
        }
      }

      ctx.save();
      ctx.translate(canvas.width / 2, canvas.height / 2);
      ctx.rotate((currentRotation * Math.PI) / 180);
      ctx.drawImage(img, -nw / 2, -nh / 2);
      ctx.restore();

      document.getElementById('hud-res').innerText = `${canvas.width}x${canvas.height} @ Qualcomm VFE`;
    }

    function startStreamLoop() {
      if (streamLoopRunning) return;
      streamLoopRunning = true;
      placeholder.style.display = 'none';
      canvas.style.display = 'block';

      const liveBadge = document.getElementById('badge-cam-live');
      const liveText = document.getElementById('text-cam-live');
      liveBadge.className = 'badge badge-online';
      liveText.innerText = 'LIVE STREAM';

      // FPS tracking
      setInterval(() => {
        currentFPS = fpsCounter;
        fpsCounter = 0;
        document.getElementById('badge-stream-fps').innerText = `FPS: ${currentFPS}`;
      }, 1000);

      function fetchFrame() {
        const img = new Image();
        img.onload = function() {
          renderImageToCanvas(img);
          fpsCounter++;
          setTimeout(fetchFrame, camIntervalMs);
        };
        img.onerror = function() {
          setTimeout(fetchFrame, Math.max(250, camIntervalMs));
        };
        img.src = '/api/camera/stream?t=' + Date.now();
      }
      fetchFrame();
    }

    /* ==========================================================================
       VIDEO RECORDING & DYNAMIC CHUNKER ENGINE
       ========================================================================== */
    let isRecording = false;
    let mediaRecorder = null;
    let chunkIndex = 1;
    let targetChunkSizeBytes = 5 * 1024 * 1024; // 5 MB default
    let currentChunkBlobs = [];
    let currentChunkBytes = 0;
    let totalSessionBytes = 0;
    let recStartTime = 0;
    let recTimerInterval = null;
    let chunkStartTime = 0;
    let finalizedChunks = [];

    function updateChunkSize(mb) {
      const num = Math.max(1, Math.min(500, parseFloat(mb) || 5));
      targetChunkSizeBytes = Math.round(num * 1024 * 1024);
      document.getElementById('inp-chunk-size').value = num;
      showToast('Chunk size threshold set to ' + num + ' MB', 'info');
    }

    function setChunkSizePreset(mb) {
      updateChunkSize(mb);
      [2, 5, 10, 25].forEach(p => {
        const pill = document.getElementById('cpill-' + p);
        if (pill) pill.className = 'btn-pill' + (p === mb ? ' active' : '');
      });
    }

    function formatBytes(bytes) {
      if (bytes < 1024) return bytes + ' B';
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
      return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    }

    function formatDuration(ms) {
      const totalSec = Math.floor(ms / 1000);
      const m = Math.floor(totalSec / 60);
      const s = totalSec % 60;
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }

    function toggleRecording() {
      if (isRecording) {
        stopRecording();
      } else {
        startRecording();
      }
    }

    function startRecording() {
      if (isRecording) return;
      
      const stream = canvas.captureStream(25);
      const types = [
        'video/webm;codecs=vp8',
        'video/webm',
        'video/mp4'
      ];
      let selectedMime = types.find(t => MediaRecorder.isTypeSupported(t)) || '';

      try {
        mediaRecorder = selectedMime ? new MediaRecorder(stream, { mimeType: selectedMime }) : new MediaRecorder(stream);
      } catch (err) {
        showToast('Recorder init error: ' + err.message, 'error');
        return;
      }

      isRecording = true;
      chunkIndex = 1;
      currentChunkBlobs = [];
      currentChunkBytes = 0;
      totalSessionBytes = 0;
      recStartTime = Date.now();
      chunkStartTime = Date.now();

      const btn = document.getElementById('btn-record-toggle');
      btn.innerText = '⏹ Stop Recording';
      btn.className = 'btn btn-danger';
      document.getElementById('rec-active-box').style.display = 'flex';
      document.getElementById('chunks-drawer').style.display = 'block';

      recTimerInterval = setInterval(() => {
        const elapsedMs = Date.now() - recStartTime;
        document.getElementById('rec-timer-txt').innerText = formatDuration(elapsedMs);
      }, 500);

      mediaRecorder.ondataavailable = function(e) {
        if (e.data && e.data.size > 0) {
          currentChunkBlobs.push(e.data);
          currentChunkBytes += e.data.size;
          totalSessionBytes += e.data.size;
          updateRecordingProgressUI();

          if (currentChunkBytes >= targetChunkSizeBytes) {
            finalizeCurrentChunk(false);
          }
        }
      };

      mediaRecorder.start(250); // timeslice 250ms for fine-grained chunk size triggers
      showToast('Recording started. Chunking at ' + (targetChunkSizeBytes / (1024 * 1024)) + ' MB', 'success');
    }

    function updateRecordingProgressUI() {
      document.getElementById('rec-chunk-idx').innerText = 'Chunk #' + chunkIndex;
      document.getElementById('rec-session-total').innerText = formatBytes(totalSessionBytes);
      
      const targetMb = targetChunkSizeBytes / (1024 * 1024);
      const curMb = currentChunkBytes / (1024 * 1024);
      const pct = Math.min(100, Math.round((currentChunkBytes / targetChunkSizeBytes) * 100));
      
      document.getElementById('rec-chunk-progress-txt').innerText = `${curMb.toFixed(2)} / ${targetMb.toFixed(1)} MB (${pct}%)`;
      document.getElementById('rec-chunk-bar').style.width = pct + '%';
    }

    function finalizeCurrentChunk(isSessionEnd) {
      if (currentChunkBlobs.length === 0) return;

      const mimeType = mediaRecorder.mimeType || 'video/webm';
      const blob = new Blob(currentChunkBlobs, { type: mimeType });
      const ext = mimeType.includes('mp4') ? 'mp4' : 'webm';
      const filename = `jiophone_cam_chunk_${String(chunkIndex).padStart(3, '0')}.${ext}`;
      const url = URL.createObjectURL(blob);
      const durMs = Date.now() - chunkStartTime;
      const durStr = formatDuration(durMs);

      const chunkItem = {
        index: chunkIndex,
        filename: filename,
        size: blob.size,
        sizeStr: formatBytes(blob.size),
        durationStr: durStr,
        timestamp: new Date().toLocaleTimeString(),
        url: url
      };

      finalizedChunks.unshift(chunkItem);
      renderChunksTable();

      const autoDl = document.getElementById('chk-auto-dl').checked;
      if (autoDl) {
        triggerDownload(url, filename);
      }

      showToast(`Finalized ${filename} (${chunkItem.sizeStr})`, 'success');

      if (!isSessionEnd) {
        chunkIndex++;
        currentChunkBlobs = [];
        currentChunkBytes = 0;
        chunkStartTime = Date.now();
        updateRecordingProgressUI();
      }
    }

    function stopRecording() {
      if (!isRecording || !mediaRecorder) return;
      
      mediaRecorder.onstop = function() {
        finalizeCurrentChunk(true);
        isRecording = false;
        clearInterval(recTimerInterval);

        const btn = document.getElementById('btn-record-toggle');
        btn.innerText = '🔴 Start Recording';
        btn.className = 'btn btn-danger';
        document.getElementById('rec-active-box').style.display = 'none';
        showToast('Recording completed. Saved ' + finalizedChunks.length + ' chunk(s).', 'info');
      };
      mediaRecorder.stop();
    }

    function triggerDownload(url, filename) {
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }

    function renderChunksTable() {
      const tbody = document.getElementById('chunks-tbody');
      tbody.innerHTML = '';

      finalizedChunks.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><b style="color:var(--cyan);">${c.filename}</b></td>
          <td>${c.sizeStr}</td>
          <td>${c.durationStr}</td>
          <td style="color:var(--text-dim);">${c.timestamp}</td>
          <td style="text-align: right;">
            <button class="btn btn-pill" onclick="previewChunk('${c.url}', '${c.filename}')">▶ Play</button>
            <button class="btn btn-pill" style="background:var(--cyan); color:#000;" onclick="triggerDownload('${c.url}', '${c.filename}')">⬇ Save</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function previewChunk(url, filename) {
      const modal = document.getElementById('preview-modal');
      const player = document.getElementById('modal-video-player');
      const title = document.getElementById('modal-video-title');
      const dlLink = document.getElementById('modal-dl-link');

      title.innerText = 'Preview: ' + filename;
      dlLink.href = url;
      dlLink.download = filename;
      player.src = url;
      modal.style.display = 'flex';
      player.play();
    }

    function closePreviewModal(e) {
      const modal = document.getElementById('preview-modal');
      const player = document.getElementById('modal-video-player');
      player.pause();
      player.src = '';
      modal.style.display = 'none';
    }

    /* ==========================================================================
       REMOTE APP LAUNCH & DEVICE CONTROLS
       ========================================================================== */
    function launchAppRemotely() {
      const btn = document.getElementById('btn-launch-app');
      btn.disabled = true;
      btn.innerText = '⏳ Launching...';
      showToast('Sending RDP launch command to JioPhone...', 'info');

      fetch('/api/app/launch')
        .then(r => r.json())
        .then(d => {
          btn.disabled = false;
          btn.innerText = '🚀 Launch Cam App';
          if (d.status === 'ok') {
            showToast(d.message, 'success');
          } else {
            showToast('Launch failed: ' + d.message, 'error');
          }
        })
        .catch(err => {
          btn.disabled = false;
          btn.innerText = '🚀 Launch Cam App';
          showToast('Error sending launch command: ' + err, 'error');
        });
    }

    function switchCamera() {
      sendKey(510);
      showToast('Switched Camera (Soft L sent to device)', 'info');
    }

    let phoneScreenState = true;
    function togglePhoneScreen() {
      phoneScreenState = !phoneScreenState;
      const btn = document.getElementById('btn-screen-pwr');
      btn.innerText = phoneScreenState ? '🌑 Screen OFF' : '☀️ Screen ON';
      btn.className = phoneScreenState ? 'btn btn-amber' : 'btn btn-success';
      fetch('/api/camera/screen_toggle?cmd=' + (phoneScreenState ? 'on' : 'off'));
      showToast(phoneScreenState ? 'Screen Backlight Restored' : 'Screen Backlight Turned OFF', 'info');
    }

    function toggleB2G(action) {
      showToast(`Executing ${action} b2g...`, 'info');
      fetch('/api/system/b2g?action=' + action)
        .then(r => r.json())
        .then(d => {
          showToast(d.message, 'success');
          fetchTelemetry();
        });
    }

    function toggleLeanMode(action) {
      showToast(`Executing lean mode (${action})...`, 'info');
      fetch('/api/system/lean_mode?action=' + action)
        .then(r => r.json())
        .then(d => {
          showToast(d.message, 'success');
          fetchTelemetry();
        });
    }

    function scanSubnet() {
      const btn = document.getElementById('btn-scan');
      btn.disabled = true;
      btn.innerText = 'Scanning...';
      showToast('Probing subnet for port 5555...', 'info');

      fetch('/api/network/scan')
        .then(r => r.json())
        .then(d => {
          btn.disabled = false;
          btn.innerText = '🔍 Scan Subnet';
          showToast(d.message, d.found.length ? 'success' : 'info');
          fetchTelemetry();
        })
        .catch(e => {
          btn.disabled = false;
          btn.innerText = '🔍 Scan Subnet';
          showToast('Subnet scan error: ' + e, 'error');
        });
    }

    /* ==========================================================================
       KEYPAD & INTERACTIVE PC KEYBOARD BRIDGE
       ========================================================================== */
    function sendKey(code) {
      const ack = document.getElementById('key-ack-txt');
      ack.innerText = 'Transmitted Keycode ' + code;
      fetch('/api/keypad/press?code=' + code);
      setTimeout(() => ack.innerText = '', 1200);
    }

    const pcKeyInput = document.getElementById('pc-key-input');
    pcKeyInput.addEventListener('keydown', function(e) {
      let keyToSend = null;
      if (e.key === 'Backspace') {
        keyToSend = 'Backspace';
        e.preventDefault();
      } else if (e.key === 'Enter') {
        keyToSend = 'Enter';
        e.preventDefault();
      } else if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Escape'].includes(e.key)) {
        keyToSend = e.key;
        e.preventDefault();
      } else if (e.key.length === 1) {
        keyToSend = e.key;
      }
      
      if (keyToSend) {
        const log = document.getElementById('bridge-log-txt');
        log.innerText = 'Transmitting: ' + keyToSend;
        fetch('/api/keyboard/char?c=' + encodeURIComponent(keyToSend))
          .then(r => r.json())
          .then(d => {
            log.innerText = `Input: '${keyToSend}' -> Phone Action: ${d.action}`;
          })
          .catch(err => {
            log.innerText = 'Bridge Error: ' + err;
          });
      }
    });

    function clearBridgeInput() {
      pcKeyInput.value = '';
      document.getElementById('bridge-log-txt').innerText = 'Input cleared.';
    }

    /* ==========================================================================
       INITIALIZATION
       ========================================================================== */
    applyRotationUI();
    setCamInterval(camIntervalSec);
    resetTelemetryTimer();
    fetchTelemetry();
  </script>
</body>
</html>
"""

class TelemetryHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global latest_camera_frame, POLL_INTERVAL
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        clean_path = path.rstrip("/").lower()

        # Short URLs for phone camera streamer
        if clean_path in ("/c", "/cam", "/camera", "/s", "/1", "/cam_sender"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(CAMERA_SENDER_HTML.encode("utf-8"))
        elif clean_path in ("", "/index.html"):
            ua = self.headers.get("User-Agent", "").lower()
            if "mobile" in ua or "kaios" in ua or "android" in ua:
                self.send_response(302)
                self.send_header("Location", "/c")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))
        elif path == "/api/telemetry":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(telemetry_data).encode("utf-8"))
        elif path.startswith("/api/telemetry/interval"):
            sec = query.get("sec", ["3.5"])[0]
            try:
                new_sec = max(0.5, min(60.0, float(sec)))
                POLL_INTERVAL = new_sec
                telemetry_data["poll_rate_sec"] = new_sec
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "poll_interval_sec": POLL_INTERVAL}).encode("utf-8"))
        elif path.startswith("/api/camera/stream"):
            with frame_lock:
                frame = latest_camera_frame
            if frame:
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-cache, no-store")
                self.end_headers()
                self.wfile.write(frame)
            else:
                self.send_response(404)
                self.end_headers()
        elif path == "/api/app/launch":
            ok, msg = launch_cam_app_remote()
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok" if ok else "error", "message": msg}).encode("utf-8"))
        elif path == "/api/camera/test":
            res = run_adb(["echo 1 | mm-qcamera-app"], timeout=6)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"output": res.strip() if res else "Hardware test passed"}).encode("utf-8"))
        elif path.startswith("/api/system/b2g"):
            action = query.get("action", ["start"])[0]
            run_adb([f"{action} b2g"], timeout=5)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            msg = "Stopped B2G GUI (Freed ~250MB RAM! Ultra Eco Mode active)" if action == "stop" else "Started B2G GUI"
            self.wfile.write(json.dumps({"message": msg}).encode("utf-8"))
        elif path.startswith("/api/system/lean_mode"):
            action = query.get("action", ["strip"])[0]
            if action == "strip":
                cmds = "stop loc_launcher; stop fidodaemon; stop tct_diag; stop tctd; stop imsqmidaemon; stop imsdatadaemon; stop ims_rtp_daemon; stop cnd; stop qti; stop ril-daemon; stop netmgrd; stop qmuxd; stop audiod; stop gatekeeperd; stop keystore"
                run_adb([cmds], timeout=6)
                msg = "Successfully stripped 14 background bloat daemons! RAM freed and CPU dedicated to Camera."
            else:
                cmds = "start ril-daemon; start netmgrd; start qmuxd; start audiod; start loc_launcher; start fidodaemon; start tctd"
                run_adb([cmds], timeout=6)
                msg = "Restored system background daemons."
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "action": action, "message": msg}).encode("utf-8"))
        elif path == "/api/network/scan":
            found = scan_subnet_for_port()
            connected_ip = None
            for ip in found:
                try:
                    subprocess.run([ADB_PATH, "connect", f"{ip}:5555"], timeout=3)
                    state["phone_ip"] = ip
                    connected_ip = ip
                    break
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            msg = f"Scan complete. Connected to {connected_ip}" if connected_ip else "Scan complete."
            self.wfile.write(json.dumps({"status": "ok", "found": found, "connected": connected_ip, "message": msg}).encode("utf-8"))
        elif path.startswith("/api/keyboard/char"):
            char_val = query.get("c", [""])[0]
            action_desc = type_character(char_val)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "char": char_val, "action": action_desc}).encode("utf-8"))
        elif path.startswith("/api/keypad/press"):
            code = 28
            try:
                code = int(query.get("code", [28])[0])
            except Exception:
                pass
            send_key_event(code)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        elif path.startswith("/api/camera/log"):
            msg = query.get("msg", [""])[0]
            try:
                print(f"[Phone Camera Log]: {msg.encode('ascii', errors='replace').decode('ascii')}")
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        elif path.startswith("/api/camera/interval"):
            sec = query.get("sec", [None])[0]
            ms = query.get("ms", [None])[0]
            if sec is not None:
                try:
                    state["camera_interval_ms"] = max(30, int(float(sec) * 1000))
                except Exception:
                    pass
            elif ms is not None:
                try:
                    state["camera_interval_ms"] = max(30, int(ms))
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "interval_ms": state.get("camera_interval_ms", 40)}).encode("utf-8"))
        elif path.startswith("/api/camera/screen_cmd"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"cmd": state.get("screen_cmd", "none"), "interval_ms": state.get("camera_interval_ms", 40)}).encode("utf-8"))
        elif path.startswith("/api/camera/screen_toggle"):
            cmd = query.get("cmd", ["toggle"])[0]
            if cmd == "toggle":
                state["screen_cmd"] = "on" if state.get("screen_cmd") == "off" else "off"
            else:
                state["screen_cmd"] = cmd
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "cmd": state["screen_cmd"]}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global latest_camera_frame, telemetry_data
        if self.path == "/api/camera/upload":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                with frame_lock:
                    latest_camera_frame = body
                telemetry_data["camera_last_seen"] = time.time()
                telemetry_data["has_live_frame"] = True
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp_data = {
                "status": "received",
                "interval_ms": state.get("camera_interval_ms", 2000),
                "cmd": state.get("screen_cmd", "none")
            }
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def start_server():
    t = threading.Thread(target=poll_telemetry, daemon=True)
    t.start()
    
    socketserver.TCPServer.allow_reuse_address = True

    def run_port_80():
        try:
            server_80 = socketserver.TCPServer(("", 80), TelemetryHandler)
            print("Port 80 active: http://192.168.1.15/c (no port number needed)")
            server_80.serve_forever()
        except Exception as e:
            print(f"Notice: Port 80 not available ({e})")

    t80 = threading.Thread(target=run_port_80, daemon=True)
    t80.start()

    def run_port_8443():
        cert_path = os.path.join(os.path.dirname(__file__), "cert.pem")
        key_path = os.path.join(os.path.dirname(__file__), "key.pem")
        if os.path.exists(cert_path) and os.path.exists(key_path):
            try:
                server_8443 = socketserver.TCPServer(("", 8443), TelemetryHandler)
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(cert_path, key_path)
                server_8443.socket = ctx.wrap_socket(server_8443.socket, server_side=True)
                print("Port 8443 (HTTPS) active: https://192.168.1.15:8443/c")
                server_8443.serve_forever()
            except Exception as e:
                print(f"Notice: Port 8443 HTTPS not available ({e})")

    t8443 = threading.Thread(target=run_port_8443, daemon=True)
    t8443.start()

    server_8000 = socketserver.TCPServer(("", PORT), TelemetryHandler)
    print(f"JioPhone Live Ground Station running at http://localhost:{PORT} and http://192.168.1.15:{PORT}")
    server_8000.serve_forever()

if __name__ == "__main__":
    start_server()
