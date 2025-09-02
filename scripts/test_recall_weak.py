# -*- coding: utf-8 -*-
"""
Weakly-supervised Recall@5 for news RAG
- Load docs from AWS (DynamoDB + S3). If ticker/time缺失会跳过该query。
- Chunk with your token-based TextChunker (uses title in first chunk).
- Embed once (normalized).
- Build FAISS IndexFlatIP.
- For each sampled query chunk: success if top-5 neighbors contain a chunk
  with overlapping ticker AND within ±3 days.
"""

import os, sys, json, time, random, faiss, numpy as np
from datetime import datetime, timedelta, timezone
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from apps.index.chunk import TextChunker
from apps.index.embed import TextEmbedder

# ---------- helpers ----------
def parse_iso(ts: str):
    if not ts: return None
    if ts.endswith("Z"): ts = ts.replace("Z","+00:00")
    try:
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except Exception:
        return None

def load_docs_from_aws(limit=400):
    import boto3
    table  = os.getenv("DDB_TABLE",  "news_documents")
    bucket = os.getenv("S3_BUCKET",  "fin-news-raw-yz")
    region = os.getenv("AWS_REGION","us-east-2")
    ddb = boto3.resource("dynamodb", region_name=region)
    s3  = boto3.client("s3",         region_name=region)
    tbl = ddb.Table(table)
    resp = tbl.scan(Limit=limit)
    items = resp.get("Items", [])[:limit]
    docs = []
    for it in items:
        doc_id  = it.get("doc_id") or it.get("id") or it.get("pk")
        title   = it.get("title") or ""
        body    = it.get("body") or ""  # 直接使用 body 字段
        ts      = it.get("published_utc") or it.get("published_at") or it.get("ts") or ""
        tickers = it.get("tickers") or it.get("matched_tickers") or []
        
        # 如果没有 body 内容，跳过
        if not doc_id or not (title or body): 
            continue
            
        docs.append({"id":doc_id, "title":title, "body":body, "published_at":ts, "tickers":tickers})
    return docs

# ---------- main ----------
if __name__ == "__main__":
    print("[LOAD] reading from AWS…")
    docs = load_docs_from_aws(limit=400)
    print(f"[LOAD] docs={len(docs)}")

    # 1) chunk
    chunker = TextChunker(
        target_tokens=360, max_tokens=460, overlap_tokens=40, min_tokens=200,
        use_blingfire=True  # 若未安装blingfire会自动fallback到regex
    )
    chunks = []
    for d in docs:
        chs = chunker.split_text(d["body"], d["id"], title=d["title"])
        ts  = d.get("published_at")
        for c in chs:
            c.meta = {"tickers": d.get("tickers", []), "ts": ts}
        chunks.extend(chs)
    print(f"[CHUNK] chunks={len(chunks)}")

    # 2) embed (single load)
    texts = [c.text for c in chunks]
    embedder = TextEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
    t0 = time.time()
    vecs = embedder.encode(texts, normalize=True).astype("float32")
    print(f"[EMB] took {time.time()-t0:.2f}s for {len(texts)} chunks")

    # 3) index
    dim = vecs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vecs)
    print(f"[FAISS] ntotal={index.ntotal}")

    # 4) weak labels: same ticker & within ±3 days
    k = 5
    wins = timedelta(days=3)
    rng = random.Random(0)

    # candidate queries：必须有 ticker & ts
    q_ids = []
    for i, c in enumerate(chunks):
        ts = c.meta.get("ts"); tick = c.meta.get("tickers", [])
        if tick and parse_iso(ts):
            q_ids.append(i)
    if not q_ids:
        print("[WARN] no query candidates with ticker+timestamp; abort.")
        sys.exit(0)

    sample = rng.sample(q_ids, min(150, len(q_ids)))
    hits, total = 0, 0

    def ts_of(c):
        return parse_iso(c.meta.get("ts"))

    # latency粗测
    t_search = 0.0
    for i in sample:
        q = vecs[i:i+1]
        t1 = time.time()
        D, I = index.search(q, k+1)  # +1 to include self
        t_search += (time.time() - t1)
        qtick = set(chunks[i].meta.get("tickers", []))
        qts   = ts_of(chunks[i])
        if not qts: 
            continue
        total += 1
        ok = False
        for j in I[0]:
            if j == i or j < 0: 
                continue
            ctick = set(chunks[j].meta.get("tickers", []))
            cts   = ts_of(chunks[j])
            if not cts: 
                continue
            # weak label
            if (qtick & ctick) and abs((cts - qts).days) <= wins.days:
                ok = True
                break
        if ok: 
            hits += 1

    recall_at5 = hits / max(1, total)
    print(f"[WEAK-RECALL@5] total={total}, hits={hits}, recall={recall_at5:.2f}")
    if total:
        print(f"[LATENCY] avg_search_ms={t_search/total*1000:.2f}  (IndexFlatIP, no filter)")
