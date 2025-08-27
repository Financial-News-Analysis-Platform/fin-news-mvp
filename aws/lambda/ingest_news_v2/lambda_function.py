import os
import json
import hashlib
import requests
from datetime import datetime, timezone
import boto3
from bs4 import BeautifulSoup
from decimal import Decimal
import botocore
import re
from urllib.parse import urlparse

# ========== Config ==========
BUCKET = os.environ.get("BUCKET", "")
TABLE_DOCS = os.environ.get("TABLE_DOCS", "news_documents")
TABLE_STOCK = os.environ.get("TABLE_STOCK", "stock_prices")
TABLE_OPTION = os.environ.get("TABLE_OPTION", "stock_options")
SOURCE = "polygon"
API_KEY = os.environ.get("POLYGON_API_KEY")

DEFAULT_ALLOWED_TICKERS = {"RBLX", "AAPL", "NVDA", "TSLA", "AMZN"}

NEWS_URL = "https://api.polygon.io/v2/reference/news"
PRICE_URL = "https://api.polygon.io/v1/open-close/{ticker}/{date}"
OPTION_URL = "https://api.polygon.io/v3/snapshot/options/{ticker}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}

# 噪声域名（宏观/点评类，标签多但正文未必提公司）
NOISY_DOMAINS = {"www.investing.com", "investing.com"}

# 轻量公司名匹配（只维护白名单里的，避免引第三方大词表）
TICKER_NAME_MAP = {
    "AAPL": ["apple"],
    "NVDA": ["nvidia"],
    "TSLA": ["tesla"],
    "AMZN": ["amazon"],
    "RBLX": ["roblox"],
}

# ========== AWS Clients ==========
s3 = boto3.client("s3")
ddb_docs = boto3.resource("dynamodb").Table(TABLE_DOCS)
ddb_price = boto3.resource("dynamodb").Table(TABLE_STOCK)
ddb_option = boto3.resource("dynamodb").Table(TABLE_OPTION)

