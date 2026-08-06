import os
import subprocess
import time
import socket
import json
from threading import Thread

# 1. 自动下载并解压官方包
if not os.path.exists("alist"):
    os.system("wget https://github.com/alist-org/alist/releases/latest/download/alist-linux-amd64.tar.gz")
    os.system("tar -zxvf alist-linux-amd64.tar.gz")
    os.system("chmod +x alist")


print("正在启动 Alist 核心...")
subprocess.Popen(["./alist", "server"])

time.sleep(3)
# 强行把 admin 的密码固定为 123456
os.system("./alist admin set 123456")

# 3. 极简极速的端口转发函数
def pipe(src, dst):
    while True:
        try:
            data = src.recv(4096)
            if not data: break
            dst.sendall(data)
        except: break

def proxy():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 7860))
    server.listen(100)
    while True:
        try:
            local_conn, addr = server.accept()
            alist_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            alist_conn.connect(('127.0.0.1', 5244))
            Thread(target=pipe, args=(local_conn, alist_conn)).start()
            Thread(target=pipe, args=(alist_conn, local_conn)).start()
        except:
            time.sleep(1)

Thread(target=proxy, daemon=True).start()
print("端口代理流量转发已就绪：7860 ===> 5244")

while True:
    time.sleep(1)