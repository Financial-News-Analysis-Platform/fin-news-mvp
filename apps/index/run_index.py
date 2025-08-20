"""
Index模块主运行脚本 - 负责分块、向量化和索引构建
"""
import os
import sys
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from apps.index.chunk import TextChunker, Chunk
from apps.index.embed import TextEmbedder, EmbeddingCache
from apps.index.faiss_store import FAISSStore, VectorStoreManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IndexingPipeline:
    """索引构建管道"""
    
    def __init__(self, 
                 chunk_size: int = 500,
                 overlap: int = 50,
                 model_name: str = "all-MiniLM-L6-v2"):
        """
        初始化索引管道
        
        Args:
            chunk_size: 块大小（token数）
            overlap: 重叠大小
            model_name: 向量化模型名称
        """
        self.chunker = TextChunker(max_tokens=chunk_size, overlap=overlap)
        self.embedder = TextEmbedder(model_name=model_name)
        self.cache = EmbeddingCache()
        
        # 初始化FAISS存储
        dimension = self.embedder.get_embedding_dimension()
        self.store = FAISSStore(dimension=dimension)
        self.manager = VectorStoreManager(self.store)
        
        logger.info(f"Indexing pipeline initialized with dimension: {dimension}")
    
    def process_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个文档
        
        Args:
            document: 文档数据
            
        Returns:
            处理结果
        """
        doc_id = document.get('id')
        text = document.get('body', '')
        
        logger.info(f"Processing document: {doc_id}")
        
        # 1. 文本分块
        chunks = self.chunker.split_text(text, doc_id)
        logger.info(f"Created {len(chunks)} chunks for document {doc_id}")
        
        # 2. 文本向量化
        chunk_texts = [chunk.text for chunk in chunks]
        embeddings = self.embedder.encode_batch(chunk_texts)
        logger.info(f"Generated embeddings: {embeddings.shape}")
        
        # 3. 准备元数据
        chunk_data = []
        for i, chunk in enumerate(chunks):
            chunk_dict = {
                'id': chunk.id,
                'chunk_index': chunk.chunk_index,
                'text': chunk.text,
                'tokens': chunk.tokens,
                'tickers': document.get('tickers', []),
                'published_at': document.get('published_at'),
                'source': document.get('source'),
                'url': document.get('url'),
                'title': document.get('title')
            }
            chunk_data.append(chunk_dict)
        
        # 4. 添加到向量存储
        self.manager.add_document_chunks(doc_id, chunk_data, embeddings)
        
        # 5. 保存索引
        self.store.save_index()
        
        return {
            'doc_id': doc_id,
            'chunks_created': len(chunks),
            'embeddings_generated': embeddings.shape[0],
            'status': 'success'
        }
    
    def process_batch(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量处理文档
        
        Args:
            documents: 文档列表
            
        Returns:
            处理结果列表
        """
        results = []
        
        for doc in documents:
            try:
                result = self.process_document(doc)
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing document {doc.get('id')}: {e}")
                results.append({
                    'doc_id': doc.get('id'),
                    'status': 'error',
                    'error': str(e)
                })
        
        return results
    
    def search_similar(self, query: str, k: int = 5,
                      ticker: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        搜索相似内容
        
        Args:
            query: 查询文本
            k: 返回结果数量
            ticker: 股票代码过滤
            
        Returns:
            搜索结果列表
        """
        # 向量化查询
        query_embedding = self.embedder.encode(query)
        
        # 执行搜索
        if ticker:
            distances, indices = self.store.search_by_ticker(query_embedding, ticker, k)
        else:
            distances, indices = self.store.search(query_embedding, k)
        
        # 构建结果
        results = []
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < len(self.store.metadata):
                metadata = self.store.metadata[idx]
                result = {
                    'rank': i + 1,
                    'similarity_score': float(dist),
                    'text': metadata.get('text', ''),
                    'doc_id': metadata.get('doc_id', ''),
                    'tickers': metadata.get('tickers', []),
                    'source': metadata.get('source', ''),
                    'url': metadata.get('url', '')
                }
                results.append(result)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        store_stats = self.store.get_stats()
        
        return {
            'total_documents': len(set(m.get('doc_id') for m in self.store.metadata)),
            'total_chunks': store_stats['total_vectors'],
            'embedding_dimension': store_stats['dimension'],
            'index_size_mb': self._get_index_size()
        }
    
    def _get_index_size(self) -> float:
        """获取索引文件大小（MB）"""
        index_path = os.path.join(self.store.index_dir, "faiss.index")
        if os.path.exists(index_path):
            return os.path.getsize(index_path) / (1024 * 1024)
        return 0.0


def main():
    """主函数 - 测试索引管道"""
    
    # 创建测试文档
    test_documents = [
        {
            'id': 'doc_001',
            'title': 'Apple Q3 Earnings Report',
            'body': '''
            Apple Inc. reported strong quarterly earnings today. The company's revenue 
            exceeded analyst expectations by 15%. iPhone sales were particularly strong, 
            with a 20% increase year-over-year. CEO Tim Cook expressed optimism about 
            the upcoming product launches. The stock price rose 5% in after-hours trading.
            
            Analysts are revising their price targets upward. Many believe Apple's 
            services business will continue to grow rapidly. The company's ecosystem 
            approach has proven successful in retaining customers.
            ''',
            'tickers': ['AAPL'],
            'published_at': datetime.now().isoformat(),
            'source': 'Reuters',
            'url': 'https://example.com/apple-earnings'
        },
        {
            'id': 'doc_002',
            'title': 'Tesla Production Update',
            'body': '''
            Tesla announced record vehicle production numbers for Q3. The company 
            delivered over 400,000 vehicles, exceeding previous guidance. Model Y 
            continues to be the best-selling electric vehicle globally. Production 
            efficiency improvements at Gigafactories contributed to the strong results.
            
            CEO Elon Musk highlighted the importance of scaling production while 
            maintaining quality. The company's focus on automation and vertical 
            integration has paid dividends.
            ''',
            'tickers': ['TSLA'],
            'published_at': datetime.now().isoformat(),
            'source': 'Yahoo Finance',
            'url': 'https://example.com/tesla-production'
        }
    ]
    
    # 初始化管道
    pipeline = IndexingPipeline(chunk_size=300, overlap=30)
    
    # 处理文档
    logger.info("Starting document processing...")
    results = pipeline.process_batch(test_documents)
    
    # 显示结果
    for result in results:
        logger.info(f"Document {result['doc_id']}: {result['status']}")
        if result['status'] == 'success':
            logger.info(f"  - Created {result['chunks_created']} chunks")
            logger.info(f"  - Generated {result['embeddings_generated']} embeddings")
    
    # 显示统计信息
    stats = pipeline.get_stats()
    logger.info(f"Index statistics: {stats}")
    
    # 测试搜索
    logger.info("Testing search functionality...")
    search_results = pipeline.search_similar("Apple earnings performance", k=3, ticker="AAPL")
    
    for result in search_results:
        logger.info(f"Rank {result['rank']}: {result['text'][:100]}...")
        logger.info(f"  Similarity: {result['similarity_score']:.4f}")
        logger.info(f"  Source: {result['source']}")


if __name__ == "__main__":
    main()
