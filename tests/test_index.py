"""
Index模块测试文件
"""
import sys
import os
import unittest
from unittest.mock import Mock, patch

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from apps.index.chunk import TextChunker, Chunk
from apps.index.embed import TextEmbedder
from apps.index.faiss_store import FAISSStore


class TestTextChunker(unittest.TestCase):
    """测试文本分块器"""
    
    def setUp(self):
        self.chunker = TextChunker(max_tokens=300, overlap=30)
        self.sample_text = """
        Apple Inc. reported strong quarterly earnings today. The company's revenue 
        exceeded analyst expectations by 15%. iPhone sales were particularly strong, 
        with a 20% increase year-over-year. CEO Tim Cook expressed optimism about 
        the upcoming product launches. The stock price rose 5% in after-hours trading.
        
        Analysts are revising their price targets upward. Many believe Apple's 
        services business will continue to grow rapidly. The company's ecosystem 
        approach has proven successful in retaining customers.
        """
    
    def test_chunk_creation(self):
        """测试分块创建"""
        chunks = self.chunker.split_text(self.sample_text, "test_doc")
        
        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 0)
        
        for chunk in chunks:
            self.assertIsInstance(chunk, Chunk)
            self.assertEqual(chunk.doc_id, "test_doc")
            self.assertGreater(len(chunk.text), 0)
    
    def test_chunk_overlap(self):
        """测试分块重叠"""
        chunks = self.chunker.split_text(self.sample_text, "test_doc")
        
        if len(chunks) > 1:
            # 检查相邻块之间是否有重叠
            first_chunk_text = chunks[0].text
            second_chunk_text = chunks[1].text
            
            # 简单检查：第二个块应该包含第一个块的最后几个词
            first_words = first_chunk_text.split()[-5:]  # 最后5个词
            for word in first_words:
                if word in second_chunk_text:
                    break
            else:
                self.fail("No overlap detected between consecutive chunks")


class TestTextEmbedder(unittest.TestCase):
    """测试文本向量化器"""
    
    @patch('torch.cuda.is_available')
    def test_device_detection(self, mock_cuda):
        """测试设备检测"""
        mock_cuda.return_value = False
        
        embedder = TextEmbedder()
        self.assertEqual(embedder.device, "cpu")
    
    def test_embedding_dimension(self):
        """测试向量维度"""
        embedder = TextEmbedder()
        dimension = embedder.get_embedding_dimension()
        
        self.assertIsInstance(dimension, int)
        self.assertGreater(dimension, 0)


class TestFAISSStore(unittest.TestCase):
    """测试FAISS存储"""
    
    def setUp(self):
        self.store = FAISSStore(dimension=384)
    
    def test_store_initialization(self):
        """测试存储初始化"""
        self.assertIsNotNone(self.store.index)
        self.assertEqual(self.store.dimension, 384)
    
    def test_add_vectors(self):
        """测试添加向量"""
        test_vectors = [[0.1] * 384, [0.2] * 384]
        test_metadata = [{'doc_id': 'doc1'}, {'doc_id': 'doc2'}]
        
        self.store.add_vectors(test_vectors, test_metadata)
        
        stats = self.store.get_stats()
        self.assertEqual(stats['total_vectors'], 2)


if __name__ == '__main__':
    unittest.main()
