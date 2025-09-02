"""
在线检索服务 - 基于FAISS的金融新闻检索API
"""
import os
import sys
import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import numpy as np
import pandas as pd
import faiss
import boto3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from apps.index.embed import TextEmbedder
from .llm_client import llm_client

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI应用
app = FastAPI(
    title="Financial News RAG Service",
    description="Retrieval-Augmented Generation service for financial news",
    version="1.0.0"
)

# 请求/响应模型
class SearchRequest(BaseModel):
    query: str
    tickers: Optional[List[str]] = None
    published_utc: Optional[str] = None
    use_filter: bool = True
    time_window_days: int = 3
    top_k: int = 5

class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    timings: Dict[str, float]
    total_results: int

class SummarizeRequest(BaseModel):
    query: Optional[str] = None
    tickers: Optional[List[str]] = None
    published_utc: Optional[str] = None
    time_window_days: int = 3
    top_k: int = 8
    model: str = "gpt-4o-mini"

class SummarizeResponse(BaseModel):
    summary: str
    bullets: List[str]
    sentiment: str
    sources: List[Dict[str, str]]
    usage: Dict[str, float]

class CardRequest(BaseModel):
    ticker: str
    date: str  # YYYY-MM-DD
    time_window_days: int = 3
    top_k: int = 8

class CardResponse(BaseModel):
    ticker: str
    date: str
    headline: str
    key_points: List[str]
    numbers: List[Dict[str, str]]
    risks: List[str]
    sentiment: str
    sources: List[Dict[str, str]]


