---
title: Dense-306
emoji: 📐
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
models:
  - Pacific-i64/Dense-306
---

# Dense-306 · vllm-i64

OpenAI-compatible inference API for the width-matched 306.5M-parameter dense
SwiGLU baseline. It is served by
[`Complexity-ML/vllm-i64`](https://github.com/Complexity-ML/vllm-i64).

```bash
curl https://Pacific-i64-Dense-306.hf.space/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dense-306",
    "prompt": "The meaning of life is",
    "max_tokens": 64,
    "temperature": 0.7,
    "stream": false
  }'
```

The CPU deployment uses continuous batching, paged KV caching, prefix caching,
streaming and dynamic INT8 packing of linear layers. Set the Space variable
`CPU_INT8=false` to serve the original floating-point weights instead.
The model repository is mounted read-only at `/home/user/app/model`; its
weights are not duplicated in the Space repository or Docker image.

Endpoints: `/health`, `/v1/models`, `/v1/completions`,
`/v1/chat/completions`, `/v1/metrics`, `/v1/monitor`, `/v1/experts`.
