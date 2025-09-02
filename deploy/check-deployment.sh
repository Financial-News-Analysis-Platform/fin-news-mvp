#!/bin/bash
# 部署检查脚本
# 使用方法: sudo bash check-deployment.sh

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

# 检查函数
check_service() {
    local service_name=$1
    if systemctl is-active --quiet $service_name; then
        log_success "$service_name 服务运行正常"
        return 0
    else
        log_error "$service_name 服务未运行"
        return 1
    fi
}

check_file() {
    local file_path=$1
    if [ -f "$file_path" ]; then
        log_success "文件存在: $file_path"
        return 0
    else
        log_error "文件不存在: $file_path"
        return 1
    fi
}

check_directory() {
    local dir_path=$1
    if [ -d "$dir_path" ]; then
        log_success "目录存在: $dir_path"
        return 0
    else
        log_error "目录不存在: $dir_path"
        return 1
    fi
}

check_port() {
    local port=$1
    if netstat -tlnp | grep -q ":$port "; then
        log_success "端口 $port 正在监听"
        return 0
    else
        log_error "端口 $port 未监听"
        return 1
    fi
}

check_api() {
    local url=$1
    if curl -f -s "$url" > /dev/null 2>&1; then
        log_success "API响应正常: $url"
        return 0
    else
        log_error "API响应异常: $url"
        return 1
    fi
}

# 主检查函数
main() {
    log_info "开始部署检查..."
    
    local errors=0
    
    echo ""
    echo "=== 系统服务检查 ==="
    
    # 检查服务状态
    check_service "fin-news" || ((errors++))
    check_service "nginx" || ((errors++))
    
    echo ""
    echo "=== 文件系统检查 ==="
    
    # 检查目录
    check_directory "$APP_DIR" || ((errors++))
    check_directory "$APP_DIR/apps" || ((errors++))
    check_directory "$APP_DIR/scripts" || ((errors++))
    check_directory "$APP_DIR/logs" || ((errors++))
    check_directory "$APP_DIR/data" || ((errors++))
    
    # 检查文件
    check_file "$APP_DIR/.env" || ((errors++))
    check_file "$APP_DIR/manage.sh" || ((errors++))
    check_file "$APP_DIR/monitor.sh" || ((errors++))
    check_file "$APP_DIR/health-check.sh" || ((errors++))
    
    echo ""
    echo "=== 网络检查 ==="
    
    # 检查端口
    check_port "8000" || ((errors++))
    check_port "80" || ((errors++))
    
    echo ""
    echo "=== API检查 ==="
    
    # 检查API端点
    check_api "http://localhost:8000/status" || ((errors++))
    check_api "http://localhost/health" || ((errors++))
    
    echo ""
    echo "=== 权限检查 ==="
    
    # 检查文件权限
    if [ -O "$APP_DIR" ]; then
        log_success "应用目录权限正确"
    else
        log_error "应用目录权限错误"
        ((errors++))
    fi
    
    if [ -r "$APP_DIR/.env" ]; then
        log_success "环境变量文件可读"
    else
        log_error "环境变量文件不可读"
        ((errors++))
    fi
    
    echo ""
    echo "=== 资源检查 ==="
    
    # 检查磁盘空间
    local disk_usage=$(df "$APP_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ $disk_usage -lt 90 ]; then
        log_success "磁盘使用率正常: ${disk_usage}%"
    else
        log_warning "磁盘使用率较高: ${disk_usage}%"
    fi
    
    # 检查内存使用
    local memory_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
    if [ $memory_usage -lt 90 ]; then
        log_success "内存使用率正常: ${memory_usage}%"
    else
        log_warning "内存使用率较高: ${memory_usage}%"
    fi
    
    echo ""
    echo "=== 配置检查 ==="
    
    # 检查环境变量
    if [ -f "$APP_DIR/.env" ]; then
        if grep -q "AWS_ACCESS_KEY_ID" "$APP_DIR/.env"; then
            log_success "AWS凭证已配置"
        else
            log_warning "AWS凭证未配置"
        fi
        
        if grep -q "OPENAI_API_KEY" "$APP_DIR/.env"; then
            log_success "OpenAI API Key已配置"
        else
            log_warning "OpenAI API Key未配置"
        fi
    fi
    
    # 检查AWS连接
    if sudo -u finnews aws sts get-caller-identity > /dev/null 2>&1; then
        log_success "AWS连接正常"
    else
        log_warning "AWS连接异常"
    fi
    
    echo ""
    echo "=== 检查结果 ==="
    
    if [ $errors -eq 0 ]; then
        log_success "所有检查通过! 部署成功!"
        echo ""
        echo "🌐 服务访问地址:"
        echo "  本地: http://localhost:8000"
        echo "  外部: http://$(curl -s ifconfig.me):8000"
        echo ""
        echo "🔧 管理命令:"
        echo "  查看状态: sudo $APP_DIR/manage.sh status"
        echo "  查看日志: sudo $APP_DIR/manage.sh logs"
        echo "  监控仪表板: sudo $APP_DIR/dashboard.sh"
        echo ""
        return 0
    else
        log_error "发现 $errors 个问题，请检查并修复"
        echo ""
        echo "🔧 故障排除建议:"
        echo "1. 查看服务日志: sudo journalctl -u fin-news -f"
        echo "2. 检查配置文件: sudo cat $APP_DIR/.env"
        echo "3. 重启服务: sudo systemctl restart fin-news"
        echo "4. 查看详细状态: sudo $APP_DIR/manage.sh status"
        echo ""
        return 1
    fi
}

# 运行主检查
main "$@"
