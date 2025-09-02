# 金融新闻 RAG 系统 - 快速参考

## 🚀 快速启动

### 1. 环境设置
```bash
# 安装依赖
pip install -r requirements.txt

# 配置AWS凭证
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-2
```

### 2. 构建索引
```bash
# 基本构建
python -m apps.index.build_index_aws --limit 1000

# 生产构建
python -m apps.index.build_index_aws --limit 2000 --min_body_chars 400
```

### 3. 启动服务
```bash
# 启动检索服务
uvicorn apps.service.search_api:app --host 0.0.0.0 --port 8000
```

### 4. 测试服务
```bash
# 测试搜索
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "Apple earnings", "top_k": 5}'

# 测试AI摘要
curl -X POST "http://localhost:8000/summarize" \
  -H "Content-Type: application/json" \
  -d '{"query": "NVDA earnings", "tickers": ["NVDA"], "top_k": 5}'

# 测试股票卡片
curl -X POST "http://localhost:8000/card" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2025-08-21", "top_k": 5}'

# 查看状态
curl "http://localhost:8000/status"

# 运行基准测试
curl -X POST "http://localhost:8000/bench/weak_recall"
```

## 📊 性能指标

### 当前系统状态
- **文档数量**: 197 个
- **文本块数量**: 511 个
- **向量维度**: 384 维
- **股票覆盖**: 192 个唯一股票
- **时间跨度**: 55 个唯一日期

### 检索性能
- **召回率**: 71% (基础) → 100% (带过滤)
- **搜索延迟**: 0.03-21ms
- **向量质量**: L2 范数 = 1.0000
- **分块质量**: 平均 379-411 tokens

## 🔧 核心模块

### 文本分块 (TextChunker)
```python
from apps.index.chunk import TextChunker

chunker = TextChunker(
    target_tokens=360,    # 目标块大小
    max_tokens=460,       # 最大块大小
    overlap_tokens=40,    # 重叠token数
    min_tokens=200,       # 最小块大小
    use_blingfire=True    # 使用BlingFire分割器
)

chunks = chunker.split_text(title, body)
```

### 文本嵌入 (TextEmbedder)
```python
from apps.index.embed import TextEmbedder

embedder = TextEmbedder(normalize=True)
embeddings = embedder.encode(texts)
```

### 在线检索服务
```python
# FastAPI 服务端点
POST /search          # 基础向量搜索
POST /summarize       # AI驱动的摘要生成
POST /card            # 股票信息卡片
GET /status           # 服务状态检查
```

## 📁 关键文件

### 核心模块
- `apps/index/chunk.py` - 文本分块模块
- `apps/index/embed.py` - 文本嵌入模块
- `apps/service/search_api.py` - 在线检索服务
- `apps/service/llm_client.py` - LLM客户端

### 脚本工具
- `apps/index/build_index_aws.py` - 生产索引构建器
- `scripts/sanity_check.py` - 质量验证脚本
- `scripts/build_index_incremental.py` - 增量索引构建

### 配置文件
- `conf/aws_config.py` - AWS配置
- `conf/tickers_alias.json` - 股票代码别名

### 文档
- `docs/RAG_PIPELINE_STATUS.md` - 完整系统文档
- `docs/PROJECT_STATUS.md` - 项目进度文档
- `docs/TECHNICAL_DECISIONS.md` - 技术决策记录

## 🔍 常用命令

### 质量检查
```bash
# 运行完整性检查
python scripts/sanity_check.py

# 测试召回率
python scripts/test_recall_weak.py
```

### 索引管理
```bash
# 构建新索引
python -m apps.index.build_index_aws --limit 1000

# 增量构建
python scripts/build_index_incremental.py --limit 500

# 检查FAISS索引
python scripts/check_faiss_index.py
```

### 性能测试
```bash
# 运行召回率测试
python scripts/test_recall_weak.py

# 测试新端点
python scripts/test_new_endpoints.py
```

## 🐛 故障排除

### 常见问题

1. **ModuleNotFoundError: No module named 'apps'**
   ```bash
   # 确保在项目根目录运行
   cd /Users/xyl/vscode/fin-news-mvp
   export PYTHONPATH=.
   ```

2. **AWS连接失败**
   ```bash
   # 检查AWS凭证
   aws sts get-caller-identity
   
   # 确认区域设置
   export AWS_DEFAULT_REGION=us-east-2
   ```

3. **依赖缺失**
   ```bash
   # 安装缺失依赖
   pip install pyarrow blingfire
   ```

### 调试模式
```bash
# 启用详细日志
export LOG_LEVEL=DEBUG

# 运行调试检查
python scripts/sanity_check.py --verbose
```

## 📈 监控指标

### 关键指标
- **召回率**: 目标 > 90%
- **搜索延迟**: 目标 < 50ms
- **分块质量**: 平均 380-420 tokens
- **孤儿块比例**: 目标 < 0.05

### 监控端点
- `GET /status` - 服务状态
- `POST /bench/weak_recall` - 召回率测试

## 🔄 工作流程

### 数据流水线
```
AWS Lambda → DynamoDB → S3 (raw) → 批处理构建器 → S3 (index)
```

### 检索流水线
```
用户查询 → 候选过滤 → 向量搜索 → 结果排序 → API响应
```

### AI增强流水线
```
检索结果 → 去重排序 → LLM处理 → 结构化输出 → API响应
```

## 🚀 部署指南

### 本地开发
```bash
# 启动服务
uvicorn apps.service.search_api:app --host 0.0.0.0 --port 8000

# 后台运行
nohup uvicorn apps.service.search_api:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &
```

### EC2部署
```bash
# 配置systemd服务
sudo systemctl enable finnews-api
sudo systemctl start finnews-api

# 配置Nginx反向代理
sudo ln -s /etc/nginx/sites-available/finnews-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 自动化部署
```bash
# 使用GitHub Actions自动部署
# 推送代码到main分支自动触发部署
git push origin main
```

## 📚 相关文档

- [RAG Pipeline Status](docs/RAG_PIPELINE_STATUS.md) - 完整系统文档
- [Project Status](docs/PROJECT_STATUS.md) - 项目进度和协作指南
- [Technical Decisions](docs/TECHNICAL_DECISIONS.md) - 技术决策记录
- [Incremental Build](docs/INCREMENTAL_BUILD.md) - 增量构建指南

---

**最后更新**: 2025-08-28  
**版本**: 1.0.0  
**状态**: 生产就绪 ✅
