# EC2部署配置指南

## 🚀 快速开始

### 一键部署
```bash
# 在EC2实例上运行
sudo bash quick-deploy.sh https://github.com/your-username/fin-news-mvp.git
```

### 分步部署
```bash
# 1. 基础环境配置
sudo bash ec2-setup.sh

# 2. 环境变量配置
sudo bash env-setup.sh

# 3. 应用部署
sudo bash deploy-app.sh https://github.com/your-username/fin-news-mvp.git

# 4. 监控配置
sudo bash monitoring-setup.sh
```

## 📋 部署脚本说明

### 1. `ec2-setup.sh` - 基础环境配置
- 安装系统依赖包
- 创建应用用户和目录
- 配置Python虚拟环境
- 安装Python依赖
- 配置systemd服务
- 配置Nginx反向代理
- 设置防火墙规则

### 2. `env-setup.sh` - 环境变量配置
- 交互式配置AWS凭证
- 配置OpenAI API Key
- 设置服务参数
- 配置AWS CLI
- 测试AWS连接

### 3. `deploy-app.sh` - 应用部署
- 从Git仓库拉取代码
- 安装/更新Python依赖
- 设置文件权限
- 启动服务
- 测试API端点

### 4. `monitoring-setup.sh` - 监控配置
- 安装监控工具
- 配置系统监控
- 设置日志轮转
- 配置告警系统
- 创建健康检查

### 5. `quick-deploy.sh` - 一键部署
- 自动下载所有脚本
- 按顺序执行部署步骤
- 进行最终检查
- 显示部署结果

## 🔧 系统配置

### 目录结构
```
/opt/fin-news/
├── apps/                    # 应用代码
├── scripts/                 # 脚本文件
├── conf/                    # 配置文件
├── logs/                    # 日志文件
├── data/                    # 数据文件
├── .artifacts/              # 索引文件
├── reports/                 # 监控报告
├── .env                     # 环境变量
├── manage.sh                # 管理脚本
├── monitor.sh               # 监控脚本
├── health-check.sh          # 健康检查
├── dashboard.sh             # 监控仪表板
└── alert.sh                 # 告警脚本
```

### 服务配置
- **应用服务**: systemd服务，自动启动
- **Nginx**: 反向代理，负载均衡
- **监控**: 定时任务，健康检查
- **日志**: 自动轮转，集中管理

### 环境变量
```bash
# AWS配置
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-2

# OpenAI配置
OPENAI_API_KEY=your_openai_key

# 服务配置
HOST=0.0.0.0
PORT=8000
WORKERS=4

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=/opt/fin-news/logs/app.log
```

## 🌐 网络配置

### 端口配置
- **22**: SSH访问
- **80**: HTTP访问
- **443**: HTTPS访问 (可选)
- **8000**: 应用服务 (内部)

### 防火墙规则
```bash
# 开放必要端口
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Nginx配置
- 反向代理到应用服务
- 健康检查端点
- 负载均衡
- 静态文件服务

## 📊 监控配置

### 监控指标
- CPU使用率
- 内存使用率
- 磁盘使用率
- 服务状态
- API响应时间
- 错误率

### 告警规则
- 服务停止告警
- 资源使用率告警
- API异常告警
- 磁盘空间告警

### 日志管理
- 自动轮转
- 压缩存储
- 定期清理
- 集中收集

## 🔐 安全配置

### 用户权限
- 专用应用用户
- 最小权限原则
- 文件权限控制

### 网络安全
- 防火墙配置
- 安全组设置
- SSL证书 (可选)

### 访问控制
- SSH密钥认证
- 服务访问控制
- API访问限制

## 🚨 故障排除

### 常见问题
1. **服务启动失败**
   - 检查环境变量
   - 查看服务日志
   - 验证依赖安装

2. **API无法访问**
   - 检查端口开放
   - 验证Nginx配置
   - 测试服务状态

3. **索引构建失败**
   - 检查AWS凭证
   - 验证S3访问
   - 查看错误日志

4. **性能问题**
   - 监控资源使用
   - 调整配置参数
   - 升级实例规格

### 调试命令
```bash
# 查看服务状态
sudo systemctl status fin-news

# 查看详细日志
sudo journalctl -u fin-news -f

# 检查端口占用
sudo netstat -tlnp | grep 8000

# 测试API
curl http://localhost:8000/status

# 查看系统资源
htop
```

## 🔄 维护操作

### 日常维护
- 监控服务状态
- 检查日志文件
- 更新系统包
- 备份重要数据

### 定期任务
- 构建增量索引
- 清理旧日志
- 生成监控报告
- 更新应用代码

### 升级操作
- 备份现有版本
- 拉取最新代码
- 更新依赖包
- 重启服务

## 📞 支持信息

### 日志位置
- 应用日志: `/opt/fin-news/logs/`
- 系统日志: `/var/log/syslog`
- Nginx日志: `/var/log/nginx/`
- 监控日志: `/opt/fin-news/logs/monitor.log`

### 配置文件
- 环境变量: `/opt/fin-news/.env`
- 服务配置: `/etc/systemd/system/fin-news.service`
- Nginx配置: `/etc/nginx/sites-available/fin-news`

### 管理脚本
- 服务管理: `/opt/fin-news/manage.sh`
- 监控脚本: `/opt/fin-news/monitor.sh`
- 健康检查: `/opt/fin-news/health-check.sh`

## 📚 相关文档

- [项目README](../README.md)
- [API文档](../docs/README.md)
- [技术决策](../docs/TECHNICAL_DECISIONS.md)
- [快速参考](../QUICK_REFERENCE.md)
