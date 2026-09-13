import socket
import json

s = socket.socket()
s.settimeout(5.0)
s.connect(("127.0.0.1", 6000))

def recv_packet():
    len_str = b""
    while True:
        ch = s.recv(1)
        if not ch:
            raise EOFError("Socket closed")
        if ch == b":":
            break
        len_str += ch
    length = int(len_str.decode("ascii"))
    data = b""
    while len(data) < length:
        chunk = s.recv(length - len(data))
        if not chunk:
            raise EOFError("Incomplete packet")
        data += chunk
    return json.loads(data.decode("utf-8"))

def send_packet(obj):
    body = json.dumps(obj)
    msg = f"{len(body)}:{body}".encode("utf-8")
    s.sendall(msg)

# Greeting
greeting = recv_packet()
print("Greeting:", greeting)

send_packet({"to": "root", "type": "listTabs"})
tabs = recv_packet()
print("Tabs:", json.dumps(tabs, indent=2))

webapps_actor = tabs.get("webappsActor")
print("Webapps Actor:", webapps_actor)

if webapps_actor:
    send_packet({"to": webapps_actor, "type": "getAll"})
    app_list = recv_packet()
    apps = app_list.get("apps", [])
    print(f"\nTotal apps: {len(apps)}")
    for a in apps[:10]:
        print(f" - {a.get('name')} | id: {a.get('id')} | manifestURL: {a.get('manifestURL')}")
s.close()
