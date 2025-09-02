tui daobu shu da#!/bin/bash
# EC2部署脚本 - 金融新闻分析平台
# 使用方法: sudo bash ec2-setup.sh

set -e

echo "🚀 开始EC2环境配置..."

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    log_error "请使用sudo运行此脚本"
    exit 1
fi

# 1. 更新系统包
log_info "更新系统包..."
apt update && apt upgrade -y

# 2. 安装基础依赖
log_info "安装基础依赖..."
apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    git \
    curl \
    wget \
    unzip \
    htop \
    nginx \
    supervisor \
    jq \
    tree \
    vim \
    tmux

# 3. 安装AWS CLI (使用官方方法)
log_info "安装AWS CLI..."
if ! command -v aws &> /dev/null; then
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    ./aws/install
    rm -rf awscliv2.zip aws/
    log_success "AWS CLI安装完成"
else
    log_info "AWS CLI已安装"
fi

# 4. 创建应用用户
log_info "创建应用用户..."
if ! id "finnews" &>/dev/null; then
    useradd -m -s /bin/bash finnews
    usermod -aG sudo finnews
    log_success "创建用户 finnews"
else
    log_info "用户 finnews 已存在"
fi

# 5. 创建应用目录
log_info "创建应用目录..."
APP_DIR="/opt/fin-news"
mkdir -p $APP_DIR
mkdir -p $APP_DIR/logs
mkdir -p $APP_DIR/data
mkdir -p $APP_DIR/.artifacts
chown -R finnews:finnews $APP_DIR

# 5. 配置Python环境
log_info "配置Python环境..."
sudo -u finnews python3 -m venv $APP_DIR/venv
sudo -u finnews $APP_DIR/venv/bin/pip install --upgrade pip

# 6. 安装基础Python依赖
log_info "安装基础Python依赖..."
sudo -u finnews $APP_DIR/venv/bin/pip install --upgrade pip
sudo -u finnews $APP_DIR/venv/bin/pip install \
    fastapi==0.116.1 \
    uvicorn==0.35.0 \
    pydantic==2.5.0 \
    python-dotenv==1.0.0 \
    pandas==2.1.4 \
    numpy==1.24.3 \
    requests==2.31.0 \
    boto3>=1.26.0 \
    tqdm==4.66.1 \
    click==8.1.7

# 7. 配置AWS CLI
log_info "配置AWS CLI..."
sudo -u finnews mkdir -p /home/finnews/.aws
cat > /home/finnews/.aws/config << EOF
[default]
region = us-east-2
output = json
EOF
chown -R finnews:finnews /home/finnews/.aws

# 8. 创建环境变量模板
log_info "创建环境变量模板..."
cat > $APP_DIR/.env.template << 'EOF'
# AWS配置
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_DEFAULT_REGION=us-east-2

# OpenAI配置
OPENAI_API_KEY=your_openai_api_key_here

# 服务配置
HOST=0.0.0.0
PORT=8000
WORKERS=4

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=/opt/fin-news/logs/app.log

# 性能配置
MAX_WORKERS=4
TIMEOUT=300
EOF

# 9. 创建systemd服务文件
log_info "创建systemd服务..."
cat > /etc/systemd/system/fin-news.service << EOF
[Unit]
Description=Financial News RAG Service
After=network.target

[Service]
Type=exec
User=finnews
Group=finnews
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/uvicorn apps.service.search_api:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=fin-news

# 环境变量
EnvironmentFile=$APP_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

# 10. 配置Nginx反向代理
log_info "配置Nginx..."
cat > /etc/nginx/sites-available/fin-news << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # 增加超时时间
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # 健康检查端点
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
EOF

# 启用站点
ln -sf /etc/nginx/sites-available/fin-news /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 测试Nginx配置
nginx -t

# 11. 创建部署脚本
log_info "创建部署脚本..."
cat > $APP_DIR/deploy.sh << 'EOF'
#!/bin/bash
# 部署脚本

set -e

APP_DIR="/opt/fin-news"
cd $APP_DIR

echo "🚀 开始部署..."

# 1. 备份当前版本
if [ -d "apps" ]; then
    echo "备份当前版本..."
    sudo -u finnews cp -r apps apps.backup.$(date +%Y%m%d_%H%M%S)
