# Fin-News MVP - Financial News Analysis Platform

## Overview

A production-ready AWS-native financial news aggregation and analysis platform that integrates a RAG pipeline with LLMs to generate **daily stock insights**.  
This project features a complete RAG retrieval pipeline with real-time search capabilities.

## 🚀 Quick Start

### 1. Environment Setup
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure AWS credentials
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-2
```

### 2. Build Index
```bash
# Build production index (full build)
python -m apps.index.build_index_aws --limit 2000 --min_body_chars 400

# Incremental build (extend existing index)
python scripts/build_index_incremental.py --limit 1000 --min_body_chars 400

# Test incremental build
python scripts/test_incremental_build.py
```

### 3. Start Service
```bash
# Start FastAPI service
uvicorn apps.service.search_api:app --host 0.0.0.0 --port 8000
```

### 4. Test Search
```bash
# Test basic search
curl -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "Apple earnings", "top_k": 5}'

# Test summarization
curl -X POST "http://localhost:8000/summarize" \
  -H "Content-Type: application/json" \
  -d '{"query": "NVDA earnings", "tickers": ["NVDA"], "top_k": 5}'

# Test stock card generation
curl -X POST "http://localhost:8000/card" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "NVDA", "date": "2025-08-21", "top_k": 5}'

# Check service status
curl "http://localhost:8000/status"

# Run comprehensive tests
python scripts/test_new_endpoints.py
```

## 🔍 API Endpoints

### Core Search Endpoints

#### 1. **POST /search** - Basic Search
```json
{
  "query": "NVDA earnings",
  "tickers": ["NVDA"],
  "published_utc": "2025-08-21T10:00:00Z",
  "time_window_days": 3,
  "top_k": 5
}
```
**Response**: Ranked news chunks with similarity scores

#### 2. **POST /summarize** - AI-Powered Summarization
```json
{
  "query": "NVDA earnings",
  "tickers": ["NVDA"],
  "time_window_days": 7,
  "top_k": 8,
  "model": "gpt-4o-mini"
}
```
**Response**: Summary, bullet points, sentiment, sources, and usage metrics

#### 3. **POST /card** - Stock Information Card
```json
{
  "ticker": "NVDA",
  "date": "2025-08-21",
  "time_window_days": 3,
  "top_k": 8
}
```
**Response**: Structured card with headline, key points, numbers, risks, sentiment

#### 4. **GET /status** - Service Health Check
Returns service version, index statistics, and health status

### Index Management

#### **Full Index Build**
```bash
# Build complete index from scratch
python -m apps.index.build_index_aws --limit 2000 --min_body_chars 400
```

#### **Incremental Index Build**
```bash
# Extend existing index with new documents
python scripts/build_index_incremental.py --limit 1000 --min_body_chars 400

# Dry run to see what would be added
python scripts/build_index_incremental.py --dry-run true --limit 100

# With time window to limit scan cost
python scripts/build_index_incremental.py --window-days 7 --limit 500
```

## Architecture

### Core Components
- **Backend**: FastAPI + AWS Lambda
- **Databases**: DynamoDB + S3
- **Vector Database**: FAISS (IndexFlatIP)
- **AI/ML**: Sentence Transformers + tiktoken
- **LLM Integration**: OpenAI GPT-4o-mini with local fallback
- **Deployment**: GitHub Actions + AWS

### RAG Pipeline
- **Data Ingestion**: AWS Lambda → DynamoDB → S3
- **Text Processing**: Token-based chunking + BlingFire sentence splitting
- **Vector Generation**: Sentence transformers with normalization
- **Index Building**: Batch processing with versioned artifacts
- **Search Service**: Real-time retrieval with candidate filtering
- **LLM Processing**: AI-powered summarization and structured output generation

### Performance
- **Recall Rate**: 71% (base) → 100% (with filtering)
- **Search Latency**: 0.03-21ms
- **Vector Quality**: L2 norm = 1.0000 (perfect)
- **Chunk Quality**: 379-411 tokens average (optimal range)

## 📁 Project Structure

```
fin-news-mvp/
├─ apps/
│   ├─ index/                 # Core indexing modules ✅
│   │   ├─ __init__.py
│   │   ├─ aws_data_reader.py # AWS data reader
│   │   ├─ build_index_aws.py # Production index builder
│   │   ├─ chunk.py           # Token-based text chunking
│   │   ├─ embed.py           # Text embedding with normalization
│   │   ├─ faiss_store.py     # FAISS index management
│   │   ├─ models.py          # Data models
│   │   └─ run_index.py       # Index runner
│   └─ service/               # Online services ✅
│       ├─ llm_client.py      # OpenAI LLM client
│       └─ search_api.py      # FastAPI search service
├─ aws/                       # AWS infrastructure ✅
│   └─ lambda/
│       └─ ingest_news_v2/    # Data ingestion Lambda
│           ├─ lambda_function.py  # Main ingestion logic
│           ├─ requirements.txt    # Dependencies
│           └─ lambda_ingest_news.zip  # Deployment package
├─ conf/                      # Configurations ✅
│   ├─ aws_config.py          # AWS configuration
│   ├─ tickers_alias.json     # Stock ticker aliases
│   └─ .env.example           # Environment variables template
├─ scripts/                   # Utility scripts ✅
│   ├─ build_index_incremental.py  # Incremental index builder
│   ├─ check_faiss_index.py        # Index validation
│   ├─ sanity_check.py             # Quality validation
│   ├─ test_incremental_build.py   # Incremental build tests
│   ├─ test_new_endpoints.py       # API endpoint tests
│   └─ test_recall_weak.py         # Recall performance tests
├─ docs/                      # Documentation ✅
│   ├── README.md                    # Documentation index
│   ├── RAG_PIPELINE_STATUS.md      # Complete RAG system documentation
│   ├── PROJECT_STATUS.md            # Project progress and collaboration
│   ├── TECHNICAL_DECISIONS.md      # Technical decision records
│   └── INCREMENTAL_BUILD.md        # Incremental build guide
├─ requirements.txt           # Python dependencies ✅
├─ README.md                  # Project overview ✅
└─ QUICK_REFERENCE.md         # Quick start guide ✅
```

**Legend**: ✅ Completed | 🔄 In Progress | 📋 Planned

## 🚀 Getting Started

### 1. Setup Environment
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
```bash
cp conf/.env.example conf/.env
# Edit .env with required API keys and configs
```

### 3. Local Development
```bash
# Start API service
uvicorn apps.service.search_api:app --host 0.0.0.0 --port 8000

# Test the service
curl http://localhost:8000/status
```

## 📚 Documentation

- **[Complete RAG Pipeline Status](docs/RAG_PIPELINE_STATUS.md)** - Detailed system documentation
- **[Project Status](docs/PROJECT_STATUS.md)** - Development progress and collaboration
- **[Technical Decisions](docs/TECHNICAL_DECISIONS.md)** - Architecture decisions
- **[Quick Reference](QUICK_REFERENCE.md)** - Fast setup guide (Chinese)

## 🔧 Development

### Current Status
- ✅ **RAG Pipeline**: Complete and production-ready
- ✅ **Index Building**: AWS-integrated with versioning
- ✅ **Search Service**: FastAPI with performance optimization
- ✅ **Documentation**: Comprehensive system docs

### Next Steps
- 🔄 **AWS Deployment**: EC2 deployment with automation
- 📋 **Performance Monitoring**: Automated benchmarking
- 📋 **CI/CD Pipeline**: GitHub Actions integration

## 📄 License

MIT License

