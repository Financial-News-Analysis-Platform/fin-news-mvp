#!/bin/bash
# 环境变量配置脚本
# 使用方法: sudo bash env-setup.sh

set -e

APP_DIR="/opt/fin-news"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

log_info "配置环境变量..."

# 1. 创建环境变量文件
if [ ! -f "$APP_DIR/.env" ]; then
    log_info "创建环境变量文件..."
    cp $APP_DIR/.env.template $APP_DIR/.env
    chown finnews:finnews $APP_DIR/.env
    chmod 600 $APP_DIR/.env
else
    log_warning "环境变量文件已存在，将备份现有文件..."
    cp $APP_DIR/.env $APP_DIR/.env.backup.$(date +%Y%m%d_%H%M%S)
fi

# 2. 交互式配置AWS凭证
log_info "配置AWS凭证..."
echo ""
echo "请输入AWS凭证信息:"
echo ""

read -p "AWS Access Key ID: " aws_access_key
read -s -p "AWS Secret Access Key: " aws_secret_key
echo ""
read -p "AWS Region (默认: us-east-2): " aws_region
aws_region=${aws_region:-us-east-2}

# 3. 配置OpenAI API Key
log_info "配置OpenAI API Key..."
echo ""
read -s -p "OpenAI API Key (可选，留空则使用模拟模式): " openai_key
echo ""

# 4. 配置服务参数
log_info "配置服务参数..."
echo ""
read -p "服务端口 (默认: 8000): " service_port
service_port=${service_port:-8000}

read -p "工作进程数 (默认: 4): " workers
workers=${workers:-4}

read -p "日志级别 (默认: INFO): " log_level
log_level=${log_level:-INFO}

# 5. 更新环境变量文件
log_info "更新环境变量文件..."
cat > $APP_DIR/.env << EOF
# AWS配置
AWS_ACCESS_KEY_ID=$aws_access_key
AWS_SECRET_ACCESS_KEY=$aws_secret_key
AWS_DEFAULT_REGION=$aws_region

# OpenAI配置
OPENAI_API_KEY=$openai_key

# 服务配置
HOST=0.0.0.0
PORT=$service_port
WORKERS=$workers

# 日志配置
LOG_LEVEL=$log_level
LOG_FILE=$APP_DIR/logs/app.log

# 性能配置
MAX_WORKERS=$workers
TIMEOUT=300

# 应用配置
APP_DIR=$APP_DIR
PYTHONPATH=$APP_DIR
EOF

chown finnews:finnews $APP_DIR/.env
chmod 600 $APP_DIR/.env

# 6. 配置AWS CLI
log_info "配置AWS CLI..."
sudo -u finnews aws configure set aws_access_key_id "$aws_access_key"
sudo -u finnews aws configure set aws_secret_access_key "$aws_secret_key"
sudo -u finnews aws configure set default.region "$aws_region"
sudo -u finnews aws configure set default.output json

# 7. 测试AWS连接
log_info "测试AWS连接..."
if sudo -u finnews aws sts get-caller-identity > /dev/null 2>&1; then
    log_success "AWS连接测试成功"
else
    log_warning "AWS连接测试失败，请检查凭证"
fi

# 8. 更新systemd服务文件
log_info "更新systemd服务配置..."
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
ExecStart=$APP_DIR/venv/bin/uvicorn apps.service.search_api:app --host 0.0.0.0 --port $service_port --workers $workers
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

# 9. 重新加载systemd配置
systemctl daemon-reload

log_success "环境变量配置完成!"

echo ""
echo "📋 配置摘要:"
echo "  AWS Region: $aws_region"
echo "  服务端口: $service_port"
echo "  工作进程: $workers"
echo "  日志级别: $log_level"
echo "  OpenAI API: $([ -n "$openai_key" ] && echo "已配置" || echo "未配置(使用模拟模式)")"
echo ""
echo "🔧 下一步操作:"
echo "1. 上传项目代码到 $APP_DIR"
echo "2. 启动服务: sudo $APP_DIR/manage.sh start"
echo "3. 检查状态: sudo $APP_DIR/manage.sh status"
echo ""
