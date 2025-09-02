#!/usr/bin/env python3
"""
增量索引构建脚本 - 扩展现有的S3 FAISS索引
"""
import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import numpy as np
import pandas as pd
import faiss
import boto3
from botocore.exceptions import ClientError

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from apps.index.chunk import TextChunker, clean_body
from apps.index.embed import TextEmbedder

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class IncrementalIndexBuilder:
    """增量索引构建器"""
    
    def __init__(self, region: str = "us-east-2", bucket: str = "fin-news-raw-yz", 
                 table: str = "news_documents", prefix: str = "polygon/"):
        """
        初始化增量索引构建器
        
        Args:
            region: AWS区域
            bucket: S3存储桶名称
            table: DynamoDB表名
            prefix: S3前缀
        """
        self.region = region
        self.bucket = bucket
        self.table = table
        self.prefix = prefix
        
        # 初始化AWS客户端
        self.s3_client = boto3.client('s3', region_name=region)
        self.ddb_client = boto3.client('dynamodb', region_name=region)
        self.ddb_resource = boto3.resource('dynamodb', region_name=region)
        
        # 初始化处理组件
        self.chunker = TextChunker(
            target_tokens=360,
            max_tokens=460,
            overlap_tokens=40,
            min_tokens=200,
            use_blingfire=True
        )
        self.embedder = TextEmbedder()
        
        logger.info(f"Initialized IncrementalIndexBuilder for {bucket}/{table} in {region}")
    
    def _download_s3_file(self, s3_key: str, local_path: str) -> bool:
        """从S3下载文件到本地"""
        try:
            self.s3_client.download_file(self.bucket, s3_key, local_path)
            return True
        except ClientError as e:
            logger.error(f"Failed to download s3://{self.bucket}/{s3_key}: {e}")
            return False
    
    def _upload_s3_file(self, local_path: str, s3_key: str) -> bool:
        """上传本地文件到S3"""
        try:
            self.s3_client.upload_file(local_path, self.bucket, s3_key)
            return True
        except ClientError as e:
            logger.error(f"Failed to upload {local_path} to s3://{self.bucket}/{s3_key}: {e}")
            return False
    
    def _get_latest_version(self) -> Tuple[str, Dict[str, Any]]:
        """获取最新版本和清单信息"""
        logger.info("Fetching latest version information...")
        
        # 下载latest.json
        latest_key = "faiss/latest.json"
        latest_path = "/tmp/latest.json"
        if not self._download_s3_file(latest_key, latest_path):
            raise RuntimeError(f"Failed to download {latest_key}")
        
        with open(latest_path, 'r') as f:
            latest_info = json.load(f)
        
        version = latest_info["version"]
        manifest_key = latest_info["manifest_key"]
        
        # 下载manifest.json
        manifest_path = "/tmp/manifest.json"
        if not self._download_s3_file(manifest_key, manifest_path):
            raise RuntimeError(f"Failed to download {manifest_key}")
        
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        logger.info(f"Current version: {version}")
        logger.info(f"Current index: {manifest['ntotal']} vectors, {manifest['dim']} dimensions")
        
        return version, manifest
    
    def _get_since_timestamp(self, manifest: Dict[str, Any]) -> str:
        """从现有chunks元数据中确定since_ts"""
        logger.info("Determining since timestamp from existing chunks...")
        
        # 下载chunks元数据
        chunks_key = manifest["chunks_key"]
        if chunks_key.endswith(".parquet"):
            chunks_path = "/tmp/chunks.parquet"
            if not self._download_s3_file(chunks_key, chunks_path):
                # 尝试CSV fallback
                chunks_path = "/tmp/chunks.csv"
                csv_key = chunks_key.replace(".parquet", ".csv")
                if not self._download_s3_file(csv_key, chunks_path):
                    raise RuntimeError("Failed to download chunks metadata")
        else:
            chunks_path = "/tmp/chunks.csv"
            if not self._download_s3_file(chunks_key, chunks_path):
                raise RuntimeError("Failed to download chunks metadata")
        
        # 加载chunks数据
        if chunks_path.endswith(".parquet"):
            df = pd.read_parquet(chunks_path)
        else:
            df = pd.read_csv(chunks_path)
        
        # 找到最新的时间戳
        timestamps = []
        
        if 'published_utc' in df.columns:
            published_vals = df['published_utc'].dropna()
            if len(published_vals) > 0:
                # 转换为字符串并过滤有效值
                for val in published_vals:
                    if val and str(val) != 'nan':
                        timestamps.append(str(val))
        
        if 'fetched_at' in df.columns:
            fetched_vals = df['fetched_at'].dropna()
            if len(fetched_vals) > 0:
                # 转换为字符串并过滤有效值
                for val in fetched_vals:
                    if val and str(val) != 'nan':
                        timestamps.append(str(val))
        
        if not timestamps:
            # 如果没有时间戳，使用当前时间减去1天
            since_ts = (datetime.now() - timedelta(days=1)).isoformat() + "Z"
            logger.warning(f"No timestamps found, using {since_ts}")
        else:
            # 过滤掉无效的时间戳格式
            valid_timestamps = []
            for ts in timestamps:
                try:
                    # 尝试解析时间戳以验证格式
                    datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    valid_timestamps.append(ts)
                except:
                    continue
            
            if valid_timestamps:
                since_ts = max(valid_timestamps)
                logger.info(f"Found since timestamp: {since_ts}")
            else:
                since_ts = (datetime.now() - timedelta(days=1)).isoformat() + "Z"
                logger.warning(f"No valid timestamps found, using {since_ts}")
        
        return since_ts
    
    def _fetch_new_documents(self, since_ts: str, limit: int, window_days: Optional[int] = None) -> List[Dict[str, Any]]:
        """从DynamoDB获取新文档"""
        logger.info(f"Fetching new documents since {since_ts}...")
        
        # 计算时间窗口
        if window_days:
            since_date = datetime.fromisoformat(since_ts.replace('Z', '+00:00'))
            window_start = since_date - timedelta(days=window_days)
            window_start_str = window_start.isoformat().replace('+00:00', 'Z')
            logger.info(f"Using time window: {window_start_str} to {since_ts}")
        else:
            window_start_str = since_ts
        
        # 构建扫描参数
        scan_kwargs = {
            "TableName": self.table,
            "Limit": min(100, limit),
            "ProjectionExpression": "doc_id, title, body, #src, published_utc, fetched_at, query_ticker, matched_tickers, tickers, link_strength, summary, #url, s3_key",
            "ExpressionAttributeNames": {
                "#src": "source",
                "#url": "url"
            }
        }
        
        # 添加时间过滤条件
        filter_expression = "(published_utc > :since_ts OR fetched_at > :since_ts)"
        if window_days:
            filter_expression += " AND (published_utc > :window_start OR fetched_at > :window_start)"
        
        scan_kwargs["FilterExpression"] = filter_expression
        scan_kwargs["ExpressionAttributeValues"] = {
            ":since_ts": {"S": since_ts}
        }
        if window_days:
            scan_kwargs["ExpressionAttributeValues"][":window_start"] = {"S": window_start_str}
        
        # 执行扫描
        docs = []
        scanned = 0
        last_evaluated_key = None
        
        while len(docs) < limit and scanned < limit * 2:  # 防止无限循环
            if last_evaluated_key:
                scan_kwargs["ExclusiveStartKey"] = last_evaluated_key
            
            try:
                response = self.ddb_client.scan(**scan_kwargs)
                items = response.get('Items', [])
                scanned += len(items)
                
                for item in items:
                    if len(docs) >= limit:
                        break
                    
                    # 提取字段
                    doc_id = item.get("doc_id", {}).get("S", "")
                    title = item.get("title", {}).get("S", "")
                    body = item.get("body", {}).get("S", "")
                    source = item.get("#src", {}).get("S", "")
                    published_utc = item.get("published_utc", {}).get("S", "")
                    fetched_at = item.get("fetched_at", {}).get("S", "")
                    url = item.get("#url", {}).get("S", "")
                    s3_key = item.get("s3_key", {}).get("S", "")
                    
                    # 处理tickers字段
                    tickers = []
                    for ticker_field in ["tickers", "matched_tickers", "query_ticker"]:
                        if ticker_field in item:
                            ticker_data = item[ticker_field]
                            if "SS" in ticker_data:  # String Set
                                tickers.extend(ticker_data["SS"])
                            elif "S" in ticker_data:  # Single String
                                tickers.append(ticker_data["S"])
                    
                    # 跳过空文档
                    if not title and not body:
                        continue
                    
                    docs.append({
                        "doc_id": doc_id,
                        "title": title,
                        "body": body,
                        "source": source,
                        "published_utc": published_utc,
                        "fetched_at": fetched_at,
                        "url": url,
                        "s3_key": s3_key,
                        "tickers": list(set(tickers))  # 去重
                    })
                
                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break
                    
            except ClientError as e:
                logger.error(f"DynamoDB scan failed: {e}")
                break
        
        logger.info(f"Scanned {scanned} items, found {len(docs)} new documents")
        return docs
    
    def _fetch_body_from_s3(self, s3_key: str) -> Optional[str]:
        """从S3获取文档正文"""
        try:
            # 处理相对路径
            if not s3_key.startswith("s3://") and not s3_key.startswith(self.prefix):
                full_key = f"{self.prefix}{s3_key}"
            else:
                full_key = s3_key
            
            response = self.s3_client.get_object(Bucket=self.bucket, Key=full_key)
            content = response['Body'].read().decode('utf-8')
            return content
        except ClientError as e:
            logger.warning(f"Failed to fetch body from S3 {s3_key}: {e}")
            return None
    
    def _process_new_documents(self, docs: List[Dict[str, Any]], min_body_chars: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """处理新文档：清理、分块、准备元数据"""
        logger.info("Processing new documents...")
        
        processed_docs = []
        all_chunks = []
        
        for doc in docs:
            # 选择正文内容
            body = doc.get("body", "")
            if len(body) < min_body_chars and doc.get("s3_key"):
                # 从S3获取正文
                s3_body = self._fetch_body_from_s3(doc["s3_key"])
                if s3_body and len(s3_body) >= min_body_chars:
                    body = s3_body
            
            if len(body) < min_body_chars:
                logger.debug(f"Skipping doc {doc['doc_id']}: body too short ({len(body)} chars)")
                continue
            
            # 清理正文
            try:
                body = clean_body(body)
            except:
                # 简单的fallback清理器
                lines = [line.strip() for line in body.splitlines() if line.strip()]
                body = "\n".join(lines)
            
            # 分块
            try:
                chunks = self.chunker.split_text(body, doc["doc_id"], doc["title"])
            except Exception as e:
                logger.warning(f"Failed to chunk doc {doc['doc_id']}: {e}")
                continue
            
            # 准备chunk元数据
            for chunk in chunks:
                chunk_meta = {
                    "chunk_id": chunk.id,
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "source": doc["source"],
                    "url": doc["url"],
                    "published_utc": doc["published_utc"],
                    "fetched_at": doc["fetched_at"],
                    "tickers": doc["tickers"],
                    "tokens": chunk.tokens,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text
                }
                all_chunks.append(chunk_meta)
            
            processed_docs.append(doc)
        
        logger.info(f"Processed {len(processed_docs)} documents into {len(all_chunks)} chunks")
        return processed_docs, all_chunks
    
    def _embed_new_chunks(self, chunks: List[Dict[str, Any]]) -> np.ndarray:
        """嵌入新chunks"""
        if not chunks:
            return np.array([])
        
        logger.info(f"Embedding {len(chunks)} new chunks...")
        
        # 准备文本
        texts = [chunk["text"] for chunk in chunks]
        
        # 嵌入
        start_time = time.time()
        embeddings = self.embedder.encode(texts, normalize=True)
        embed_time = time.time() - start_time
        
        throughput = len(chunks) / embed_time if embed_time > 0 else 0
        logger.info(f"Embedded {len(chunks)} chunks in {embed_time:.2f}s ({throughput:.1f} chunks/s)")
        
        return embeddings
    
    def _merge_with_existing(self, manifest: Dict[str, Any], new_chunks: List[Dict[str, Any]], 
                           new_embeddings: np.ndarray) -> Tuple[np.ndarray, pd.DataFrame, int]:
        """与现有索引合并"""
        logger.info("Merging with existing index...")
        
        # 加载现有embeddings
        emb_key = manifest["emb_key"]
        emb_path = "/tmp/existing_embeddings.npy"
        if not self._download_s3_file(emb_key, emb_path):
            raise RuntimeError("Failed to download existing embeddings")
        
        existing_embeddings = np.load(emb_path).astype('float32')
        logger.info(f"Loaded existing embeddings: {existing_embeddings.shape}")
        
        # 合并embeddings
        if new_embeddings.size > 0:
            merged_embeddings = np.vstack([existing_embeddings, new_embeddings])
        else:
            merged_embeddings = existing_embeddings
        
        logger.info(f"Merged embeddings: {merged_embeddings.shape}")
        
        # 加载现有chunks元数据
        chunks_key = manifest["chunks_key"]
        if chunks_key.endswith(".parquet"):
            chunks_path = "/tmp/existing_chunks.parquet"
            if not self._download_s3_file(chunks_key, chunks_path):
                chunks_path = "/tmp/existing_chunks.csv"
                csv_key = chunks_key.replace(".parquet", ".csv")
                if not self._download_s3_file(csv_key, chunks_path):
                    raise RuntimeError("Failed to download existing chunks")
        else:
            chunks_path = "/tmp/existing_chunks.csv"
            if not self._download_s3_file(chunks_key, chunks_path):
                raise RuntimeError("Failed to download existing chunks")
        
        if chunks_path.endswith(".parquet"):
            existing_df = pd.read_parquet(chunks_path)
        else:
            existing_df = pd.read_csv(chunks_path)
        
        logger.info(f"Loaded existing chunks: {len(existing_df)} rows")
        
        # 为新chunks分配row_index
        last_row_index = existing_df['row_index'].max() if len(existing_df) > 0 else -1
        for i, chunk in enumerate(new_chunks):
            chunk['row_index'] = last_row_index + 1 + i
        
        # 合并chunks元数据
        new_df = pd.DataFrame(new_chunks)
        merged_df = pd.concat([existing_df, new_df], ignore_index=True)
        
        # 确保确定性排序
        merged_df = merged_df.sort_values(['doc_id', 'chunk_index']).reset_index(drop=True)
        
        logger.info(f"Merged chunks: {len(merged_df)} total rows")
        
        return merged_embeddings, merged_df, len(existing_df)
    
    def _build_new_index(self, embeddings: np.ndarray) -> faiss.Index:
        """构建新的FAISS索引"""
        logger.info("Building new FAISS index...")
        
        # 创建新的IndexFlatIP
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings.astype('float32'))
        
        logger.info(f"Built new index: {index.ntotal} vectors, {index.d} dimensions")
        return index
    
    def _write_new_artifacts(self, version: str, index: faiss.Index, 
                           chunks_df: pd.DataFrame, embeddings: np.ndarray) -> Dict[str, Any]:
        """写入新的版本化文件"""
        logger.info(f"Writing new artifacts for version {version}...")
        
        # 创建本地目录
        local_dir = Path(f".artifacts/faiss/{version}")
        local_dir.mkdir(parents=True, exist_ok=True)
        
        # 写入FAISS索引
        index_path = local_dir / "index.faiss"
        faiss.write_index(index, str(index_path))
        
        # 写入embeddings
        emb_path = local_dir / "embeddings.npy"
        np.save(emb_path, embeddings.astype('float32'))
        
        # 写入chunks元数据
        chunks_path = local_dir / "chunks.parquet"
        try:
            chunks_df.to_parquet(chunks_path, index=False)
            chunks_key = f"faiss/{version}/chunks.parquet"
        except Exception as e:
            logger.warning(f"Failed to write parquet, falling back to CSV: {e}")
            chunks_path = local_dir / "chunks.csv"
            chunks_df.to_csv(chunks_path, index=False)
            chunks_key = f"faiss/{version}/chunks.csv"
        
        # 写入manifest
        manifest = {
            "version": version,
            "created_at_utc": datetime.now().isoformat() + "Z",
            "bucket": self.bucket,
            "region": self.region,
            "index_key": f"faiss/{version}/index.faiss",
            "chunks_key": chunks_key,
            "emb_key": f"faiss/{version}/embeddings.npy",
            "ntotal": index.ntotal,
            "dim": index.d
        }
        
        manifest_path = local_dir / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"Written artifacts to {local_dir}")
        return manifest
    
    def _upload_new_artifacts(self, version: str, manifest: Dict[str, Any]) -> bool:
        """上传新文件到S3"""
        logger.info(f"Uploading new artifacts for version {version}...")
        
        local_dir = Path(f".artifacts/faiss/{version}")
        
        # 上传所有文件
        files_to_upload = [
            ("index.faiss", manifest["index_key"]),
            ("chunks.parquet", manifest["chunks_key"]),
            ("embeddings.npy", manifest["emb_key"]),
            ("manifest.json", f"faiss/{version}/manifest.json")
        ]
        
        # 如果parquet失败，尝试CSV
        if not (local_dir / "chunks.parquet").exists():
            files_to_upload[1] = ("chunks.csv", manifest["chunks_key"])
        
        for local_file, s3_key in files_to_upload:
            local_path = local_dir / local_file
            if local_path.exists():
                if not self._upload_s3_file(str(local_path), s3_key):
                    return False
            else:
                logger.warning(f"Local file {local_path} does not exist")
        
        # 更新latest.json
        latest_info = {
            "version": version,
            "manifest_key": f"faiss/{version}/manifest.json",
            "updated_at_utc": datetime.now().isoformat() + "Z"
        }
        
        latest_path = "/tmp/latest.json"
        with open(latest_path, 'w') as f:
            json.dump(latest_info, f, indent=2)
        
        if not self._upload_s3_file(latest_path, "faiss/latest.json"):
            return False
        
        logger.info("Successfully uploaded all artifacts")
        return True
    
    def build_incremental(self, limit: int = 2000, window_days: Optional[int] = None, 
                         min_body_chars: int = 400, dry_run: bool = False) -> bool:
        """执行增量构建"""
        start_time = time.time()
        
        try:
            # 1. 获取当前版本信息
            current_version, manifest = self._get_latest_version()
            old_ntotal = manifest["ntotal"]
            
            # 2. 确定since时间戳
            since_ts = self._get_since_timestamp(manifest)
            
            # 3. 获取新文档
            new_docs = self._fetch_new_documents(since_ts, limit, window_days)
            
            if not new_docs:
                logger.info("No new documents found")
                return True
            
            # 4. 处理新文档
            processed_docs, new_chunks = self._process_new_documents(new_docs, min_body_chars)
            
            if not new_chunks:
                logger.info("No new chunks created")
                return True
            
            # 5. 嵌入新chunks
            new_embeddings = self._embed_new_chunks(new_chunks)
            
            # 6. 合并现有索引
            merged_embeddings, merged_chunks_df, old_chunk_count = self._merge_with_existing(
                manifest, new_chunks, new_embeddings
            )
            
            # 7. 构建新索引
            new_index = self._build_new_index(merged_embeddings)
            
            # 8. 生成新版本号
            new_version = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if dry_run:
                logger.info("DRY RUN - Would create new version:")
                logger.info(f"  Version: {new_version}")
                logger.info(f"  Old total: {old_ntotal}")
                logger.info(f"  New added: {len(new_chunks)}")
                logger.info(f"  New total: {new_index.ntotal}")
                return True
            
            # 9. 写入新文件
            new_manifest = self._write_new_artifacts(new_version, new_index, merged_chunks_df, merged_embeddings)
            
            # 10. 上传到S3
            if not self._upload_new_artifacts(new_version, new_manifest):
                return False
            
            # 11. 输出统计信息
            total_time = time.time() - start_time
            logger.info("=" * 60)
            logger.info("INCREMENTAL BUILD COMPLETED SUCCESSFULLY")
            logger.info(f"Version: {new_version}")
            logger.info(f"Old total: {old_ntotal}")
            logger.info(f"New added: {len(new_chunks)}")
            logger.info(f"New total: {new_index.ntotal}")
            logger.info(f"Total time: {total_time:.2f}s")
            logger.info(f"S3 keys:")
            logger.info(f"  Index: s3://{self.bucket}/{new_manifest['index_key']}")
            logger.info(f"  Chunks: s3://{self.bucket}/{new_manifest['chunks_key']}")
            logger.info(f"  Embeddings: s3://{self.bucket}/{new_manifest['emb_key']}")
            logger.info(f"  Manifest: s3://{self.bucket}/faiss/{new_version}/manifest.json")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"Incremental build failed: {e}")
            return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Incremental FAISS index builder")
    parser.add_argument("--dry-run", type=str, default="false", 
                       help="Dry run mode (true/false)")
    parser.add_argument("--limit", type=int, default=2000,
                       help="Maximum new documents to process")
    parser.add_argument("--region", type=str, default="us-east-2",
                       help="AWS region")
    parser.add_argument("--bucket", type=str, default="fin-news-raw-yz",
                       help="S3 bucket name")
    parser.add_argument("--table", type=str, default="news_documents",
                       help="DynamoDB table name")
    parser.add_argument("--prefix", type=str, default="polygon/",
                       help="S3 prefix for raw data")
    parser.add_argument("--window-days", type=int, default=None,
                       help="Time window in days to limit scan cost")
    parser.add_argument("--min-body-chars", type=int, default=400,
                       help="Minimum body length in characters")
    
    args = parser.parse_args()
    
    # 解析dry-run参数
    dry_run = args.dry_run.lower() in ['true', '1', 'yes', 'y']
    
    # 创建构建器
    builder = IncrementalIndexBuilder(
        region=args.region,
        bucket=args.bucket,
        table=args.table,
        prefix=args.prefix
    )
    
    # 执行增量构建
    success = builder.build_incremental(
        limit=args.limit,
        window_days=args.window_days,
        min_body_chars=args.min_body_chars,
        dry_run=dry_run
    )
    
    if success:
        logger.info("Incremental build completed successfully")
        return 0
    else:
        logger.error("Incremental build failed")
        return 1


if __name__ == "__main__":
    exit(main())
