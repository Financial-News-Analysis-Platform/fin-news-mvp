# -*- coding: utf-8 -*-
"""
Sanity check on chunking / embedding / faiss using REAL docs
- Loads docs from AWS if possible, else from data/samples.jsonl
- Reports token stats for chunks
- Checks embedding L2 norms (should be ≈1.0)
- Runs a tiny FAISS search
"""

import os, sys, json, re, time, random
from statistics import mean
from typing import List, Dict, Any, Optional

# --- make project root importable ---
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from apps.index.chunk import TextChunker           # 需要你已按“token 版”实现
from apps.index.embed import TextEmbedder
import faiss
import numpy as np

# ---------- data loading ----------
def parse_iso(ts: str):
    from datetime import datetime, timezone
    if not ts: return None
    try:
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z","+00:00")).astimezone(timezone.utc)
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except Exception:
        return None

def load_from_local(path="data/samples.jsonl", limit=30) -> List[Dict[str,Any]]:
    docs = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= limit: break
                try:
                    obj = json.loads(line)
                    docs.append(obj)
                except Exception:
                    continue
    else:
        # fallback tiny samples
        docs = [
            {"id":"s1","title":"NVIDIA acquires Startup X for $1B","body":"NVIDIA announced it will acquire Startup X in a cash-and-stock deal worth $1 billion. The deal is expected to close in Q4.","published_at":"2025-08-18T13:00:00Z","tickers":["NVDA"]},
            {"id":"s2","title":"Apple Q3 earnings beat expectations","body":"Apple reported revenue of $90B and EPS of $1.35, beating estimates. Guidance remained cautious.","published_at":"2025-08-19T21:00:00Z","tickers":["AAPL"]},
            {"id":"s3","title":"美联储或将按兵不动","body":"美联储表示在通胀回落和就业市场稳定的情况下，可能维持当前利率水平不变。"}
        ]
    return docs

def load_from_aws(limit=40) -> Optional[List[Dict[str,Any]]]:
    try:
        import boto3
    except Exception:
        return None
    table = os.getenv("DDB_TABLE", "news_documents")
    bucket = os.getenv("S3_BUCKET", "fin-news-raw-yz")
    region = os.getenv("AWS_REGION", "us-east-1")

    ddb = boto3.resource("dynamodb", region_name=region)
    s3  = boto3.client("s3", region_name=region)

    tbl = ddb.Table(table)
    resp = tbl.scan(Limit=limit)
    items = resp.get("Items", [])[:limit]
    out = []
    for it in items:
        # 兼容不同字段名
        doc_id = it.get("id") or it.get("doc_id") or it.get("pk")
        title  = it.get("title") or ""
        body_key = it.get("s3_key") or it.get("body_key") or it.get("s3_path")
        published_at = it.get("published_at") or it.get("ts") or ""
        tickers = it.get("tickers") or []
        if not body_key:
            # 有些表直接就存了 body
            body = it.get("body") or it.get("content") or ""
        else:
            try:
                obj = s3.get_object(Bucket=bucket, Key=body_key)
                body = obj["Body"].read().decode("utf-8", errors="ignore")
            except Exception:
                body = it.get("body") or ""
        if not doc_id or not (title or body):
            continue
        out.append({
            "id": doc_id,
            "title": title,
            "body": body,
            "published_at": published_at,
            "tickers": tickers
        })
    return out or None

# ---------- basic token helpers ----------
import tiktoken
ENC = tiktoken.get_encoding("cl100k_base")
def tok_len(s: str) -> int:
    return len(ENC.encode(s or ""))

def rough_broken_ratio(texts: List[str]) -> float:
    """very rough: chunk head/tail look like half-sentences"""
    broken = 0
    for t in texts:
        if re.search(r"^[a-z0-9A-Z]", t) or re.search(r"[a-z0-9A-Z]$", t):
            broken += 1
    return broken / max(1, len(texts))

# ---------- main ----------
if __name__ == "__main__":
    # 1) load docs
    docs = load_from_aws(limit=40) or load_from_local(limit=30)
    print(f"[LOAD] got {len(docs)} docs (aws={'yes' if os.getenv('AWS_ACCESS_KEY_ID') else 'no'})")

    # 2) chunking (token-based)
    chunker = TextChunker(target_tokens=400, max_tokens=500, overlap_tokens=50)
    all_chunks = []
    for d in docs:
        chs = chunker.split_text(d.get("body",""), d.get("id","doc"), title=d.get("title",""))
        all_chunks.extend(chs)

    if not all_chunks:
        print("[CHUNK] no chunks produced; check your chunker implementation.")
        sys.exit(1)

    token_sizes = [c.tokens for c in all_chunks]
    token_sizes.sort()
    p50 = token_sizes[len(token_sizes)//2]
    p90 = token_sizes[int(0.9*len(token_sizes))]
    orphan_cnt = 0
    # 孤儿块：最后一块 <200 token 且该文超过 1 块（需要 doc_id 分组）
    from collections import defaultdict
    by_doc = defaultdict(list)
    for c in all_chunks:
        by_doc[c.doc_id].append(c)
    for _, lst in by_doc.items():
        lst = sorted(lst, key=lambda x: x.chunk_index)
        if len(lst) > 1 and tok_len(lst[-1].text) < 200:
            orphan_cnt += 1

    print(f"[CHUNK] chunks={len(all_chunks)}, avg={np.mean(token_sizes):.1f}, p50={p50}, p90={p90}")
    print(f"[CHUNK] orphan_ratio={orphan_cnt / max(1,len(by_doc)):.2f}, rough_broken_ratio={rough_broken_ratio([c.text for c in all_chunks]):.2f}")

    # 3) embedding (single model load, normalized)
    texts = [c.text for c in all_chunks]
    # 只抽样一部分，防止太多文本占内存
    sample_n = min(1000, len(texts))
    texts = random.sample(texts, sample_n)

    embedder = TextEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
    t0 = time.time()
    vecs = embedder.encode(texts, normalize=True)
    dt = time.time() - t0
    norms = np.linalg.norm(vecs, axis=1)
    print(f"[EMB] n={len(texts)}, time={dt:.2f}s, throughput={len(texts)/max(dt,1e-6):.1f}/s")
    print(f"[EMB] norm_avg={norms.mean():.4f}, p5={np.percentile(norms,5):.4f}, p95={np.percentile(norms,95):.4f}")

    # 4) FAISS quick check
    dim = vecs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vecs.astype("float32"))
    D, I = index.search(vecs[0:1].astype("float32"), k=5)
    print(f"[FAISS] top5 idx={I.tolist()[0]} sim={list(map(lambda x: round(float(x),3), D.tolist()[0]))}")
