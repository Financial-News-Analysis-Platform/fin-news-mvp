#!/usr/bin/env python3
"""
快速测试Index模块的脚本
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

def test_index_module():
    """测试index模块的基本功能"""
    try:
        print("🚀 测试Index模块...")
        
        # 测试导入
        from apps.index.chunk import TextChunker
        from apps.index.embed import TextEmbedder
        from apps.index.faiss_store import FAISSStore
        
        print("✅ 模块导入成功")
        
        # 测试分块器
        chunker = TextChunker(max_tokens=300, overlap=30)
        print("✅ 分块器初始化成功")
        
        # 测试向量化器
        embedder = TextEmbedder()
        print(f"✅ 向量化器初始化成功，维度: {embedder.get_embedding_dimension()}")
        
        # 测试FAISS存储
        store = FAISSStore(dimension=embedder.get_embedding_dimension())
        print("✅ FAISS存储初始化成功")
        
        print("\n🎉 Index模块测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

if __name__ == "__main__":
    test_index_module()
