#!/usr/bin/env python3
"""
测试增量索引构建功能
"""
import sys
import subprocess
import time
import json
import requests

def test_incremental_build():
    """测试增量构建功能"""
    print("🧪 Testing Incremental Index Build")
    print("=" * 50)
    
    # 1. 测试dry-run模式
    print("1. Testing dry-run mode...")
    result = subprocess.run([
        sys.executable, "scripts/build_index_incremental.py",
        "--dry-run", "true",
        "--limit", "5"
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Dry-run test passed")
    else:
        print(f"❌ Dry-run test failed: {result.stderr}")
        return False
    
    # 2. 测试实际增量构建
    print("\n2. Testing actual incremental build...")
    result = subprocess.run([
        sys.executable, "scripts/build_index_incremental.py",
        "--dry-run", "false",
        "--limit", "3"
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Incremental build test passed")
        # 提取统计信息
        output_lines = result.stdout.split('\n')
        for line in output_lines:
            if "Old total:" in line or "New added:" in line or "New total:" in line:
                print(f"   {line.strip()}")
    else:
        print(f"❌ Incremental build test failed: {result.stderr}")
        return False
    
    # 3. 测试索引检查
    print("\n3. Testing index status check...")
    result = subprocess.run([
        sys.executable, "scripts/check_faiss_index.py"
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Index status check passed")
    else:
        print(f"❌ Index status check failed: {result.stderr}")
        return False
    
    # 4. 测试搜索服务加载
    print("\n4. Testing search service loading...")
    try:
        from apps.service.search_api import search_service
        print(f"✅ Search service loaded successfully")
        print(f"   Current index: {search_service.config.get('ntotal', 0)} vectors")
        print(f"   Version: {search_service.config.get('version', 'unknown')}")
    except Exception as e:
        print(f"❌ Search service loading failed: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 All incremental build tests passed!")
    return True

def test_search_with_new_index():
    """测试新索引的搜索功能"""
    print("\n🔍 Testing search with new index...")
    
    try:
        # 启动服务
        print("Starting search service...")
        process = subprocess.Popen([
            "uvicorn", "apps.service.search_api:app",
            "--host", "0.0.0.0", "--port", "8000"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # 等待服务启动
        time.sleep(5)
        
        # 测试搜索
        response = requests.post("http://localhost:8000/search", json={
            "query": "NVDA earnings",
            "top_k": 3
        }, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Search test passed: {data['total_results']} results")
            print(f"   Response time: {data['timings']['total_ms']:.1f}ms")
        else:
            print(f"❌ Search test failed: {response.status_code}")
            return False
        
        # 停止服务
        process.terminate()
        process.wait()
        
        return True
        
    except Exception as e:
        print(f"❌ Search test failed: {e}")
        if 'process' in locals():
            process.terminate()
        return False

def main():
    """主测试函数"""
    print("🚀 Incremental Build Test Suite")
    print("=" * 60)
    
    # 运行增量构建测试
    if not test_incremental_build():
        print("❌ Incremental build tests failed")
        return 1
    
    # 运行搜索测试
    if not test_search_with_new_index():
        print("❌ Search tests failed")
        return 1
    
    print("\n🎉 All tests passed! Incremental build is working correctly.")
    return 0

if __name__ == "__main__":
    exit(main())
