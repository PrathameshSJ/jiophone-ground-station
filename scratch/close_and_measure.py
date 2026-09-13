import socket
import json
import time
import subprocess

s = socket.socket()
s.settimeout(4)
s.connect(("127.0.0.1", 6000))

def rp():
    ls = b""
    while True:
        c = s.recv(1)
        if c == b":": break
        ls += c
    buf = b""
    n = int(ls)
    while len(buf) < n: buf += s.recv(n - len(buf))
    return json.loads(buf.decode())

def sp(o):
    b = json.dumps(o)
    s.sendall(f"{len(b)}:{b}".encode())

rp()
sp({"to": "root", "type": "listTabs"})
actor = rp()["webappsActor"]
sp({"to": actor, "type": "close", "manifestURL": "app://cam_app/manifest.webapp"})
print("Close response:", rp())
s.close()

time.sleep(2.5)
res = subprocess.run(["adb", "-s", "192.168.1.8:5555", "shell", "cat /sys/class/power_supply/battery/current_now"], capture_output=True, text=True, timeout=5)
print("Current after closing cam_app:", res.stdout.strip())
