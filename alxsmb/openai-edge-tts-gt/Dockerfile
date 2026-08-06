FROM python:3.12-slim

# HF Spaces 需要创建非 root 用户
RUN useradd -m -u 1000 user

WORKDIR /app

# 安装 ffmpeg 以支持更多音频格式
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt /app
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ /app

# 创建临时文件目录并赋予权限
RUN mkdir -p /tmp/tts && chown -R user:user /tmp/tts && chown -R user:user /app

# 切换到非 root 用户
USER user

# HF Spaces 要求监听 7860 端口
ENV PORT=7860
ENV REQUIRE_API_KEY=False
ENV DEFAULT_VOICE=zh-CN-XiaoxiaoNeural
EXPOSE 7860

CMD ["python", "/app/server.py"]
