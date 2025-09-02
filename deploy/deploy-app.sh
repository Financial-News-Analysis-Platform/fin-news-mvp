#!/bin/bash
# 应用部署脚本
# 使用方法: sudo bash deploy-app.sh [git-repo-url]

set -e

APP_DIR="/opt/fin-news"
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

log_info "开始部署应用..."

# 1. 停止服务
log_info "停止现有服务..."
systemctl stop fin-news || true

# 2. 备份现有代码
if [ -d "$APP_DIR/apps" ]; then
    log_info "备份现有代码..."
    backup_dir="$APP_DIR/backup.$(date +%Y%m%d_%H%M%S)"
    sudo -u finnews mkdir -p "$backup_dir"
    sudo -u finnews cp -r "$APP_DIR/apps" "$backup_dir/"
    sudo -u finnews cp -r "$APP_DIR/scripts" "$backup_dir/" 2>/dev/null || true
    sudo -u finnews cp -r "$APP_DIR/conf" "$backup_dir/" 2>/dev/null || true
    log_success "代码已备份到 $backup_dir"
fi

# 3. 克隆或更新代码
log_info "获取最新代码..."
cd $APP_DIR

if [ -d ".git" ]; then
    log_info "更新现有仓库..."
    sudo -u finnews git fetch origin
    sudo -u finnews git reset --hard origin/main
else
    log_info "克隆新仓库..."
    sudo -u finnews git clone $GIT_REPO temp_repo
    sudo -u finnews cp -r temp_repo/* .
    sudo -u finnews cp -r temp_repo/.* . 2>/dev/null || true
    sudo -u finnews rm -rf temp_repo
fi

# 4. 设置文件权限
log_info "设置文件权限..."
chown -R finnews:finnews $APP_DIR
chmod +x $APP_DIR/scripts/*.py 2>/dev/null || true

# 5. 安装/更新Python依赖
log_info "安装Python依赖..."
sudo -u finnews $APP_DIR/venv/bin/pip install --upgrade pip
sudo -u finnews $APP_DIR/venv/bin/pip install -r $APP_DIR/requirements.txt

# 6. 创建必要的目录
log_info "创建必要目录..."
sudo -u finnews mkdir -p $APP_DIR/logs
sudo -u finnews mkdir -p $APP_DIR/data
sudo -u finnews mkdir -p $APP_DIR/.artifacts
sudo -u finnews mkdir -p $APP_DIR/tmp

# 7. 检查环境变量
if [ ! -f "$APP_DIR/.env" ]; then
    log_warning "环境变量文件不存在，请先运行 env-setup.sh"
    log_info "创建默认环境变量文件..."
    cp $APP_DIR/.env.template $APP_DIR/.env
    chown finnews:finnews $APP_DIR/.env
    chmod 600 $APP_DIR/.env
fi

# 8. 测试应用配置
log_info "测试应用配置..."
cd $APP_DIR
if sudo -u finnews $APP_DIR/venv/bin/python -c "import apps.service.search_api; print('应用配置正确')" 2>/dev/null; then
    log_success "应用配置测试通过"
else
    log_warning "应用配置测试失败，请检查依赖和配置"
fi

# 9. 启动服务
log_info "启动服务..."
systemctl start fin-news

# 10. 等待服务启动
log_info "等待服务启动..."
sleep 10

# 11. 检查服务状态
log_info "检查服务状态..."
if systemctl is-active --quiet fin-news; then
    log_success "服务启动成功"
else
    log_error "服务启动失败"
    systemctl status fin-news --no-pager
    exit 1
fi

# 12. 测试API端点
log_info "测试API端点..."
if curl -f http://localhost:8000/status > /dev/null 2>&1; then
    log_success "API端点测试通过"
else
    log_warning "API端点测试失败，请检查服务日志"
fi

# 13. 显示服务信息
log_info "显示服务信息..."
echo ""
echo "📋 部署完成!"
echo ""
echo "🔧 服务状态:"
systemctl status fin-news --no-pager -l
echo ""
echo "🌐 访问地址:"
echo "  本地: http://localhost:8000"
echo "  外部: http://$(curl -s ifconfig.me):8000"
echo ""
echo "📊 API端点:"
echo "  状态检查: curl http://localhost:8000/status"
echo "  搜索API: curl -X POST http://localhost:8000/search -H 'Content-Type: application/json' -d '{\"query\": \"test\"}'"
echo "  摘要API: curl -X POST http://localhost:8000/summarize -H 'Content-Type: application/json' -d '{\"query\": \"test\"}'"
echo ""
echo "🔧 管理命令:"
echo "  查看日志: sudo $APP_DIR/manage.sh logs"
echo "  重启服务: sudo $APP_DIR/manage.sh restart"
echo "  构建索引: sudo $APP_DIR/manage.sh build-index"
echo ""

log_success "应用部署完成!"
