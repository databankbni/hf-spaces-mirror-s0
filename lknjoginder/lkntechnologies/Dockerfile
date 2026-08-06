FROM ubuntu:22.04

RUN apt-get update && apt-get install -y curl bash git && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && apt-get install -y nodejs

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user
WORKDIR $HOME/app

COPY --chown=user:user package*.json ./
RUN npm install

COPY --chown=user:user . .
EXPOSE 7860
CMD ["node", "server.js"]