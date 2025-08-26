# Fin-News MVP - Financial News Analysis Platform (In Progress)

## Overview

An AWS-native financial news aggregation and analysis platform that integrates a RAG pipeline with LLMs to generate **daily stock insights**.  
This project is currently **in progress**.

## Architecture

- **Backend**: FastAPI + AWS Lambda
- **Databases**: DynamoDB + S3
- **Vector Database**: FAISS (EC2 t3.micro)
- **Frontend**: Next.js + AWS Amplify
- **AI/ML**: Sentence Transformers + OpenAI API
- **Deployment**: GitHub Actions + AWS

## Project Structure

```
fin-news-mvp/
├─ apps/
│ ├─ ingest/                # Data ingestion (A)
│ ├─ index/                 # Chunking + embeddings + indexing (B)
│ ├─ retrieve/              # Retrieval / re-ranking (A)
│ ├─ rag/                   # RAG pipelines + JSON validation (B)
│ ├─ pricing/               # Price impact analysis (A)
│ ├─ api/                   # FastAPI backend (B)
│ └─ dashboard/             # Frontend dashboard (B)
├─ aws/                     # AWS infra & deployment
├─ data/                    # Local datasets
├─ conf/                    # Configurations
└─ docs/                    # Documentation & diagrams
```


## Getting Started

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
cd apps/api && uvicorn server:app --reload

# Start frontend
cd apps/dashboard && streamlit run app.py
```

## Deploying to AWS

### 1. Deploy Infrastructure with Terraform
```bash
cd aws/terraform
terraform init
terraform plan
terraform apply
```

### 2. Deploy Lambda with AWS SAM
```bash
cd aws/lambda
sam build
sam deploy --guided
```

## Cost Control

- **MVP Phase**: <$15 / month
- **Production Phase**: <$30 / month
- Detailed breakdown `docs/aws-architecture.md`

## Development Plan (In Progress)

### Week 1: Data → Vector DB
- [x] Project scaffolding
- [ ] Data ingestion API
- [ ] Chunking & embeddings
- [ ] FAISS index build

### Week 2: Retrieval → RAG → Story
- [ ] Hybrid retrieval
- [ ] Extraction & summarization chains
- [ ] Story assembly logic

### Week 3: Pricing → Dashboard → Evaluation
- [ ] Price impact analysis
- [ ] Web dashboard
- [ ] Scheduling & evaluation


## License

MIT License
