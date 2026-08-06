FROM node:18-slim

RUN apt-get update && apt-get install -y \
    chromium \
    fonts-ipafont-gothic fonts-wqy-zenhei fonts-thai-tlwg fonts-kacst fonts-freefont-ttf libxss1 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV TZ=Asia/Shanghai
ENV NODE_ENV=production

WORKDIR /app

# 1. 创建数据集挂载目录并授权（和你代码里的路径完全一致）
RUN mkdir -p /datasets/txc1/tdc-shared-data && chmod -R 777 /datasets/txc1/tdc-shared-data

# 2. 声明 Volume，让 HF 自动挂载 Dataset
VOLUME ["/datasets/txc1/tdc-shared-data"]

COPY package.json .
RUN npm install

COPY . .

EXPOSE 7860

CMD ["node", "main.js"]
