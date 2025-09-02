#!/bin/bash
# 监控和日志配置脚本
# 使用方法: sudo bash monitoring-setup.sh

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

log_info "配置监控和日志系统..."

# 1. 安装监控工具
log_info "安装监控工具..."
apt update
apt install -y \
    htop \
    iotop \
    nethogs \
    sysstat \
    logrotate \
    fail2ban \
    ufw

# 2. 配置系统监控
log_info "配置系统监控..."
cat > /etc/cron.d/system-monitor << EOF
# 系统监控任务
# 每分钟收集系统指标
* * * * * root /usr/bin/sar -u 1 1 >> /var/log/sysstat/cpu.log
* * * * * root /usr/bin/sar -r 1 1 >> /var/log/sysstat/memory.log
* * * * * root /usr/bin/sar -d 1 1 >> /var/log/sysstat/disk.log

# 每5分钟收集网络指标
*/5 * * * * root /usr/bin/sar -n DEV 1 1 >> /var/log/sysstat/network.log

# 每小时生成报告
0 * * * * root /usr/bin/sar -A > /var/log/sysstat/hourly-report.log
EOF

# 3. 配置应用监控脚本
log_info "创建应用监控脚本..."
cat > $APP_DIR/monitor.sh << 'EOF'
#!/bin/bash
# 应用监控脚本

APP_DIR="/opt/fin-news"
LOG_FILE="$APP_DIR/logs/monitor.log"

# 记录时间戳
echo "$(date): 开始监控检查" >> $LOG_FILE

# 检查服务状态
if systemctl is-active --quiet fin-news; then
    echo "$(date): 服务运行正常" >> $LOG_FILE
else
    echo "$(date): 服务未运行，尝试重启" >> $LOG_FILE
    systemctl restart fin-news
fi

# 检查API健康状态
if curl -f http://localhost:8000/status > /dev/null 2>&1; then
    echo "$(date): API健康检查通过" >> $LOG_FILE
else
    echo "$(date): API健康检查失败" >> $LOG_FILE
fi

