#!/usr/bin/env python3
"""
测试新的API端点 - /summarize 和 /card
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_status():
    """测试状态端点"""
    print("🔍 Testing /status endpoint...")
    response = requests.get(f"{BASE_URL}/status")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Status: {data['status']}")
        print(f"   Version: {data['version']}")
        print(f"   Total vectors: {data['ntotal']}")
        print(f"   Has embeddings: {data['has_embeddings']}")
        return True
    else:
        print(f"❌ Status failed: {response.status_code}")
        return False

def test_search():
    """测试搜索端点"""
    print("\n🔍 Testing /search endpoint...")
    payload = {
        "query": "NVDA earnings",
        "tickers": ["NVDA"],
        "time_window_days": 7,
        "top_k": 3
    }
    
    response = requests.post(f"{BASE_URL}/search", json=payload)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Search successful: {data['total_results']} results")
        print(f"   Timings: {data['timings']['total_ms']:.1f}ms total")
        return True
    else:
        print(f"❌ Search failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False

def test_summarize():
    """测试摘要端点"""
    print("\n🔍 Testing /summarize endpoint...")
    payload = {
        "query": "NVDA earnings",
        "tickers": ["NVDA"],
        "time_window_days": 7,
        "top_k": 5
    }
    
    response = requests.post(f"{BASE_URL}/summarize", json=payload)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Summarize successful")
        print(f"   Summary: {data['summary'][:100]}...")
        print(f"   Bullets: {len(data['bullets'])} points")
        print(f"   Sentiment: {data['sentiment']}")
        print(f"   Sources: {len(data['sources'])} sources")
        print(f"   Timings: {data['usage']['total_ms']:.1f}ms total")
        return True
    else:
        print(f"❌ Summarize failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False

def test_card():
    """测试卡片端点"""
    print("\n🔍 Testing /card endpoint...")
    payload = {
        "ticker": "NVDA",
        "date": "2025-08-21",
        "time_window_days": 7,
        "top_k": 5
    }
    
    response = requests.post(f"{BASE_URL}/card", json=payload)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Card generation successful")
        print(f"   Ticker: {data['ticker']}")
        print(f"   Date: {data['date']}")
        print(f"   Headline: {data['headline'][:100]}...")
        print(f"   Key points: {len(data['key_points'])} points")
        print(f"   Numbers: {len(data['numbers'])} metrics")
        print(f"   Risks: {len(data['risks'])} risks")
        print(f"   Sentiment: {data['sentiment']}")
        return True
    else:
        print(f"❌ Card generation failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False

def main():
    """主测试函数"""
    print("🚀 Testing Financial News RAG Service - New Endpoints")
    print("=" * 60)
    
    # 等待服务启动
    print("⏳ Waiting for service to start...")
    time.sleep(2)
    
    # 运行测试
    tests = [
        test_status,
        test_search,
        test_summarize,
        test_card
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
    
    # 总结结果
    print("\n" + "=" * 60)
    print("📊 Test Results Summary:")
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"🎉 All {total} tests passed!")
        print("✅ Service is working correctly with new endpoints")
    else:
        print(f"⚠️  {passed}/{total} tests passed")
        print("❌ Some tests failed - check the output above")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
