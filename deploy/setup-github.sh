#!/bin/bash
# GitHub仓库设置脚本
# 使用方法: bash setup-github.sh [your-github-username] [repository-name]

set -e

GITHUB_USER=${1:-"yuhanzhang"}
REPO_NAME=${2:-"fin-news-mvp"}

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

log_info "设置GitHub仓库配置..."

# 1. 移除现有远程仓库
if git remote get-url origin > /dev/null 2>&1; then
    log_info "移除现有远程仓库配置..."
    git remote remove origin
fi

# 2. 添加新的远程仓库
GIT_URL="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
log_info "添加远程仓库: $GIT_URL"
git remote add origin $GIT_URL

# 3. 更新部署脚本中的仓库URL
log_info "更新部署脚本中的仓库URL..."

# 更新quick-deploy.sh
sed -i.bak "s|https://github.com/.*/.*\.git|$GIT_URL|g" deploy/quick-deploy.sh
sed -i.bak "s|https://raw.githubusercontent.com/.*/.*/main/|https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/main/|g" deploy/quick-deploy.sh

# 更新deploy-app.sh
sed -i.bak "s|https://github.com/.*/.*\.git|$GIT_URL|g" deploy/deploy-app.sh

# 更新README.md
sed -i.bak "s|https://github.com/.*/.*\.git|$GIT_URL|g" deploy/README.md
sed -i.bak "s|https://raw.githubusercontent.com/.*/.*/main/|https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/main/|g" deploy/README.md

# 清理备份文件
rm -f deploy/*.bak

log_success "GitHub仓库配置完成!"

echo ""
echo "📋 配置信息:"
echo "  GitHub用户名: $GITHUB_USER"
echo "  仓库名称: $REPO_NAME"
echo "  仓库URL: $GIT_URL"
echo ""
echo "🔧 下一步操作:"
echo "1. 在GitHub上创建仓库: $REPO_NAME"
echo "2. 推送代码到GitHub:"
echo "   git add ."
echo "   git commit -m 'Add deployment scripts'"
echo "   git push -u origin deploy-scripts"
echo ""
echo "3. 在EC2上部署:"
echo "   wget https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/main/deploy/quick-deploy.sh"
echo "   sudo bash quick-deploy.sh"
echo ""
