import socket
import json
import base64
import time
import subprocess

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

send_packet({"to": actor, "type": "uploadPackage"})
res1 = recv_packet()
print("Upload response:", res1)
upload_actor = res1["actor"]

with open("C:/Users/admin/jio/cam_app.zip", "rb") as f:
    zip_bytes = f.read()

CHUNK_SIZE = 16384
for i in range(0, len(zip_bytes), CHUNK_SIZE):
    chunk = zip_bytes[i:i+CHUNK_SIZE]
    b64 = base64.b64encode(chunk).decode("ascii")
    send_packet({"to": upload_actor, "type": "chunk", "chunk": b64})
    recv_packet()

send_packet({"to": upload_actor, "type": "done"})
res2 = recv_packet()
print("Done response:", res2)

# Check what is in /data/local/tmp/b2g
out = subprocess.check_output(["adb", "-s", "192.168.1.8:5555", "shell", "ls -la /data/local/tmp/b2g"]).decode()
print("Directory listing:\n", out)

s.close()
