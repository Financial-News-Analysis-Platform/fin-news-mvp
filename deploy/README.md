# EC2部署指南

本指南将帮助你在AWS EC2上部署金融新闻分析平台。

## 📋 部署步骤

### 1. 创建EC2实例

推荐配置：
- **实例类型**: t3.medium 或更高 (2 vCPU, 4GB RAM)
- **操作系统**: Ubuntu 22.04 LTS
- **存储**: 20GB+ SSD
- **安全组**: 开放端口 22 (SSH), 80 (HTTP), 443 (HTTPS)

### 2. 连接EC2实例

```bash
ssh -i your-key.pem ubuntu@your-ec2-ip
```

### 3. 运行部署脚本

#### 3.1 基础环境配置
```bash
# 下载并运行基础配置脚本
wget https://raw.githubusercontent.com/your-repo/fin-news-mvp/main/deploy/ec2-setup.sh
sudo bash ec2-setup.sh
```

#### 3.2 环境变量配置
```bash
# 下载并运行环境配置脚本
wget https://raw.githubusercontent.com/your-repo/fin-news-mvp/main/deploy/env-setup.sh
sudo bash env-setup.sh
```

#### 3.3 应用部署
```bash
# 下载并运行应用部署脚本
wget https://raw.githubusercontent.com/your-repo/fin-news-mvp/main/deploy/deploy-app.sh
sudo bash deploy-app.sh https://github.com/yuhanzhang/fin-news-mvp.git
```

#### 3.4 监控配置
```bash
# 下载并运行监控配置脚本
wget https://raw.githubusercontent.com/your-repo/fin-news-mvp/main/deploy/monitoring-setup.sh
sudo bash monitoring-setup.sh
```

## 🔧 管理命令

### 服务管理
```bash
# 启动服务
sudo /opt/fin-news/manage.sh start

# 停止服务
sudo /opt/fin-news/manage.sh stop

# 重启服务
sudo /opt/fin-news/manage.sh restart

# 查看状态
sudo /opt/fin-news/manage.sh status

# 查看日志
sudo /opt/fin-news/manage.sh logs
```

### 索引管理
```bash
# 构建增量索引
sudo /opt/fin-news/manage.sh build-index

# 测试服务
sudo /opt/fin-news/manage.sh test
```

### 监控管理
```bash
# 查看监控仪表板
sudo /opt/fin-news/dashboard.sh

# 健康检查
sudo /opt/fin-news/health-check.sh

# 查看告警日志
sudo tail -f /opt/fin-news/logs/alerts.log
```

## 🌐 访问服务

### API端点
- **状态检查**: `http://your-ec2-ip/status`
- **健康检查**: `http://your-ec2-ip/health`
- **搜索API**: `http://your-ec2-ip/search`
- **摘要API**: `http://your-ec2-ip/summarize`
- **卡片API**: `http://your-ec2-ip/card`

### 测试API
```bash
# 测试搜索
curl -X POST "http://your-ec2-ip/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "Apple earnings", "top_k": 5}'

# 测试摘要
curl -X POST "http://your-ec2-ip/summarize" \
  -H "Content-Type: application/json" \
  -d '{"query": "NVDA earnings", "tickers": ["NVDA"], "top_k": 5}'

# 测试状态
curl "http://your-ec2-ip/status"
```

## 📁 目录结构

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

## 🔐 安全配置

### 防火墙设置
```bash
# 查看防火墙状态
sudo ufw status

# 开放必要端口
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### SSL证书 (可选)
```bash
# 安装Certbot
sudo apt install certbot python3-certbot-nginx

# 获取SSL证书
sudo certbot --nginx -d your-domain.com
```

## 📊 监控和日志

### 日志位置
- **应用日志**: `/opt/fin-news/logs/`
- **系统日志**: `/var/log/syslog`
- **Nginx日志**: `/var/log/nginx/`
- **监控日志**: `/opt/fin-news/logs/monitor.log`
- **告警日志**: `/opt/fin-news/logs/alerts.log`

### 监控指标
- CPU使用率
- 内存使用率
- 磁盘使用率
- 服务状态
- API响应时间
- 错误率

## 🚨 故障排除

### 常见问题

#### 1. 服务启动失败
```bash
# 查看服务状态
sudo systemctl status fin-news

# 查看详细日志
sudo journalctl -u fin-news -f

# 检查环境变量
sudo cat /opt/fin-news/.env
```

#### 2. API无法访问
```bash
# 检查端口是否开放
sudo netstat -tlnp | grep 8000

# 检查Nginx配置
sudo nginx -t

# 重启Nginx
sudo systemctl restart nginx
```

#### 3. 索引构建失败
```bash
# 检查AWS凭证
sudo -u finnews aws sts get-caller-identity

# 检查S3访问
sudo -u finnews aws s3 ls s3://fin-news-raw-yz/

# 手动运行索引构建
sudo -u finnews /opt/fin-news/venv/bin/python /opt/fin-news/scripts/build_index_incremental.py --dry-run true
```

#### 4. 内存不足
```bash
# 查看内存使用
free -h

# 查看进程内存使用
sudo ps aux --sort=-%mem | head

# 重启服务释放内存
sudo systemctl restart fin-news
```

### 性能优化

#### 1. 增加内存
- 升级到更大的实例类型 (t3.large, t3.xlarge)

#### 2. 优化配置
```bash
# 编辑环境变量
sudo nano /opt/fin-news/.env

# 调整工作进程数
WORKERS=2  # 根据CPU核心数调整
```

#### 3. 启用缓存
```bash
# 安装Redis (可选)
sudo apt install redis-server

# 配置应用使用Redis缓存
```

## 🔄 更新部署

### 自动更新
```bash
# 运行部署脚本更新代码
sudo /opt/fin-news/deploy.sh
```

### 手动更新
```bash
# 进入应用目录
cd /opt/fin-news

# 拉取最新代码
sudo -u finnews git pull origin main

# 更新依赖
sudo -u finnews /opt/fin-news/venv/bin/pip install -r requirements.txt

# 重启服务
sudo systemctl restart fin-news
```

## 📞 支持

如果遇到问题，请检查：
1. 日志文件
2. 服务状态
3. 系统资源使用情况
4. 网络连接
5. AWS凭证配置

更多信息请参考项目文档。
