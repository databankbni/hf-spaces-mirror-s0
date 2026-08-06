#!/bin/bash
set -euo pipefail

echo "Starting MktBook initialization..."

# 1. Generate LTI 1.3 Private Key if missing
if [ ! -f "${LTI_PRIVATE_KEY_PATH}" ]; then
    echo "LTI Private Key not found. Generating a new one..."
    python -c '
import os
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

key_path = os.environ.get("LTI_PRIVATE_KEY_PATH", "/app/lti_private_key.pem")
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption()
)
with open(key_path, "wb") as f:
    f.write(pem)
print("Successfully generated new LTI private key at:", key_path)
'
fi

# 2. Run MktBook application
echo "Starting MktBook Bot Marketplace..."
python -m mktbook.main
