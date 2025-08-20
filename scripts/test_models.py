#!/usr/bin/env python3
"""
测试数据模型的脚本
"""
import sys
import os
from datetime import datetime, timezone

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def test_document_model():
    """测试Document模型"""
    print("🧪 测试Document模型...")
    
    try:
        from apps.index.models import Document, SourceType, DocumentStatus
        
        # 创建测试文档
        doc = Document(
            id="yahoo_001",
            title="Apple Reports Strong Q3 Earnings",
            body="Apple Inc. reported strong quarterly earnings today. The company's revenue exceeded analyst expectations by 15%. iPhone sales were particularly strong, with a 20% increase year-over-year.",
            published_at=datetime.now(timezone.utc),
            url="https://finance.yahoo.com/news/apple-earnings",
            source=SourceType.YAHOO_FINANCE,
            tickers=["AAPL", "GOOGL"],
            author="John Smith",
            category="Earnings"
        )
        
        print(f"✅ Document创建成功: {doc.id}")
        print(f"   - 标题: {doc.title}")
        print(f"   - 股票代码: {doc.tickers}")
        print(f"   - 状态: {doc.status}")
        
        # 测试验证器
        try:
            invalid_doc = Document(
                id="invalid",
                title="Test",
                body="Too short",  # 少于10个字符
                published_at=datetime.now(timezone.utc),
                url="https://test.com",
                source=SourceType.YAHOO_FINANCE
            )
        except ValueError as e:
            print(f"✅ 验证器工作正常: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Document模型测试失败: {e}")
        return False


def test_chunk_model():
    """测试Chunk模型"""
    print("\n🧪 测试Chunk模型...")
    
    try:
        from apps.index.models import Chunk
        
        chunk = Chunk(
            id="chunk_001",
            doc_id="yahoo_001",
            chunk_index=0,
            text="Apple Inc. reported strong quarterly earnings today. The company's revenue exceeded analyst expectations by 15%.",
            tokens=25,
            start_sentence=0,
            end_sentence=2,
            overlap=0
        )
        
        print(f"✅ Chunk创建成功: {chunk.id}")
        print(f"   - 文档ID: {chunk.doc_id}")
        print(f"   - Token数: {chunk.tokens}")
        print(f"   - 句子范围: {chunk.start_sentence}-{chunk.end_sentence}")
        
        return True
        
    except Exception as e:
        print(f"❌ Chunk模型测试失败: {e}")
        return False


def test_story_model():
    """测试Story模型"""
    print("\n🧪 测试Story模型...")
    
    try:
        from apps.index.models import Story
        
        story = Story(
            id="story_001",
            title="Apple Q3 Earnings Analysis",
            summary="Apple reported strong Q3 earnings with revenue exceeding expectations by 15%",
            doc_ids=["yahoo_001", "yahoo_002"],
            chunk_ids=["chunk_001", "chunk_002"],
            tickers=["AAPL"],
            key_events=[
                {"event": "Earnings Release", "date": "2024-08-20"},
                {"event": "Revenue Beat", "percentage": "15%"}
            ],
            entities=[
                {"name": "Apple Inc.", "type": "company"},
                {"name": "iPhone", "type": "product"}
            ],
            sentiment=0.8,
            sources=["Yahoo Finance", "Reuters"],
            confidence_score=0.95
        )
        
        print(f"✅ Story创建成功: {story.id}")
        print(f"   - 标题: {story.title}")
        print(f"   - 相关文档数: {len(story.doc_ids)}")
        print(f"   - 情感分数: {story.sentiment}")
        print(f"   - 置信度: {story.confidence_score}")
        
        return True
        
    except Exception as e:
        print(f"❌ Story模型测试失败: {e}")
        return False


def test_batch_processing_models():
    """测试批量处理模型"""
    print("\n🧪 测试批量处理模型...")
    
    try:
        from apps.index.models import (
            BatchProcessingRequest, BatchProcessingResponse,
            ProcessingResult, DocumentStatus, Document, SourceType
        )
        
        # 创建批量处理请求
        request = BatchProcessingRequest(
            documents=[
                Document(
                    id="doc_001",
                    title="Test Doc 1",
                    body="This is a test document for batch processing.",
                    published_at=datetime.now(timezone.utc),
                    url="https://test1.com",
                    source=SourceType.YAHOO_FINANCE
                ),
                Document(
                    id="doc_002", 
                    title="Test Doc 2",
                    body="This is another test document for batch processing.",
                    published_at=datetime.now(timezone.utc),
                    url="https://test2.com",
                    source=SourceType.YAHOO_FINANCE
                )
            ],
            chunk_size=300,
            overlap=30
        )
        
        print(f"✅ BatchProcessingRequest创建成功")
        print(f"   - 文档数量: {len(request.documents)}")
        print(f"   - 分块大小: {request.chunk_size}")
        print(f"   - 重叠大小: {request.overlap}")
        
        # 创建批量处理响应
        response = BatchProcessingResponse(
            total_documents=2,
            successful=2,
            failed=0,
            results=[
                ProcessingResult(
                    doc_id="doc_001",
                    status=DocumentStatus.COMPLETED,
                    chunks_created=3,
                    embeddings_generated=3,
                    processing_time=1.5
                ),
                ProcessingResult(
                    doc_id="doc_002",
                    status=DocumentStatus.COMPLETED,
                    chunks_created=2,
                    embeddings_generated=2,
                    processing_time=1.2
                )
            ],
            total_processing_time=2.7
        )
        
        print(f"✅ BatchProcessingResponse创建成功")
        print(f"   - 总文档数: {response.total_documents}")
        print(f"   - 成功数: {response.successful}")
        print(f"   - 失败数: {response.failed}")
        print(f"   - 总处理时间: {response.total_processing_time}s")
        
        return True
        
    except Exception as e:
        print(f"❌ 批量处理模型测试失败: {e}")
        return False


def test_json_serialization():
    """测试JSON序列化"""
    print("\n🧪 测试JSON序列化...")
    
    try:
        from apps.index.models import Document, SourceType
        import json
        
        doc = Document(
            id="json_test",
            title="JSON Test Document",
            body="This document tests JSON serialization functionality.",
            published_at=datetime.now(timezone.utc),
            url="https://json-test.com",
            source=SourceType.YAHOO_FINANCE,
            tickers=["TEST"]
        )
        
        # 转换为JSON
        doc_json = doc.json()
        print(f"✅ JSON序列化成功")
        print(f"   - JSON长度: {len(doc_json)} 字符")
        
        # 从JSON恢复
        doc_dict = json.loads(doc_json)
        print(f"✅ JSON反序列化成功")
        print(f"   - 恢复的ID: {doc_dict['id']}")
        print(f"   - 恢复的标题: {doc_dict['title']}")
        
        return True
        
    except Exception as e:
        print(f"❌ JSON序列化测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🚀 开始测试数据模型...\n")
    
    tests = [
        test_document_model,
        test_chunk_model,
        test_story_model,
        test_batch_processing_models,
        test_json_serialization
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有数据模型测试通过！")
        return True
    else:
        print("❌ 部分测试失败，请检查错误信息")
        return False


if __name__ == "__main__":
    main() 