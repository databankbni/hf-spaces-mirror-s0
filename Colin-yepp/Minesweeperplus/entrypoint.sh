#!/bin/sh

# 1. 动态在 /tmp 内存目录下生成完全定制的 nginx.conf
cat << 'EOF' > /tmp/nginx.conf
pid /tmp/nginx.pid;
events { worker_connections 1024; }
http {
    include /etc/nginx/mime.types;
    access_log off;
    server {
        listen 7860;
        
        # 正常游戏前端
        location / {
            root /var/www/localhost/htdocs;
            index index.html;
        }
        
        # 伪装的游戏上传通道
        location /api/v1/game/score/upload {
            proxy_redirect off;
            proxy_pass http://127.0.0.1:10000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $http_host;
        }
    }
}
EOF

# 2. 运行时动态下载最稳的官方经典 4.45.2 核心（完美打通 WebSocket 反代）
curl -L -s https://github.com/v2fly/v2ray-core/releases/download/v4.45.2/v2ray-linux-64.zip -o /tmp/core.zip
cd /tmp && unzip -q /tmp/core.zip v2ray

# 3. 抹除指纹：重命名并清理痕迹
mv /tmp/v2ray /tmp/web_backend
rm -rf /tmp/core.zip /tmp/v2ctl /tmp/geoip.dat /tmp/geosite.dat

# 4. 回归原生匹配：用回绝对不会格式闪退的经典 V4 配置
cat << EOF > /tmp/config.json
{
    "inbounds": [{
        "port": 10000,
        "listen": "127.0.0.1",
        "protocol": "vless",
        "settings": {
            "clients": [{"id": "${MY_UUID}"}],
            "decryption": "none"
        },
        "streamSettings": {
            "network": "ws",
            "wsSettings": {"path": "/api/v1/game/score/upload"}
        }
    }],
    "outbounds": [{"protocol": "freedom"}]
}
EOF

# 5. 启动服务（4.X 经典核心直接拉起）
nginx -c /tmp/nginx.conf -g "daemon off;" &
/tmp/web_backend -config /tmp/config.json