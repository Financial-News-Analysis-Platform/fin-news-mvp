# Fin-News MVP - 金融新闻分析平台

## 项目概述

基于AWS云原生的金融新闻聚合与分析平台，集成RAG管道和LLM，生成每日股票洞察。

## 技术架构

- **后端**: FastAPI + AWS Lambda
- **数据库**: DynamoDB + S3
- **向量数据库**: FAISS (EC2 t3.micro)
- **前端**: Next.js + AWS Amplify
- **AI/ML**: Sentence Transformers + OpenAI API
- **部署**: GitHub Actions + AWS

## 项目结构

```
fin-news-mvp/
├─ apps/
│  ├─ ingest/                 # 数据采集 (A负责)
│  ├─ index/                  # 分块+向量化+表结构 (B负责)
│  ├─ retrieve/               # 检索/重排 (A负责)
│  ├─ rag/                    # RAG两条链+JSON校验 (B负责)
│  ├─ pricing/                # 价格影响 (A负责)
│  ├─ api/                    # FastAPI后端 (B负责)
│  └─ dashboard/              # 前端仪表盘 (B负责)
├─ aws/                       # AWS配置和部署
├─ data/                      # 本地数据存储
├─ conf/                      # 配置文件
└─ docs/                      # 文档和架构图
```

## 快速开始

### 1. 环境准备
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量
```bash
cp conf/.env.example conf/.env
# 编辑 .env 文件，填入必要的API密钥和配置
```

### 3. 本地开发
```bash
# 启动API服务
cd apps/api && uvicorn server:app --reload

# 启动前端
cd apps/dashboard && streamlit run app.py
```

## 部署到AWS

### 1. 使用Terraform部署基础设施
```bash
cd aws/terraform
terraform init
terraform plan
terraform apply
```

### 2. 使用SAM部署Lambda函数
```bash
cd aws/lambda
sam build
sam deploy --guided
```

## 成本控制

- **MVP阶段**: <$15/月
- **生产阶段**: <$30/月
- 详细成本分析请参考 `docs/aws-architecture.md`

## 开发计划

### Week 1: 数据 → 向量库
- [x] 项目结构搭建
- [ ] 数据采集接口
- [ ] 分块和向量化
- [ ] FAISS索引构建

### Week 2: 检索 → RAG → 故事
- [ ] 混合检索实现
- [ ] 抽取链和摘要链
- [ ] 故事组装逻辑

### Week 3: 价格 → 发布 → 评估
- [ ] 价格影响分析
- [ ] Web仪表盘
- [ ] 定时任务和评估

## 贡献指南

- A: 负责数据采集、检索、价格分析
- B: 负责处理、建库、RAG、前端

## 许可证

MIT License
