"""
Index模块主运行脚本 - 负责分块、向量化和索引构建
"""
import os
import sys
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from apps.index.chunk import TextChunker, Chunk
from apps.index.embed import TextEmbedder, EmbeddingCache
from apps.index.faiss_store import FAISSStore, VectorStoreManager
from apps.index.models import Document, ProcessingResult, DocumentStatus
from apps.index.models import SourceType

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
    
    def process_document(self, document: Document) -> ProcessingResult:
        """
        处理单个文档
        
        Args:
            document: 文档数据
            
        Returns:
            处理结果
        """
        start_time = datetime.now()
        doc_id = document.id
        
        try:
            logger.info(f"Processing document: {doc_id}")
            
            # 1. 文本分块
            chunks = self.chunker.split_text(document.body, doc_id)
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
                    'tickers': document.tickers,
                    'published_at': document.published_at.isoformat(),
                    'source': document.source.value,
                    'url': document.url,
                    'title': document.title
                }
                chunk_data.append(chunk_dict)
            
            # 4. 添加到向量存储
            self.manager.add_document_chunks(doc_id, chunk_data, embeddings)
            
            # 5. 保存索引
            self.store.save_index()
            
            # 6. 更新文档状态
            document.status = DocumentStatus.COMPLETED
            document.updated_at = datetime.now()
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            result = ProcessingResult(
                document_id=doc_id,
                status=DocumentStatus.COMPLETED,
                chunks_created=len(chunks),
                embeddings_generated=len(embeddings),
                processing_time=processing_time
            )
            
            logger.info(f"Document {doc_id} processed successfully in {processing_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Error processing document {doc_id}: {e}")
            
            processing_time = (datetime.now() - start_time).total_seconds()
            document.status = DocumentStatus.FAILED
            document.updated_at = datetime.now()
            
            result = ProcessingResult(
                document_id=doc_id,
                status=DocumentStatus.FAILED,
                chunks_created=0,
                embeddings_generated=0,
                processing_time=processing_time,
                error_message=str(e)
            )
            
            return result
    
    def process_batch(self, documents: List[Document]) -> List[ProcessingResult]:
        """
        批量处理文档
        
        Args:
            documents: 文档列表
            
        Returns:
            处理结果列表
        """
        logger.info(f"Starting batch processing of {len(documents)} documents")
        
        results = []
        for i, doc in enumerate(documents):
            logger.info(f"Processing document {i+1}/{len(documents)}: {doc.id}")
            result = self.process_document(doc)
            results.append(result)
            
            # 每处理10个文档保存一次索引
            if (i + 1) % 10 == 0:
                self.store.save_index()
                logger.info(f"Saved index after processing {i+1} documents")
        
        # 最终保存索引
        self.store.save_index()
        logger.info(f"Batch processing completed. Results: {results}")
        
        return results
    
    def search_similar(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        搜索相似文档
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        try:
            # 1. 向量化查询
            query_embedding = self.embedder.encode([query])
            
            # 2. 搜索相似向量
            distances, indices = self.store.search(query_embedding, k=top_k)
            
            # 3. 格式化结果
            formatted_results = []
            for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
                if idx < len(self.store.metadata):
                    chunk_info = self.store.metadata[idx]
                    
                    formatted_results.append({
                        'chunk_id': chunk_info.get('chunk_id', f'chunk_{idx}'),
                        'similarity_score': 1.0 / (1.0 + distance),  # 将距离转换为相似度分数
                        'text': chunk_info.get('text', ''),
                        'tickers': chunk_info.get('tickers', []),
                        'source': chunk_info.get('source', ''),
                        'title': chunk_info.get('title', '')
                    })
            
            logger.info(f"Search completed, found {len(formatted_results)} results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def get_index_stats(self) -> Dict[str, Any]:
        """
        获取索引统计信息
        
        Returns:
            统计信息字典
        """
        try:
            stats = {
                'total_documents': self.manager.get_total_documents(),
                'total_chunks': self.manager.get_total_chunks(),
                'vector_dimension': self.embedder.get_embedding_dimension(),
                'index_size_mb': self.store.get_index_size_mb()
            }
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            return {}


def main():
    """主函数 - 测试索引管道"""
    try:
        # 创建测试文档
        test_documents = [
            Document(
                id="test_doc_1",
                title="Apple Reports Strong Q4 Earnings",
                body="Apple Inc. reported strong fourth-quarter earnings today, beating analyst expectations. The company's revenue grew 8% year-over-year, driven by strong iPhone sales and services growth. CEO Tim Cook highlighted the company's continued innovation in AI and machine learning.",
                published_at=datetime.now(),
                url="https://example.com/apple-earnings",
                source=SourceType.YAHOO_FINANCE,
                tickers=["AAPL"]
            ),
            Document(
                id="test_doc_2",
                title="Tesla Announces New Gigafactory",
                body="Tesla Motors announced plans to build a new Gigafactory in Texas, which will focus on producing the Cybertruck and Model Y. The facility is expected to create thousands of jobs and significantly increase Tesla's production capacity.",
                published_at=datetime.now(),
                url="https://example.com/tesla-gigafactory",
                source=SourceType.REUTERS,
                tickers=["TSLA"]
            )
        ]
        
        # 初始化管道
        pipeline = IndexingPipeline(chunk_size=300, overlap=30)
        
        # 处理文档
        logger.info("Starting document processing...")
        results = pipeline.process_batch(test_documents)
        
        # 显示结果
        for result in results:
            logger.info(f"Document {result.document_id}: {result.status}")
            logger.info(f"  Chunks created: {result.chunks_created}")
            logger.info(f"  Embeddings generated: {result.embeddings_generated}")
            logger.info(f"  Processing time: {result.processing_time:.2f}s")
        
        # 测试搜索
        logger.info("Testing search functionality...")
        search_results = pipeline.search_similar("Apple earnings", top_k=3)
        
        for i, result in enumerate(search_results):
            logger.info(f"Result {i+1}:")
            logger.info(f"  Score: {result['similarity_score']:.4f}")
            logger.info(f"  Text: {result['text'][:100]}...")
            logger.info(f"  Tickers: {result['tickers']}")
        
        # 显示索引统计
        stats = pipeline.get_index_stats()
        logger.info(f"Index statistics: {stats}")
        
        logger.info("Indexing pipeline test completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise


if __name__ == "__main__":
    main()
