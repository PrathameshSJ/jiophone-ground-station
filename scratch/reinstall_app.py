import os
import zipfile
import subprocess
import socket
import json
import time
import threading

# Enforce strict watchdog
watchdog = threading.Timer(12.0, lambda: os._exit(1))
watchdog.daemon = True
watchdog.start()

PHONE_TARGET = "192.168.1.8:5555"

print("1. Rebuilding cam_app.zip...")
app_dir = r"C:\Users\admin\jio\cam_app"
zip_path = r"C:\Users\admin\jio\cam_app.zip"

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
    for filename in ['manifest.webapp', 'index.html', 'app.js', 'style.css', 'icon56.png', 'icon112.png']:
        full_path = os.path.join(app_dir, filename)
        if os.path.exists(full_path):
            z.write(full_path, arcname=filename)
print(f"cam_app.zip rebuilt ({os.path.getsize(zip_path)} bytes)")

print("2. Staging to phone...")
subprocess.run(["adb", "-s", PHONE_TARGET, "push", zip_path, "/sdcard/cam_app.zip"], check=True, timeout=8)
cmd_unpack = "mkdir -p /data/local/tmp/b2g/cam_app && cp /sdcard/cam_app.zip /data/local/tmp/b2g/cam_app/application.zip && cd /data/local/tmp/b2g/cam_app && /system/bin/busybox unzip -o application.zip"
subprocess.run(["adb", "-s", PHONE_TARGET, "shell", cmd_unpack], check=True, timeout=8)
print("Staged in /data/local/tmp/b2g/cam_app")

print("3. Connecting to Gecko RDP port 6000...")
subprocess.run(["adb", "-s", PHONE_TARGET, "forward", "tcp:6000", "localfilesystem:/data/local/debugger-socket"], timeout=5)

s = socket.socket()
s.settimeout(6.0)
s.connect(("127.0.0.1", 6000))

def recv_packet():
    len_str = b""
    while True:
        ch = s.recv(1)
        if not ch: raise EOFError()
        if ch == b":": break
        len_str += ch
    length = int(len_str.decode("ascii"))
    data = b""
    while len(data) < length:
        chunk = s.recv(length - len(data))
        if not chunk: raise EOFError()
        data += chunk
    return json.loads(data.decode("utf-8"))

def send_packet(obj):
    body = json.dumps(obj)
    msg = f"{len(body)}:{body}".encode("utf-8")
    s.sendall(msg)

recv_packet() # greeting
send_packet({"to": "root", "type": "listTabs"})
tabs = recv_packet()
actor = tabs["webappsActor"]

print("Closing existing cam_app...")
try:
    send_packet({"to": actor, "type": "close", "manifestURL": "app://cam_app/manifest.webapp"})
    print("Close:", recv_packet())
    time.sleep(0.4)
except Exception as e:
    print("Close err:", e)

print("Installing staged cam_app...")
send_packet({"to": actor, "type": "install", "appId": "cam_app"})
res_install = recv_packet()
print("Install response:", res_install)

time.sleep(0.4)
print("Launching cam_app...")
send_packet({"to": actor, "type": "launch", "manifestURL": "app://cam_app/manifest.webapp"})
res_launch = recv_packet()
print("Launch response:", res_launch)

s.close()
print("Done! App reinstalled and launched.")
watchdog.cancel()
