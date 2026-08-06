FROM python:3.11-slim

# 以 root 安装系统依赖（LibreOffice + 中文字体）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice libreoffice-l10n-zh-cn \
    fonts-wqy-zenhei fonts-wqy-microhei \
    fonts-noto-cjk fonts-noto-cjk-extra \
    fontconfig \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

# 把 "宋体" / "SimSun" 字体名映射到 Noto Serif CJK（思源宋体），保证模板里指定的"宋体"在 Linux 也能正确渲染
RUN mkdir -p /etc/fonts/conf.d && cat > /etc/fonts/conf.d/99-songti-alias.conf <<'EOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <alias><family>宋体</family><accept><family>Noto Serif CJK SC</family></accept></alias>
  <alias><family>SimSun</family><accept><family>Noto Serif CJK SC</family></accept></alias>
  <alias><family>NSimSun</family><accept><family>Noto Serif CJK SC</family></accept></alias>
</fontconfig>
EOF
RUN fc-cache -fv

# Hugging Face 要求非 root 用户运行
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# 安装 Python 依赖
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# 拷贝应用文件
COPY --chown=user main.py .
COPY --chown=user 合同模板_占位符版.xlsx .
COPY --chown=user xl_logo.png .
COPY --chown=user seal_xianling.png .

ENV TEMPLATE_PATH=/home/user/app/合同模板_占位符版.xlsx
ENV LIBREOFFICE_BIN=libreoffice
ENV COUNTER_FILE=/tmp/counter.txt
ENV COUNTER_START=0
ENV PORT=7860

EXPOSE 7860

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]