# ========== Utilities ==========
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def sha256_hex(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def news_exists(doc_id):
    try:
        resp = ddb_docs.get_item(Key={"doc_id": doc_id})
        return "Item" in resp
    except Exception as e:
        print("[Error] Failed checking news existence:", str(e))
        return False

def price_exists(ticker, date):
    try:
        resp = ddb_price.get_item(Key={"ticker": ticker, "date": date})
        return "Item" in resp
    except Exception as e:
        print("[Error] price_exists:", e)
        return False

def option_exists(ticker, date):
    try:
        resp = ddb_option.get_item(Key={"ticker": ticker, "date": date})
        return "Item" in resp
    except Exception as e:
        print("[Error] option_exists:", e)
        return False

def fetch_news(ticker, limit=50):
    params = {
        "ticker": ticker,
        "order": "desc",
        "limit": limit,
        "apiKey": API_KEY,
    }
    resp = requests.get(NEWS_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("results", []) or []

def scrape_body(article_url):
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 更稳容器选择：优先 article/正文常见容器；退化为全文 p
        candidates = soup.select("article, .article-body, .entry-content, .post-content, main")
        container = None
        for c in candidates:
            if len(c.find_all("p")) >= 3:
                container = c
                break
        nodes = (container or soup).find_all("p")
        paras = [p.get_text(" ", strip=True) for p in nodes]
        text = "\n".join([t for t in paras if t])
        return text.strip()
    except Exception as e:
        print("[Error] Failed to scrape body:", str(e))
        return ""

CASHTAG_RE = re.compile(r'\$([A-Z]{1,5})\b')
def mentions_ticker(body_text: str, ticker: str) -> bool:
    if not body_text:
        return False
    t = ticker.upper()
    # 1) cashtag
    for m in CASHTAG_RE.findall(body_text):
        if m == t:
            return True
    # 2) 公司名关键词（小写对比）
    names = TICKER_NAME_MAP.get(t, [])
    low = body_text.lower()
    return any(name in low for name in names)

def extract_matched_tickers(body_text: str, allowed_set):
    matched = []
    for t in allowed_set:
        if mentions_ticker(body_text, t):
            matched.append(t)
    return matched

def fetch_price(ticker, date):
    if not date:
        print("[SKIP] fetch_price missing date")
        return {"skipped": True, "reason": "no_date"}
    if price_exists(ticker, date):
        return {"skipped": True, "reason": "exists"}

    url = PRICE_URL.format(ticker=ticker, date=date)
    resp = requests.get(url, params={"apiKey": API_KEY}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("close") is None:
        return {"skipped": True, "reason": "no_close"}
    try:
        ddb_price.put_item(
            Item={
                "ticker": ticker,
                "date": date,
                "price": Decimal(str(data["close"])),
                "fetched_at": now_iso()
            },
            ConditionExpression="attribute_not_exists(#t) AND attribute_not_exists(#d)",
            ExpressionAttributeNames={"#t": "ticker", "#d": "date"},
        )
        return {"ok": True}
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return {"skipped": True, "reason": "exists_race"}
        raise

def fetch_option(ticker, date):
    if not date:
        print("[SKIP] fetch_option missing date")
        return {"skipped": True, "reason": "no_date"}
    if option_exists(ticker, date):
        return {"skipped": True, "reason": "exists"}

    url = OPTION_URL.format(ticker=ticker)
    resp = requests.get(url, params={"apiKey": API_KEY}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    payload = json.dumps(data)

    item = {
        "ticker": ticker,
        "date": date,
        "fetched_at": now_iso()
    }
    # 保护 400KB 限制
    if len(payload.encode("utf-8")) <= 380_000:
        item["data"] = payload
    else:
        item["summary"] = {
            "status": data.get("status"),
            "results_cnt": len(data.get("results", []))
        }
    ddb_option.put_item(Item=item)
    return {"ok": True}

# ========== Workers ==========
def run_news(tickers, limit=50, force_rescrape=False, strict_for_noisy=True):
    results_summary = {
        "processed": 0, "skipped_no_body": 0, "skipped_exists": 0,
        "stored": 0, "skipped_weak_on_noisy": 0
    }
    for query_ticker in tickers:
        items = fetch_news(query_ticker, limit=limit)
        for it in items:
            doc_id = it.get("id")
            if not doc_id:
                continue

            exists = news_exists(doc_id)
            if exists and not force_rescrape:
                results_summary["skipped_exists"] += 1
                continue

            article_url = it.get("article_url", "")
            body = scrape_body(article_url)
            if not body:
                results_summary["skipped_no_body"] += 1
                continue

            matched = extract_matched_tickers(body, DEFAULT_ALLOWED_TICKERS)
            host = (urlparse(article_url).hostname or "").lower()
            is_noisy = host in NOISY_DOMAINS

            # 对噪声域名，正文没有命中就跳过（避免误关联）
            if strict_for_noisy and is_noisy and not matched:
                results_summary["skipped_weak_on_noisy"] += 1
                continue

            s3_key = f"polygon/{doc_id}.txt"
            s3.put_object(Bucket=BUCKET, Key=s3_key, Body=body.encode("utf-8"))

            payload = {
                "doc_id": doc_id,
                "source": SOURCE,
                "query_ticker": query_ticker,                  # 这条结果由哪个查询ticker得到
                "tickers": it.get("tickers", []) or [],        # Polygon/来源标签
                "matched_tickers": matched,                    # 正文内真实命中的白名单ticker
                "link_strength": "strong" if matched else "weak",
                "title": it.get("title", "") or "",
                "summary": it.get("description", "") or "",
                "published_utc": it.get("published_utc", "") or "",
                "url": article_url,
                "s3_key": s3_key,
                "fetched_at": now_iso(),
            }

            if not exists:
                ddb_docs.put_item(Item=payload)
                results_summary["stored"] += 1
            else:
                if force_rescrape:
                    ddb_docs.update_item(
                        Key={"doc_id": doc_id},
                        UpdateExpression="""
                            SET #qt = :qt, #t = :t, #mt = :mt, #ls = :ls,
                                #ti = :ti, #sm = :sm, #pu = :pu, #url = :url,
                                #s3 = :s3, #fa = :fa
                        """,
                        ExpressionAttributeNames={
                            "#qt": "query_ticker", "#t": "tickers", "#mt": "matched_tickers",
                            "#ls": "link_strength", "#ti": "title", "#sm": "summary",
                            "#pu": "published_utc", "#url": "url", "#s3": "s3_key", "#fa": "fetched_at",
                        },
                        ExpressionAttributeValues={
                            ":qt": payload["query_ticker"], ":t": payload["tickers"], ":mt": payload["matched_tickers"],
                            ":ls": payload["link_strength"], ":ti": payload["title"], ":sm": payload["summary"],
                            ":pu": payload["published_utc"], ":url": payload["url"], ":s3": payload["s3_key"], ":fa": now_iso(),
                        }
                    )

            results_summary["processed"] += 1
    return results_summary

def run_prices(tickers, date=None):
    date = date or datetime.utcnow().strftime("%Y-%m-%d")
    out = {"date": date, "ok": 0, "skip": 0}
    for t in tickers:
        r = fetch_price(t, date)
        if r.get("ok"):
            out["ok"] += 1
        else:
            out["skip"] += 1
    return out

def run_options(tickers, date=None):
    date = date or datetime.utcnow().strftime("%Y-%m-%d")
    out = {"date": date, "ok": 0, "skip": 0}
    for t in tickers:
        r = fetch_option(t, date)
        if r.get("ok"):
            out["ok"] += 1
        else:
            out["skip"] += 1
    return out

# ========== Main Handler ==========
def lambda_handler(event, context):
    """
    event 示例:
    {
      "do_news": true,
      "do_prices": false,
      "do_options": false,
      "tickers": ["AAPL","NVDA"],
      "limit": 20,
      "date": "2025-08-23",
      "force_rescrape": false
    }
    """
    do_news = bool(event.get("do_news"))
    do_prices = bool(event.get("do_prices"))
    do_options = bool(event.get("do_options"))

    tickers = event.get("tickers") or list(DEFAULT_ALLOWED_TICKERS)
    if isinstance(tickers, str):
        tickers = [tickers]
    limit = int(event.get("limit", 50))
    date = event.get("date")
    force_rescrape = bool(event.get("force_rescrape"))

    result = {"status": "ok", "actions": []}

    if do_news:
        r = run_news(tickers, limit=limit, force_rescrape=force_rescrape)
        result["actions"].append({"news": r})
    if do_prices:
        r = run_prices(tickers, date=date)
        result["actions"].append({"prices": r})
    if do_options:
        r = run_options(tickers, date=date)
        result["actions"].append({"options": r})

    if not (do_news or do_prices or do_options):
        result["status"] = "noop"
        result["hint"] = "set do_news / do_prices / do_options to true"

    return result