class SearchService:
    """搜索服务，管理FAISS索引和检索"""
    
    def __init__(self):
        """初始化搜索服务"""
        self.s3_client = None
        self.embedder = None
        self.index = None
        self.chunks_df = None
        self.row_meta = {}
        self.inv_ticker = {}
        self.inv_date = {}
        self.vecs = None
        self.config = {}
        
        # 初始化
        self._init_aws()
        self._init_embedder()
        self._load_latest_artifacts()
    
    def _init_aws(self):
        """初始化AWS客户端"""
        try:
            region = os.getenv("AWS_REGION", "us-east-2")
            self.s3_client = boto3.client('s3', region_name=region)
            logger.info(f"AWS S3 client initialized for region: {region}")
        except Exception as e:
            logger.error(f"Failed to initialize AWS client: {e}")
            raise
    
    def _init_embedder(self):
        """初始化文本嵌入器"""
        try:
            self.embedder = TextEmbedder()
            logger.info("Text embedder initialized")
        except Exception as e:
            logger.error(f"Failed to initialize text embedder: {e}")
            raise
    
    def _load_latest_artifacts(self):
        """从S3加载最新的索引文件"""
        try:
            logger.info("Loading latest artifacts from S3...")
            
            # 1. 获取latest.json指针
            latest_key = "faiss/latest.json"
            response = self.s3_client.get_object(Bucket="fin-news-raw-yz", Key=latest_key)
            latest_info = json.loads(response['Body'].read().decode('utf-8'))
            
            version = latest_info["version"]
            manifest_key = latest_info["manifest_key"]
            
            logger.info(f"Loading version: {version}")
            
            # 2. 下载manifest.json
            response = self.s3_client.get_object(Bucket="fin-news-raw-yz", Key=manifest_key)
            manifest = json.loads(response['Body'].read().decode('utf-8'))
            
            # 3. 下载FAISS索引
            index_key = manifest["index_key"]
            index_path = "/tmp/index.faiss"
            self._download_s3_file(index_key, index_path)
            
            # 4. 下载chunks元数据
            chunks_key = manifest["chunks_key"]
            if chunks_key.endswith(".parquet"):
                chunks_path = "/tmp/chunks.parquet"
                if not self._download_s3_file(chunks_key, chunks_path):
                    chunks_path = "/tmp/chunks.csv"  # Fallback path
                    csv_key = chunks_key.replace(".parquet", ".csv")
                    if not self._download_s3_file(csv_key, chunks_path):
                        raise RuntimeError("Failed to download chunks metadata")
            else:  # Assume CSV if not parquet
                chunks_path = "/tmp/chunks.csv"
                if not self._download_s3_file(chunks_key, chunks_path):
                    raise RuntimeError("Failed to download chunks metadata")
            
            # 5. 下载embeddings矩阵（如果可用）
            emb_key = manifest.get("emb_key")
            if emb_key:
                emb_path = "/tmp/embeddings.npy"
                if self._download_s3_file(emb_key, emb_path):
                    self.vecs = np.load(emb_path).astype('float32')
                    logger.info(f"Loaded embeddings matrix: {self.vecs.shape}")
            
            # 6. 加载FAISS索引
            self.index = faiss.read_index(index_path)
            logger.info(f"Loaded FAISS index: {self.index.ntotal} vectors, {self.index.d} dimensions")
            
            # 7. 加载chunks元数据
            if chunks_path.endswith(".parquet"):
                df = pd.read_parquet(chunks_path)
            else:
                df = pd.read_csv(chunks_path)
            
            self.chunks_df = df
            logger.info(f"Loaded chunks metadata: {len(df)} chunks")
            
            # 8. 构建行元数据字典
            self.row_meta = {}
            for _, row in df.iterrows():
                row_idx = int(row['row_index'])
                self.row_meta[row_idx] = {
                    'chunk_id': row['chunk_id'],
                    'doc_id': row['doc_id'],
                    'title': row['title'],
                    'tickers': eval(row['tickers']) if isinstance(row['tickers'], str) else row['tickers'],
                    'published_utc': row['published_utc'],
                    'url': row['url'],
                    'tokens': row['tokens'],
                    'chunk_index': row['chunk_index']
                }
            
            # 9. 构建倒排索引
            self._build_inverted_indices()
            
            # 10. 保存配置
            self.config = {
                "bucket": "fin-news-raw-yz",
                "region": "us-east-2",
                "latest_key": latest_key,
                "version": version,
                "dim": manifest["dim"],
                "ntotal": manifest["ntotal"]
            }
            
            logger.info(f"Successfully loaded artifacts. Index: {self.index.ntotal} vectors, {self.index.d} dimensions")
            
        except Exception as e:
            logger.error(f"Failed to load artifacts: {e}")
            raise
    
    def _download_s3_file(self, s3_key: str, local_path: str) -> bool:
        """从S3下载文件到本地"""
        try:
            self.s3_client.download_file("fin-news-raw-yz", s3_key, local_path)
            return True
        except Exception as e:
            logger.error(f"Failed to download {s3_key}: {e}")
            return False
    
    def _build_inverted_indices(self):
        """构建倒排索引"""
        # 构建ticker倒排索引
        self.inv_ticker = {}
        for row_idx, meta in self.row_meta.items():
            tickers = meta.get('tickers', [])
            for ticker in tickers:
                if ticker not in self.inv_ticker:
                    self.inv_ticker[ticker] = []
                self.inv_ticker[ticker].append(row_idx)
        
        # 构建日期倒排索引
        self.inv_date = {}
        for row_idx, meta in self.row_meta.items():
            try:
                # 解析日期
                date_str = meta.get('published_utc', '')
                if date_str:
                    date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    date_key = date_obj.strftime('%Y-%m-%d')
                    if date_key not in self.inv_date:
                        self.inv_date[date_key] = []
                    self.inv_date[date_key].append(row_idx)
            except Exception as e:
                logger.debug(f"Failed to parse date {date_str}: {e}")
        
        logger.info(f"Built inverted indices: {len(self.inv_ticker)} tickers, {len(self.inv_date)} dates")
    
    def _get_candidate_rows(self, tickers: Optional[List[str]] = None, 
                           published_utc: Optional[str] = None, 
                           time_window_days: int = 3) -> List[int]:
        """获取候选行索引"""
        candidates = set()
        
        # 1. 基于ticker过滤
        if tickers:
            for ticker in tickers:
                if ticker in self.inv_ticker:
                    candidates.update(self.inv_ticker[ticker])
        
        # 2. 基于时间窗口过滤
        if published_utc:
            try:
                query_date = datetime.fromisoformat(published_utc.replace('Z', '+00:00'))
                for i in range(-time_window_days, time_window_days + 1):
                    check_date = query_date + timedelta(days=i)
                    date_key = check_date.strftime('%Y-%m-%d')
                    if date_key in self.inv_date:
                        candidates.update(self.inv_date[date_key])
            except Exception as e:
                logger.warning(f"Failed to parse published_utc: {e}")
        
        # 3. 如果没有候选者，返回所有行
        if not candidates:
            candidates = set(range(self.index.ntotal))
        
        # 4. 限制候选者数量
        if len(candidates) > 5000:
            logger.warning(f"Too many candidates ({len(candidates)}), limiting to 5000")
            candidates = set(list(candidates)[:5000])
        
        return sorted(list(candidates))
    
    def _search_candidates(self, query_vector: np.ndarray, candidate_rows: List[int], 
                          top_k: int) -> Tuple[np.ndarray, np.ndarray]:
        """在候选行中搜索"""
        if not candidate_rows:
            return np.array([]), np.array([])
        
        # 如果embeddings矩阵可用，直接使用
        if self.vecs is not None:
            candidate_vecs = self.vecs[candidate_rows]
            
            # 创建临时FAISS索引
            temp_index = faiss.IndexFlatIP(self.vecs.shape[1])
            temp_index.add(candidate_vecs)
            
            # 搜索
            distances, indices = temp_index.search(query_vector, min(top_k, len(candidate_rows)))
            
            # 映射回原始行索引
            original_indices = [candidate_rows[i] for i in indices[0]]
            return distances, np.array([original_indices])
        
        else:
            # 备用方案：从主索引中提取候选向量
            candidate_vecs = self.index.reconstruct_n(0, candidate_rows)
            temp_index = faiss.IndexFlatIP(self.index.d)
            temp_index.add(candidate_vecs)
            
            distances, indices = temp_index.search(query_vector, min(top_k, len(candidate_rows)))
            original_indices = [candidate_rows[i] for i in indices[0]]
            return distances, np.array([original_indices])
    
    def search(self, query: str, tickers: Optional[List[str]] = None,
               published_utc: Optional[str] = None, use_filter: bool = True,
               time_window_days: int = 3, top_k: int = 5) -> Dict[str, Any]:
        """执行搜索"""
        start_time = time.time()
        
        # 1. 嵌入查询
        embed_start = time.time()
        query_vector = self.embedder.encode([query], normalize=True)
        embed_ms = (time.time() - embed_start) * 1000
        
        # 2. 候选过滤
        filter_start = time.time()
        if use_filter:
            candidate_rows = self._get_candidate_rows(tickers, published_utc, time_window_days)
        else:
            candidate_rows = list(range(self.index.ntotal))
        filter_ms = (time.time() - filter_start) * 1000
        
        # 3. 向量搜索
        search_start = time.time()
        if candidate_rows:
            distances, indices = self._search_candidates(query_vector, candidate_rows, top_k)
        else:
            distances, indices = np.array([]), np.array([])
        search_ms = (time.time() - search_start) * 1000
        
        # 4. 格式化结果
        results = []
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < len(self.row_meta):
                meta = self.row_meta[idx]
                results.append({
                    "score": float(dist),
                    "chunk_id": meta['chunk_id'],
                    "doc_id": meta['doc_id'],
                    "title": meta['title'],
                    "url": meta['url'],
                    "tickers": meta['tickers'],
                    "published_utc": meta['published_utc'],
                    "snippet": meta.get('text_snippet', '')[:200] + "..." if len(meta.get('text_snippet', '')) > 200 else meta.get('text_snippet', '')
                })
        
        total_ms = (time.time() - start_time) * 1000
        
        return {
            "results": results,
            "timings": {
                "embed_ms": embed_ms,
                "filter_ms": filter_ms,
                "search_ms": search_ms,
                "total_ms": total_ms
            },
            "total_results": len(results)
        }
    
    def summarize(self, query: Optional[str] = None, tickers: Optional[List[str]] = None,
                  published_utc: Optional[str] = None, time_window_days: int = 3,
                  top_k: int = 8, model: str = "gpt-4o-mini") -> Dict[str, Any]:
        """生成摘要"""
        start_time = time.time()
        
        # 1. 执行检索
        search_result = self.search(
            query=query or "financial news",
            tickers=tickers,
            published_utc=published_utc,
            use_filter=True,
            time_window_days=time_window_days,
            top_k=top_k
        )
        
        # 2. 去重（基于URL）
        seen_urls = set()
        unique_results = []
        for result in search_result["results"]:
            url = result.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        # 3. 按发布时间排序，然后按分数排序
        def sort_key(result):
            try:
                date = datetime.fromisoformat(result.get("published_utc", "").replace('Z', '+00:00'))
                return (date, result.get("score", 0))
            except:
                return (datetime.min, result.get("score", 0))
        
        unique_results.sort(key=sort_key, reverse=True)
        
        # 4. 限制到top_k
        selected_results = unique_results[:top_k]
        
        # 5. 准备上下文项目
        context_items = []
        for result in selected_results:
            # 获取完整的chunk文本（这里需要从原始数据中获取）
            chunk_text = result.get("snippet", "")
            
            context_items.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "published_utc": result.get("published_utc", ""),
                "text_snippet": chunk_text
            })
        
        # 6. 构建指令
        if query:
            instruction = f"analyze the following news articles related to: {query}"
        elif tickers:
            instruction = f"analyze the following news articles about {', '.join(tickers)}"
        else:
            instruction = "analyze the following financial news articles"
        
        # 7. 调用LLM生成摘要
        llm_start = time.time()
        summary_result = llm_client.summarize(context_items, instruction, model)
        llm_ms = (time.time() - llm_start) * 1000
        
        # 8. 计算总时间
        total_ms = (time.time() - start_time) * 1000
        
        return {
            "summary": summary_result.get("summary", ""),
            "bullets": summary_result.get("bullets", []),
            "sentiment": summary_result.get("sentiment", "neu"),
            "sources": summary_result.get("sources", []),
            "usage": {
                "embed_ms": search_result["timings"]["embed_ms"],
                "filter_ms": search_result["timings"]["filter_ms"],
                "search_ms": search_result["timings"]["search_ms"],
                "llm_ms": llm_ms,
                "total_ms": total_ms
            }
        }
    
    def generate_card(self, ticker: str, date: str, time_window_days: int = 3, top_k: int = 8) -> Dict[str, Any]:
        """生成股票卡片"""
        start_time = time.time()
        
        # 1. 构建查询
        query = f"{ticker} stock news"
        
        # 2. 执行检索
        search_result = self.search(
            query=query,
            tickers=[ticker],
            published_utc=f"{date}T00:00:00Z",
            use_filter=True,
            time_window_days=time_window_days,
            top_k=top_k
        )
        
        # 3. 去重和排序
        seen_urls = set()
        unique_results = []
        for result in search_result["results"]:
            url = result.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        # 按发布时间排序
        def sort_key(result):
            try:
                date = datetime.fromisoformat(result.get("published_utc", "").replace('Z', '+00:00'))
                return date
            except:
                return datetime.min
        
        unique_results.sort(key=sort_key, reverse=True)
        selected_results = unique_results[:top_k]
        
        # 4. 准备上下文
        context_items = []
        for result in selected_results:
            chunk_text = result.get("snippet", "")
            context_items.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "published_utc": result.get("published_utc", ""),
                "text_snippet": chunk_text
            })
        
        # 5. 生成卡片内容
        instruction = f"create a financial summary card for {ticker} stock based on recent news"
        card_result = llm_client.summarize(context_items, instruction, "gpt-4o-mini")
        
        # 6. 构建结构化卡片
        headline = card_result.get("summary", f"Latest news for {ticker}")
        key_points = card_result.get("bullets", [])
        
        # 提取数字信息（简单的启发式方法）
        numbers = []
        for point in key_points:
            if any(char.isdigit() for char in point):
                # 简单的数字提取
                import re
                money_matches = re.findall(r'\$[\d,]+\.?\d*[MBK]?', point)
                for match in money_matches:
                    numbers.append({
                        "metric": "Financial Figure",
                        "value": match,
                        "period": "Recent"
                    })
        
        # 提取风险信息
        risks = []
        risk_keywords = ["risk", "concern", "challenge", "threat", "volatility", "uncertainty"]
        for point in key_points:
            if any(keyword in point.lower() for keyword in risk_keywords):
                risks.append(point)
        
        # 如果没有风险，添加默认项
        if not risks:
            risks = ["Market conditions remain uncertain"]
        
        # 7. 构建响应
        sources = card_result.get("sources", [])
        
        return {
            "ticker": ticker,
            "date": date,
            "headline": headline,
            "key_points": key_points,
            "numbers": numbers,
            "risks": risks,
            "sentiment": card_result.get("sentiment", "neu"),
            "sources": sources
        }


