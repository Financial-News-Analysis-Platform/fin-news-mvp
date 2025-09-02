#!/bin/bash
# 一键部署脚本
# 使用方法: sudo bash quick-deploy.sh [git-repo-url]

set -e

GIT_REPO=${1:-"https://github.com/Financial-News-Analysis-Platform/fin-news-mvp.git"}

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

log_info "开始一键部署金融新闻分析平台..."

# 1. 下载部署脚本
log_info "下载部署脚本..."
DEPLOY_DIR="/tmp/fin-news-deploy"
mkdir -p $DEPLOY_DIR
cd $DEPLOY_DIR

# 下载所有部署脚本
wget -q https://raw.githubusercontent.com/Financial-News-Analysis-Platform/fin-news-mvp/deploy-scripts/deploy/ec2-setup.sh
wget -q https://raw.githubusercontent.com/Financial-News-Analysis-Platform/fin-news-mvp/deploy-scripts/deploy/env-setup.sh
wget -q https://raw.githubusercontent.com/Financial-News-Analysis-Platform/fin-news-mvp/deploy-scripts/deploy/deploy-app.sh
wget -q https://raw.githubusercontent.com/Financial-News-Analysis-Platform/fin-news-mvp/deploy-scripts/deploy/monitoring-setup.sh

chmod +x *.sh

# 2. 运行基础环境配置
log_info "配置基础环境..."
bash ec2-setup.sh

# 3. 配置环境变量
log_info "配置环境变量..."
bash env-setup.sh

# 4. 部署应用
log_info "部署应用..."
bash deploy-app.sh $GIT_REPO

# 5. 配置监控
log_info "配置监控..."
bash monitoring-setup.sh

# 6. 清理临时文件
log_info "清理临时文件..."
rm -rf $DEPLOY_DIR

# 7. 最终检查
log_info "进行最终检查..."

APP_DIR="/opt/fin-news"

# 检查服务状态
if systemctl is-active --quiet fin-news; then
    log_success "应用服务运行正常"
else
    log_error "应用服务启动失败"
    exit 1
fi

# 检查API状态
if curl -f http://localhost:8000/status > /dev/null 2>&1; then
    log_success "API服务正常"
else
    log_warning "API服务可能有问题，请检查日志"
fi

# 检查Nginx状态
if systemctl is-active --quiet nginx; then
    log_success "Nginx服务运行正常"
else
    log_error "Nginx服务启动失败"
    exit 1
fi

# 8. 显示部署结果
log_success "部署完成!"

echo ""
echo "🎉 金融新闻分析平台部署成功!"
echo ""
echo "📋 服务信息:"
echo "  应用目录: $APP_DIR"
echo "  服务状态: $(systemctl is-active fin-news)"
echo "  API地址: http://$(curl -s ifconfig.me):8000"
echo "  健康检查: http://$(curl -s ifconfig.me)/health"
echo ""
echo "🔧 管理命令:"
echo "  查看状态: sudo $APP_DIR/manage.sh status"
echo "  查看日志: sudo $APP_DIR/manage.sh logs"
echo "  重启服务: sudo $APP_DIR/manage.sh restart"
echo "  构建索引: sudo $APP_DIR/manage.sh build-index"
echo "  监控仪表板: sudo $APP_DIR/dashboard.sh"
echo ""
echo "🌐 测试API:"
echo "  curl http://$(curl -s ifconfig.me):8000/status"
echo "  curl -X POST http://$(curl -s ifconfig.me):8000/search -H 'Content-Type: application/json' -d '{\"query\": \"test\"}'"
echo ""
echo "📚 更多信息请查看: $APP_DIR/README.md"
echo ""

log_success "部署完成! 请访问 http://$(curl -s ifconfig.me):8000 测试服务"