fi

# 2. 从Git拉取最新代码
echo "拉取最新代码..."
sudo -u finnews git pull origin main

# 3. 安装/更新依赖
echo "更新依赖..."
sudo -u finnews $APP_DIR/venv/bin/pip install -r requirements.txt

# 4. 重启服务
echo "重启服务..."
systemctl restart fin-news
systemctl restart nginx

# 5. 检查服务状态
echo "检查服务状态..."
sleep 5
systemctl status fin-news --no-pager
curl -f http://localhost:8000/status || echo "服务启动失败"

echo "✅ 部署完成!"
EOF

chmod +x $APP_DIR/deploy.sh
chown finnews:finnews $APP_DIR/deploy.sh

# 12. 创建管理脚本
log_info "创建管理脚本..."
cat > $APP_DIR/manage.sh << 'EOF'
#!/bin/bash
# 管理脚本

APP_DIR="/opt/fin-news"
SERVICE_NAME="fin-news"

case "$1" in
    start)
        echo "启动服务..."
        systemctl start $SERVICE_NAME
        systemctl start nginx
        ;;
    stop)
        echo "停止服务..."
        systemctl stop $SERVICE_NAME
        systemctl stop nginx
        ;;
    restart)
        echo "重启服务..."
        systemctl restart $SERVICE_NAME
        systemctl restart nginx
        ;;
    status)
        echo "服务状态:"
        systemctl status $SERVICE_NAME --no-pager
        echo ""
        echo "Nginx状态:"
        systemctl status nginx --no-pager
        ;;
    logs)
        echo "查看日志..."
        journalctl -u $SERVICE_NAME -f
        ;;
    build-index)
        echo "构建索引..."
        cd $APP_DIR
        sudo -u finnews $APP_DIR/venv/bin/python scripts/build_index_incremental.py --limit 1000
        ;;
    test)
        echo "测试服务..."
        curl -f http://localhost:8000/status
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|logs|build-index|test}"
        exit 1
        ;;
esac
EOF

chmod +x $APP_DIR/manage.sh
chown finnews:finnews $APP_DIR/manage.sh

# 13. 创建日志轮转配置
log_info "配置日志轮转..."
cat > /etc/logrotate.d/fin-news << EOF
$APP_DIR/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 finnews finnews
    postrotate
        systemctl reload fin-news
    endscript
}
EOF

# 14. 设置定时任务
log_info "设置定时任务..."
cat > /etc/cron.d/fin-news << EOF
# 每天凌晨2点构建增量索引
0 2 * * * finnews cd $APP_DIR && $APP_DIR/venv/bin/python scripts/build_index_incremental.py --limit 1000 >> $APP_DIR/logs/cron.log 2>&1

# 每周日凌晨3点清理旧日志
0 3 * * 0 finnews find $APP_DIR/logs -name "*.log.*" -mtime +30 -delete
EOF

# 15. 配置防火墙
log_info "配置防火墙..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 16. 启动服务
log_info "启动服务..."
systemctl daemon-reload
systemctl enable fin-news
systemctl enable nginx
systemctl start nginx

log_success "EC2环境配置完成!"

echo ""
echo "📋 下一步操作:"
echo "1. 配置环境变量: sudo nano $APP_DIR/.env"
echo "2. 上传项目代码到 $APP_DIR"
echo "3. 启动服务: sudo $APP_DIR/manage.sh start"
echo "4. 检查状态: sudo $APP_DIR/manage.sh status"
echo ""
echo "🔧 管理命令:"
echo "  启动服务: sudo $APP_DIR/manage.sh start"
echo "  停止服务: sudo $APP_DIR/manage.sh stop"
echo "  重启服务: sudo $APP_DIR/manage.sh restart"
echo "  查看日志: sudo $APP_DIR/manage.sh logs"
echo "  构建索引: sudo $APP_DIR/manage.sh build-index"
echo "  测试服务: sudo $APP_DIR/manage.sh test"
echo ""
echo "📁 重要目录:"
echo "  应用目录: $APP_DIR"
echo "  日志目录: $APP_DIR/logs"
echo "  配置文件: $APP_DIR/.env"
echo ""