# 全局搜索服务实例
search_service = SearchService()


# API端点
@app.post("/search", response_model=SearchResponse)
async def search_endpoint(request: SearchRequest):
    """搜索端点"""
    try:
        result = search_service.search(
            query=request.query,
            tickers=request.tickers,
            published_utc=request.published_utc,
            use_filter=request.use_filter,
            time_window_days=request.time_window_days,
            top_k=request.top_k
        )
        return SearchResponse(**result)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summarize", response_model=SummarizeResponse)
async def summarize_endpoint(request: SummarizeRequest):
    """摘要端点"""
    try:
        result = search_service.summarize(
            query=request.query,
            tickers=request.tickers,
            published_utc=request.published_utc,
            time_window_days=request.time_window_days,
            top_k=request.top_k,
            model=request.model
        )
        return SummarizeResponse(**result)
    except Exception as e:
        logger.error(f"Summarize failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/card", response_model=CardResponse)
async def card_endpoint(request: CardRequest):
    """股票卡片端点"""
    try:
        result = search_service.generate_card(
            ticker=request.ticker,
            date=request.date,
            time_window_days=request.time_window_days,
            top_k=request.top_k
        )
        return CardResponse(**result)
    except Exception as e:
        logger.error(f"Card generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
async def get_status():
    """状态端点"""
    try:
        return {
            "version": search_service.config.get("version", "unknown"),
            "ntotal": search_service.config.get("ntotal", 0),
            "dim": search_service.config.get("dim", 0),
            "has_embeddings": search_service.vecs is not None,
            "status": "healthy"
        }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/bench/weak_recall")
async def run_weak_recall_benchmark():
    """运行弱召回基准测试"""
    try:
        # 这里可以实现弱召回基准测试
        # 暂时返回简单的状态信息
        return {
            "message": "Weak recall benchmark endpoint ready",
            "status": "implemented"
        }
    except Exception as e:
        logger.error(f"Weak recall benchmark failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 