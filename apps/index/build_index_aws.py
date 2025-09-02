#!/usr/bin/env python3
"""
Production-ready batch builder for constructing and publishing vector index to AWS S3

Usage:
    python scripts/build_index_aws.py --limit 1000 --min_body_chars 400
"""

import os
import sys
import json
import time
import hashlib
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import boto3
import numpy as np
import faiss
from botocore.exceptions import ClientError, NoCredentialsError

# Import existing modules
from apps.index.chunk import TextChunker, clean_body
from apps.index.embed import TextEmbedder

# Fallback clean_body if import fails
try:
    from apps.index.chunk import clean_body
    CLEAN_BODY_AVAILABLE = True
except ImportError:
    CLEAN_BODY_AVAILABLE = False
    
    def clean_body(text: str) -> str:
        """Fallback text cleaner for boilerplate removal"""
        if not text:
            return ""
        
        # Simple boilerplate patterns
        boilerplate_patterns = [
            "subscribe", "sign up", "newsletter", "cookie", "privacy policy",
            "terms of service", "contact us", "advertisement", "sponsored",
            "click here", "read more", "continue reading", "share this",
            "follow us", "copyright", "all rights reserved"
        ]
        
        lines = text.splitlines()
        cleaned_lines = []
        
        for line in lines:
            line_lower = line.lower().strip()
            is_boilerplate = any(pattern in line_lower for pattern in boilerplate_patterns)
            if not is_boilerplate and line.strip():
                cleaned_lines.append(line)
        
        return "\n".join(cleaned_lines)