# 检查磁盘空间
DISK_USAGE=$(df $APP_DIR | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    echo "$(date): 警告: 磁盘使用率超过80% ($DISK_USAGE%)" >> $LOG_FILE
fi

# 检查内存使用
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
if [ $MEMORY_USAGE -gt 90 ]; then
    echo "$(date): 警告: 内存使用率超过90% ($MEMORY_USAGE%)" >> $LOG_FILE
fi

# 检查日志文件大小
LOG_SIZE=$(du -m $APP_DIR/logs | tail -1 | awk '{print $1}')
if [ $LOG_SIZE -gt 1000 ]; then
    echo "$(date): 警告: 日志文件总大小超过1GB ($LOG_SIZE MB)" >> $LOG_FILE
fi

echo "$(date): 监控检查完成" >> $LOG_FILE
EOF

chmod +x $APP_DIR/monitor.sh
chown finnews:finnews $APP_DIR/monitor.sh

# 4. 配置监控定时任务
log_info "配置监控定时任务..."
cat > /etc/cron.d/fin-news-monitor << EOF
# 应用监控任务
# 每5分钟检查服务状态
*/5 * * * * finnews $APP_DIR/monitor.sh

# 每天凌晨1点清理旧日志
0 1 * * * finnews find $APP_DIR/logs -name "*.log.*" -mtime +7 -delete

# 每周日凌晨2点生成监控报告
0 2 * * 0 finnews $APP_DIR/generate-report.sh
EOF

# 5. 创建监控报告生成脚本
log_info "创建监控报告脚本..."
cat > $APP_DIR/generate-report.sh << 'EOF'
#!/bin/bash
# 生成监控报告

APP_DIR="/opt/fin-news"
REPORT_DIR="$APP_DIR/reports"
REPORT_FILE="$REPORT_DIR/weekly-report-$(date +%Y%m%d).txt"

mkdir -p $REPORT_DIR

echo "=== 金融新闻分析平台 - 周报 ===" > $REPORT_FILE
echo "生成时间: $(date)" >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "=== 系统状态 ===" >> $REPORT_FILE
echo "CPU使用率:" >> $REPORT_FILE
sar -u | tail -5 >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "内存使用率:" >> $REPORT_FILE
free -h >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "磁盘使用率:" >> $REPORT_FILE
df -h >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "=== 服务状态 ===" >> $REPORT_FILE
systemctl status fin-news --no-pager >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "=== 应用日志统计 ===" >> $REPORT_FILE
echo "错误日志数量: $(grep -c "ERROR" $APP_DIR/logs/*.log 2>/dev/null || echo 0)" >> $REPORT_FILE
echo "警告日志数量: $(grep -c "WARNING" $APP_DIR/logs/*.log 2>/dev/null || echo 0)" >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "=== API使用统计 ===" >> $REPORT_FILE
echo "搜索请求数量: $(grep -c "POST /search" $APP_DIR/logs/*.log 2>/dev/null || echo 0)" >> $REPORT_FILE
echo "摘要请求数量: $(grep -c "POST /summarize" $APP_DIR/logs/*.log 2>/dev/null || echo 0)" >> $REPORT_FILE
echo "卡片请求数量: $(grep -c "POST /card" $APP_DIR/logs/*.log 2>/dev/null || echo 0)" >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "报告已生成: $REPORT_FILE"
EOF

chmod +x $APP_DIR/generate-report.sh
chown finnews:finnews $APP_DIR/generate-report.sh

# 6. 配置日志轮转
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

$APP_DIR/logs/monitor.log {
    weekly
    missingok
    rotate 12
    compress
    delaycompress
    notifempty
    create 644 finnews finnews
}
EOF

# 7. 配置fail2ban
log_info "配置fail2ban..."
cat > /etc/fail2ban/jail.local << EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = ssh
logpath = /var/log/auth.log
maxretry = 3

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 10
EOF

systemctl enable fail2ban
systemctl start fail2ban

# 8. 创建健康检查脚本
log_info "创建健康检查脚本..."
cat > $APP_DIR/health-check.sh << 'EOF'
#!/bin/bash
# 健康检查脚本

APP_DIR="/opt/fin-news"
HEALTH_FILE="$APP_DIR/health.status"

# 检查服务状态
if systemctl is-active --quiet fin-news; then
    SERVICE_STATUS="healthy"
else
    SERVICE_STATUS="unhealthy"
fi

# 检查API响应
if curl -f http://localhost:8000/status > /dev/null 2>&1; then
    API_STATUS="healthy"
else
    API_STATUS="unhealthy"
fi

# 检查磁盘空间
DISK_USAGE=$(df $APP_DIR | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -lt 90 ]; then
    DISK_STATUS="healthy"
else
    DISK_STATUS="unhealthy"
fi

# 检查内存使用
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
if [ $MEMORY_USAGE -lt 95 ]; then
    MEMORY_STATUS="healthy"
else
    MEMORY_STATUS="unhealthy"
fi

# 生成健康状态文件
cat > $HEALTH_FILE << EOF
{
    "timestamp": "$(date -Iseconds)",
    "service": "$SERVICE_STATUS",
    "api": "$API_STATUS",
    "disk": "$DISK_STATUS",
    "memory": "$MEMORY_STATUS",
    "disk_usage": $DISK_USAGE,
    "memory_usage": $MEMORY_USAGE
}
EOF

# 如果任何组件不健康，返回非零退出码
if [ "$SERVICE_STATUS" != "healthy" ] || [ "$API_STATUS" != "healthy" ] || [ "$DISK_STATUS" != "healthy" ] || [ "$MEMORY_STATUS" != "healthy" ]; then
    exit 1
fi
EOF

chmod +x $APP_DIR/health-check.sh
chown finnews:finnews $APP_DIR/health-check.sh

# 9. 配置Nginx健康检查端点
log_info "配置Nginx健康检查..."
cat > /etc/nginx/sites-available/fin-news << EOF
server {
    listen 80;
    server_name _;

    # 健康检查端点
    location /health {
        access_log off;
        try_files \$uri @health_check;
    }

    location @health_check {
        content_by_lua_block {
            local handle = io.popen("/opt/fin-news/health-check.sh")
            local result = handle:read("*a")
            handle:close()
            
            if result == "" then
                ngx.status = 200
                ngx.say("healthy")
            else
                ngx.status = 503
                ngx.say("unhealthy")
            end
        }
    }

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
}
EOF

# 安装lua模块（如果需要）
apt install -y nginx-module-lua || true

# 重新加载Nginx配置
nginx -t && systemctl reload nginx

# 10. 创建监控仪表板脚本
log_info "创建监控仪表板..."
cat > $APP_DIR/dashboard.sh << 'EOF'
#!/bin/bash
# 监控仪表板

clear
echo "=== 金融新闻分析平台 - 监控仪表板 ==="
echo "更新时间: $(date)"
echo ""

# 服务状态
echo "🔧 服务状态:"
if systemctl is-active --quiet fin-news; then
    echo "  ✅ 应用服务: 运行中"
else
    echo "  ❌ 应用服务: 停止"
fi

if systemctl is-active --quiet nginx; then
    echo "  ✅ Nginx: 运行中"
else
    echo "  ❌ Nginx: 停止"
fi

echo ""

# 系统资源
echo "💻 系统资源:"
echo "  CPU使用率: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)%"
echo "  内存使用率: $(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100.0}')"
echo "  磁盘使用率: $(df /opt/fin-news | tail -1 | awk '{print $5}')"

echo ""

# API状态
echo "🌐 API状态:"
if curl -f http://localhost:8000/status > /dev/null 2>&1; then
    echo "  ✅ API服务: 正常"
    # 获取API状态信息
    API_INFO=$(curl -s http://localhost:8000/status 2>/dev/null || echo "{}")
    if [ "$API_INFO" != "{}" ]; then
        echo "  版本: $(echo $API_INFO | jq -r '.version // "unknown"')"
        echo "  索引向量数: $(echo $API_INFO | jq -r '.ntotal // 0')"
    fi
else
    echo "  ❌ API服务: 异常"
fi

echo ""

# 最近日志
echo "📋 最近日志 (最后5条):"
if [ -f "/opt/fin-news/logs/monitor.log" ]; then
    tail -5 /opt/fin-news/logs/monitor.log | while read line; do
        echo "  $line"
    done
else
    echo "  暂无监控日志"
fi

echo ""
echo "按 Ctrl+C 退出，或等待30秒自动刷新..."
sleep 30
EOF

chmod +x $APP_DIR/dashboard.sh
chown finnews:finnews $APP_DIR/dashboard.sh

# 11. 创建告警脚本
log_info "创建告警脚本..."
cat > $APP_DIR/alert.sh << 'EOF'
#!/bin/bash
# 告警脚本

APP_DIR="/opt/fin-news"
ALERT_LOG="$APP_DIR/logs/alerts.log"

# 检查服务状态
if ! systemctl is-active --quiet fin-news; then
    echo "$(date): 告警: 应用服务停止" >> $ALERT_LOG
    # 这里可以添加邮件或短信告警
fi

# 检查API状态
if ! curl -f http://localhost:8000/status > /dev/null 2>&1; then
    echo "$(date): 告警: API服务异常" >> $ALERT_LOG
fi

# 检查磁盘空间
DISK_USAGE=$(df $APP_DIR | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 85 ]; then
    echo "$(date): 告警: 磁盘使用率过高 ($DISK_USAGE%)" >> $ALERT_LOG
fi

# 检查内存使用
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
if [ $MEMORY_USAGE -gt 90 ]; then
    echo "$(date): 告警: 内存使用率过高 ($MEMORY_USAGE%)" >> $ALERT_LOG
fi
EOF

chmod +x $APP_DIR/alert.sh
chown finnews:finnews $APP_DIR/alert.sh

# 12. 配置告警定时任务
cat > /etc/cron.d/fin-news-alerts << EOF
# 告警检查任务
# 每10分钟检查一次
*/10 * * * * finnews $APP_DIR/alert.sh
EOF

log_success "监控和日志系统配置完成!"

echo ""
echo "📋 监控功能:"
echo "  ✅ 系统资源监控"
echo "  ✅ 服务状态监控"
echo "  ✅ API健康检查"
echo "  ✅ 日志轮转"
echo "  ✅ 安全防护 (fail2ban)"
echo "  ✅ 告警系统"
echo ""
echo "🔧 监控命令:"
echo "  查看仪表板: sudo $APP_DIR/dashboard.sh"
echo "  健康检查: sudo $APP_DIR/health-check.sh"
echo "  查看告警: sudo tail -f $APP_DIR/logs/alerts.log"
echo "  查看监控日志: sudo tail -f $APP_DIR/logs/monitor.log"
echo ""
echo "🌐 健康检查端点:"
echo "  http://your-server/health"
echo ""
