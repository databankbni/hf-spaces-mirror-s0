import os
import subprocess

NODE_DIR = "./node-v22.14.0-linux-x64"

if not os.path.exists(NODE_DIR):
    print("Downloading Node.js v22...")
    os.system("wget -q https://nodejs.org/dist/v22.14.0/node-v22.14.0-linux-x64.tar.xz")
    print("Extracting Node.js...")
    os.system("tar -xf node-v22.14.0-linux-x64.tar.xz")
    os.system("rm node-v22.14.0-linux-x64.tar.xz")

# Add Node.js bin to PATH
os.environ["PATH"] = os.path.abspath(f"{NODE_DIR}/bin") + ":" + os.environ.get("PATH", "")

print("Node.js Version:")
os.system("node -v")

print("Installing npm dependencies...")
subprocess.run(["npm", "install"], check=True)

print("Starting Node.js application...")
node_path = os.path.abspath(f"{NODE_DIR}/bin/node")
os.execl(node_path, "node", "app.js")
