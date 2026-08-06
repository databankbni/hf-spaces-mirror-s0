import base64, pickle, os

pkl_path = "reference_embeddings.pkl"
if not os.path.exists(pkl_path):
    print("ERROR: reference_embeddings.pkl not found")
    import sys; sys.exit(1)

with open(pkl_path, "rb") as f:
    data = f.read()

b64 = base64.b64encode(data).decode()
print(f"Read {len(data)} bytes, base64 len={len(b64)}")

with open("_embeddings_data.py", "w") as out:
    out.write("# Auto-generated - do not edit manually\n")
    out.write("import base64, os, pickle\n\n")
    out.write(f"B64_DATA = {repr(b64)}\n\n")
    out.write("def decode_embeddings(path=None):\n")
    out.write("    if path is None:\n")
    out.write("        path = os.path.join(os.path.dirname(__file__), 'reference_embeddings.pkl')\n")
    out.write("    if os.path.exists(path):\n")
    out.write("        return\n")
    out.write("    raw = base64.b64decode(B64_DATA)\n")
    out.write("    with open(path, 'wb') as f:\n")
    out.write("        f.write(raw)\n")
    out.write("    print(f'wrote {len(raw)} bytes')\n\n")
    out.write("if __name__ == '__main__':\n")
    out.write("    decode_embeddings()\n")

print(f"Wrote _embeddings_data.py ({os.path.getsize('_embeddings_data.py')} bytes)")