class IndexBuilder:
    """Production index builder for AWS deployment"""
    
    def __init__(self, 
                 region: str = "us-east-2",
                 bucket: str = "fin-news-raw-yz",
                 table: str = "news_documents",
                 s3_prefix: str = "polygon/",
                 use_blingfire: bool = True):
        
        self.region = region
        self.bucket = bucket
        self.table = table
        self.s3_prefix = s3_prefix
        self.use_blingfire = use_blingfire
        
        # Initialize AWS clients
        self.ddb = boto3.resource("dynamodb", region_name=region)
        self.s3 = boto3.client("s3", region_name=region)
        
        # Initialize components
        self.chunker = TextChunker(
            target_tokens=360,
            max_tokens=460,
            overlap_tokens=40,
            min_tokens=200,
            use_blingfire=use_blingfire
        )
        
        self.embedder = TextEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
        
        # Cache for embeddings (avoid recomputing in same run)
        self.embedding_cache = {}
        
    def _get_cached_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get cached embedding if available"""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return self.embedding_cache.get(text_hash)
    
    def _cache_embedding(self, text: str, embedding: np.ndarray):
        """Cache embedding for potential reuse"""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        self.embedding_cache[text_hash] = embedding
    
    def _fetch_body_from_s3(self, s3_key: str) -> str:
        """Fetch body content from S3"""
        try:
            # Handle full S3 URLs vs relative keys
            if s3_key.startswith("s3://"):
                # Full S3 URL - extract bucket and key
                parts = s3_key.replace("s3://", "").split("/", 1)
                if len(parts) == 2:
                    bucket_name, key = parts
                    if bucket_name != self.bucket:
                        print(f"[WARN] S3 key bucket mismatch: {bucket_name} vs {self.bucket}")
                        return ""
                else:
                    return ""
            else:
                # Relative key - use configured bucket
                bucket_name = self.bucket
                key = s3_key
            
            response = self.s3.get_object(Bucket=bucket_name, Key=key)
            body = response["Body"].read().decode("utf-8", errors="ignore")
            return body
            
        except ClientError as e:
            print(f"[ERROR] Failed to fetch S3 body from {s3_key}: {e}")
            return ""
        except Exception as e:
            print(f"[ERROR] Unexpected error fetching S3 body: {e}")
            return ""
    
    def _load_documents_from_dynamodb(self, limit: int, min_body_chars: int) -> List[Dict[str, Any]]:
        """Load documents from DynamoDB with pagination"""
        print(f"[LOAD] Scanning DynamoDB table '{self.table}' in region '{self.region}'...")
        
        table = self.ddb.Table(self.table)
        docs = []
        last_key = None
        scanned = 0
        
        while len(docs) < limit:
            scan_kwargs = {
                "Limit": min(100, limit - len(docs)),  # DynamoDB scan limit
                "ProjectionExpression": "doc_id, title, body, #src, published_utc, fetched_at, query_ticker, matched_tickers, tickers, link_strength, summary, #url, s3_key",
                "ExpressionAttributeNames": {
                    "#src": "source",  # Alias for reserved keyword
                    "#url": "url"      # Alias for reserved keyword
                }
            }
            
            if last_key:
                scan_kwargs["ExclusiveStartKey"] = last_key
            
            try:
                response = table.scan(**scan_kwargs)
                items = response.get("Items", [])
                scanned += len(items)
                
                for item in items:
                    if len(docs) >= limit:
                        break
                    
                    # Extract fields exactly as specified
                    doc_id = item.get("doc_id", "")
                    title = item.get("title", "")
                    body = item.get("body", "")
                    source = item.get("#src", "")  # Use alias for reserved keyword
                    published_utc = item.get("published_utc", "")
                    fetched_at = item.get("fetched_at", "")
                    query_ticker = item.get("query_ticker", "")
                    matched_tickers = item.get("matched_tickers", [])
                    tickers = item.get("tickers", [])
                    link_strength = item.get("link_strength", 0)
                    summary = item.get("summary", "")
                    url = item.get("#url", "")  # Use alias for reserved keyword
                    s3_key = item.get("s3_key", "")
                    
                    # Choose body content priority
                    final_body = ""
                    s3_body_key = None
                    
                    if body and len(body) >= min_body_chars:
                        final_body = body
                    elif s3_key:
                        s3_body = self._fetch_body_from_s3(s3_key)
                        if s3_body and len(s3_body) >= min_body_chars:
                            final_body = s3_body
                            s3_body_key = s3_key
                    
                    # Skip if no valid body content
                    if not final_body or not title:
                        continue
                    
                    # Prepare document
                    doc = {
                        "doc_id": doc_id,
                        "title": title,
                        "body": final_body,
                        "source": source,
                        "published_utc": published_utc,
                        "fetched_at": fetched_at,
                        "query_ticker": query_ticker,
                        "matched_tickers": matched_tickers if matched_tickers else [],
                        "tickers": tickers if tickers else [],
                        "link_strength": link_strength,
                        "summary": summary,
                        "url": url,
                        "s3_body_key": s3_body_key
                    }
                    
                    docs.append(doc)
                
                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break
                    
            except ClientError as e:
                print(f"[ERROR] DynamoDB scan failed: {e}")
                break
            except Exception as e:
                print(f"[ERROR] Unexpected error during scan: {e}")
                break
        
        print(f"[LOAD] Scanned {scanned} items, loaded {len(docs)} valid documents")
        return docs
    
    def _process_documents(self, docs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process documents: clean, chunk, and prepare for embedding"""
        print("[PROCESS] Cleaning and chunking documents...")
        
        all_chunks = []
        chunk_metadata = []
        
        for doc in docs:
            # Clean body text
            cleaned_body = clean_body(doc["body"])
            
            # Chunk text
            chunks = self.chunker.split_text(cleaned_body, doc["doc_id"], title=doc["title"])
            
            for chunk in chunks:
                # Prepare metadata for this chunk
                meta = {
                    "chunk_id": chunk.id,
                    "doc_id": chunk.doc_id,
                    "chunk_index": chunk.chunk_index,
                    "tokens": chunk.tokens,
                    "title": doc["title"],  # Original title, not chunk text
                    "source": doc["source"],
                    "url": doc["url"],
                    "tickers": doc["tickers"],
                    "published_utc": doc["published_utc"],
                    "s3_body_key": doc["s3_body_key"]
                }
                
                chunk_metadata.append(meta)
                all_chunks.append(chunk)
        
        # Sort by (doc_id, chunk_index) for deterministic order
        chunk_metadata.sort(key=lambda x: (x["doc_id"], x["chunk_index"]))
        
        # Add row_index
        for i, meta in enumerate(chunk_metadata):
            meta["row_index"] = i
        
        print(f"[PROCESS] Created {len(all_chunks)} chunks from {len(docs)} documents")
        return all_chunks, chunk_metadata
    
    def _embed_chunks(self, chunks: List[Dict[str, Any]]) -> np.ndarray:
        """Embed all chunks using the embedder"""
        print("[EMBED] Generating embeddings...")
        
        texts = [chunk.text for chunk in chunks]
        
        # Check cache first
        cached_embeddings = []
        uncached_texts = []
        uncached_indices = []
        
        for i, text in enumerate(texts):
            cached_emb = self._get_cached_embedding(text)
            if cached_emb is not None:
                cached_embeddings.append((i, cached_emb))
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)
        
        # Generate embeddings for uncached texts
        if uncached_texts:
            t0 = time.time()
            new_embeddings = self.embedder.encode(uncached_texts, normalize=True)
            dt = time.time() - t0
            
            # Cache new embeddings
            for i, (text, emb) in enumerate(zip(uncached_texts, new_embeddings)):
                self._cache_embedding(text, emb)
                cached_embeddings.append((uncached_indices[i], emb))
            
            print(f"[EMBED] Generated {len(uncached_texts)} new embeddings in {dt:.2f}s")
        
        # Combine all embeddings in correct order
        all_embeddings = []
        for i in range(len(texts)):
            for idx, emb in cached_embeddings:
                if idx == i:
                    all_embeddings.append(emb)
                    break
        
        embeddings = np.array(all_embeddings, dtype=np.float32)
        print(f"[EMBED] Total embeddings: {embeddings.shape}")
        return embeddings
    
    def _build_faiss_index(self, embeddings: np.ndarray) -> faiss.Index:
        """Build FAISS index from embeddings"""
        print("[FAISS] Building index...")
        
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings.astype(np.float32))
        
        print(f"[FAISS] Index built: {index.ntotal} vectors, {dim} dimensions")
        return index
    
    def _write_artifacts_locally(self, version: str, index: faiss.Index, 
                                chunk_metadata: List[Dict[str, Any]], 
                                embeddings: np.ndarray) -> Dict[str, str]:
        """Write artifacts to local directory"""
        print(f"[WRITE] Writing artifacts locally to ./.artifacts/faiss/{version}/")
        
        # Create local directory
        local_dir = Path(f"./.artifacts/faiss/{version}")
        local_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Write FAISS index
        index_path = local_dir / "index.faiss"
        faiss.write_index(index, str(index_path))
        
        # 2. Write chunks metadata
        chunks_path = local_dir / "chunks.parquet"
        chunks_key = f"faiss/{version}/chunks.parquet"
        
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            
            # Convert to pyarrow table
            table_data = {
                "row_index": [m["row_index"] for m in chunk_metadata],
                "chunk_id": [m["chunk_id"] for m in chunk_metadata],
                "doc_id": [m["doc_id"] for m in chunk_metadata],
                "chunk_index": [m["chunk_index"] for m in chunk_metadata],
                "tokens": [m["tokens"] for m in chunk_metadata],
                "title": [m["title"] for m in chunk_metadata],
                "source": [m["source"] for m in chunk_metadata],
                "url": [m["url"] for m in chunk_metadata],
                "tickers": [m["tickers"] for m in chunk_metadata],
                "published_utc": [m["published_utc"] for m in chunk_metadata],
                "s3_body_key": [m["s3_body_key"] for m in chunk_metadata]
            }
            
            table = pa.table(table_data)
            pq.write_table(table, str(chunks_path))
            
        except ImportError:
            # Fallback to CSV
            import csv
            
            chunks_path = local_dir / "chunks.csv"
            chunks_key = f"faiss/{version}/chunks.csv"
            
            with open(chunks_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["row_index", "chunk_id", "doc_id", "chunk_index", "tokens", 
                               "title", "source", "url", "tickers", "published_utc", "s3_body_key"])
                
                for meta in chunk_metadata:
                    writer.writerow([
                        meta["row_index"], meta["chunk_id"], meta["doc_id"], meta["chunk_index"],
                        meta["tokens"], meta["title"], meta["source"], meta["url"],
                        str(meta["tickers"]), meta["published_utc"], meta["s3_body_key"] or ""
                    ])
        
        # 3. Write embeddings
        embeddings_path = local_dir / "embeddings.npy"
        np.save(str(embeddings_path), embeddings)
        
        # 4. Write manifest
        manifest = {
            "version": version,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "bucket": self.bucket,
            "region": self.region,
            "index_key": f"faiss/{version}/index.faiss",
            "chunks_key": chunks_key,
            "emb_key": f"faiss/{version}/embeddings.npy",
            "ntotal": index.ntotal,
            "dim": embeddings.shape[1]
        }
        
        manifest_path = local_dir / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        print(f"[WRITE] Local artifacts written successfully")
        return {
            "index": str(index_path),
            "chunks": str(chunks_path),
            "embeddings": str(embeddings_path),
            "manifest": str(manifest_path)
        }
    
    def _upload_to_s3(self, version: str, local_paths: Dict[str, str]):
        """Upload artifacts to S3"""
        print(f"[UPLOAD] Uploading artifacts to S3...")
        
        for artifact_type, local_path in local_paths.items():
            if artifact_type == "manifest":
                s3_key = f"faiss/{version}/manifest.json"
            else:
                s3_key = f"faiss/{version}/{Path(local_path).name}"
            
            try:
                self.s3.upload_file(local_path, self.bucket, s3_key)
                print(f"[UPLOAD] {artifact_type}: s3://{self.bucket}/{s3_key}")
            except Exception as e:
                print(f"[ERROR] Failed to upload {artifact_type}: {e}")
                raise
    
    def _update_latest_pointer(self, version: str):
        """Update the latest.json pointer"""
        print("[POINTER] Updating latest.json pointer...")
        
        latest_content = {
            "version": version,
            "manifest_key": f"faiss/{version}/manifest.json",
            "updated_at_utc": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key="faiss/latest.json",
                Body=json.dumps(latest_content, indent=2),
                ContentType="application/json"
            )
            print(f"[POINTER] Updated s3://{self.bucket}/faiss/latest.json")
        except Exception as e:
            print(f"[ERROR] Failed to update latest pointer: {e}")
            raise
    
    def build_index(self, limit: int, min_body_chars: int) -> str:
        """Main method to build and publish the index"""
        start_time = time.time()
        
        try:
            # 1. Load documents
            docs = self._load_documents_from_dynamodb(limit, min_body_chars)
            if not docs:
                raise ValueError("No valid documents found")
            
            # 2. Process documents
            chunks, chunk_metadata = self._process_documents(docs)
            
            # 3. Generate embeddings
            embeddings = self._embed_chunks(chunks)
            
            # 4. Build FAISS index
            index = self._build_faiss_index(embeddings)
            
            # Verify index size
            assert index.ntotal == len(chunks), f"Index size mismatch: {index.ntotal} != {len(chunks)}"
            
            # 5. Generate version
            version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            
            # 6. Write artifacts locally
            local_paths = self._write_artifacts_locally(version, index, chunk_metadata, embeddings)
            
            # 7. Upload to S3
            self._upload_to_s3(version, local_paths)
            
            # 8. Update latest pointer
            self._update_latest_pointer(version)
            
            # 9. Print statistics
            total_time = time.time() - start_time
            token_lengths = [m["tokens"] for m in chunk_metadata]
            avg_tokens = np.mean(token_lengths)
            p90_tokens = np.percentile(token_lengths, 90)
            
            print(f"\n[SUCCESS] Index built and published successfully!")
            print(f"[STATS] Documents: {len(docs)} | Chunks: {len(chunks)} | Avg tokens: {avg_tokens:.1f} | P90 tokens: {p90_tokens:.1f}")
            print(f"[STATS] Embedding throughput: {len(chunks)/total_time:.1f} chunks/s | Total time: {total_time:.1f}s")
            print(f"[S3] Index: s3://{self.bucket}/faiss/{version}/index.faiss")
            print(f"[S3] Chunks: s3://{self.bucket}/faiss/{version}/chunks.parquet")
            print(f"[S3] Embeddings: s3://{self.bucket}/faiss/{version}/embeddings.npy")
            print(f"[S3] Manifest: s3://{self.bucket}/faiss/{version}/manifest.json")
            print(f"[S3] Latest: s3://{self.bucket}/faiss/latest.json")
            
            return version
            
        except Exception as e:
            print(f"[ERROR] Index building failed: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(description="Build and publish vector index to AWS S3")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum documents to process")
    parser.add_argument("--min_body_chars", type=int, default=400, help="Minimum body length in characters")
    parser.add_argument("--region", default="us-east-2", help="AWS region")
    parser.add_argument("--bucket", default="fin-news-raw-yz", help="S3 bucket name")
    parser.add_argument("--table", default="news_documents", help="DynamoDB table name")
    parser.add_argument("--s3-prefix", default="polygon/", help="S3 prefix for raw data")
    parser.add_argument("--no-blingfire", action="store_true", help="Disable BlingFire sentence splitter")
    
    args = parser.parse_args()
    
    try:
        builder = IndexBuilder(
            region=args.region,
            bucket=args.bucket,
            table=args.table,
            s3_prefix=args.s3_prefix,
            use_blingfire=not args.no_blingfire
        )
        
        version = builder.build_index(args.limit, args.min_body_chars)
        print(f"\n✅ Index version {version} built and published successfully!")
        
    except KeyboardInterrupt:
        print("\n[INFO] Build interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Build failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 