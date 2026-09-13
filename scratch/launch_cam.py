import socket
import json

s = socket.socket()
s.settimeout(5.0)
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
send_packet({"to": actor, "type": "launch", "manifestURL": "app://cam_app/manifest.webapp"})
res = recv_packet()
print("Launch result:", res)
s.close()
