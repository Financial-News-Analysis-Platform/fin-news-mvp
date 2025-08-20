"""
FAISS向量存储模块 - 管理向量索引和检索
"""
import os
import pickle
import numpy as np
import faiss
from typing import List, Dict, Any, Tuple, Optional
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FAISSStore:
    """FAISS向量存储管理器"""
    
    def __init__(self, index_dir: str = "data/faiss_index", 
                 dimension: int = 384):
        """
        初始化FAISS存储
        
        Args:
            index_dir: 索引文件目录
            dimension: 向量维度
        """
        self.index_dir = index_dir
        self.dimension = dimension
        self.index = None
        self.metadata = []
        
        os.makedirs(index_dir, exist_ok=True)
        self._load_or_create_index()
    
    def _load_or_create_index(self):
        """加载现有索引或创建新索引"""
        index_path = os.path.join(self.index_dir, "faiss.index")
        metadata_path = os.path.join(self.index_dir, "metadata.pkl")
        
        if os.path.exists(index_path) and os.path.exists(metadata_path):
            logger.info("Loading existing FAISS index")
            self.index = faiss.read_index(index_path)
            with open(metadata_path, 'rb') as f:
                self.metadata = pickle.load(f)
        else:
            logger.info("Creating new FAISS index")
            self.index = faiss.IndexFlatIP(self.dimension)  # 内积索引
            self.metadata = []
    
    def add_vectors(self, vectors: np.ndarray, 
                   metadata_list: List[Dict[str, Any]]) -> None:
        """
        添加向量到索引
        
        Args:
            vectors: 向量数组
            metadata_list: 对应的元数据列表
        """
        if self.index is None:
            raise ValueError("Index not initialized")
        
        if len(vectors) != len(metadata_list):
            raise ValueError("Vectors and metadata must have same length")
        
        # 添加向量到索引
        self.index.add(vectors)
        
        # 添加元数据
        self.metadata.extend(metadata_list)
        
        logger.info(f"Added {len(vectors)} vectors to index")
    
    def search(self, query_vector: np.ndarray, k: int = 5,
               filter_func: Optional[callable] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        搜索最相似的向量
        
        Args:
            query_vector: 查询向量
            k: 返回结果数量
            filter_func: 过滤函数
            
        Returns:
            (距离数组, 索引数组)
        """
        if self.index is None:
            raise ValueError("Index not initialized")
        
        # 确保查询向量是2D
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        
        # 执行搜索
        distances, indices = self.index.search(query_vector, k)
        
        # 应用过滤
        if filter_func:
            filtered_results = []
            for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
                if idx < len(self.metadata) and filter_func(self.metadata[idx]):
                    filtered_results.append((dist, idx))
            
            if filtered_results:
                distances = np.array([[d for d, _ in filtered_results]])
                indices = np.array([[i for _, i in filtered_results]])
            else:
                distances = np.array([[]])
                indices = np.array([[]])
        
        return distances, indices
    
    def search_by_ticker(self, query_vector: np.ndarray, ticker: str,
                        k: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """
        按ticker搜索
        
        Args:
            query_vector: 查询向量
            ticker: 股票代码
            k: 返回结果数量
            
        Returns:
            (距离数组, 索引数组)
        """
        def ticker_filter(metadata):
            return ticker in metadata.get('tickers', [])
        
        return self.search(query_vector, k, ticker_filter)
    
    def search_by_time_range(self, query_vector: np.ndarray, 
                           start_time: datetime, end_time: datetime,
                           k: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """
        按时间范围搜索
        
        Args:
            query_vector: 查询向量
            start_time: 开始时间
            end_time: 结束时间
            k: 返回结果数量
            
        Returns:
            (距离数组, 索引数组)
        """
        def time_filter(metadata):
            pub_time = metadata.get('published_at')
            if not pub_time:
                return False
            
            if isinstance(pub_time, str):
                pub_time = datetime.fromisoformat(pub_time.replace('Z', '+00:00'))
            
            return start_time <= pub_time <= end_time
        
        return self.search(query_vector, k, time_filter)
    
    def get_metadata(self, index: int) -> Optional[Dict[str, Any]]:
        """获取指定索引的元数据"""
        if 0 <= index < len(self.metadata):
            return self.metadata[index]
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        if self.index is None:
            return {"total_vectors": 0, "dimension": self.dimension}
        
        return {
            "total_vectors": self.index.ntotal,
            "dimension": self.index.d,
            "is_trained": self.index.is_trained
        }
    
    def save_index(self) -> None:
        """保存索引到磁盘"""
        if self.index is None:
            logger.warning("No index to save")
            return
        
        index_path = os.path.join(self.index_dir, "faiss.index")
        metadata_path = os.path.join(self.index_dir, "metadata.pkl")
        
        # 保存FAISS索引
        faiss.write_index(self.index, index_path)
        
        # 保存元数据
        with open(metadata_path, 'wb') as f:
            pickle.dump(self.metadata, f)
        
        logger.info(f"Index saved to {self.index_dir}")
    
    def clear_index(self) -> None:
        """清空索引"""
        if self.index is None:
            return
        
        self.index.reset()
        self.metadata.clear()
        logger.info("Index cleared")


class VectorStoreManager:
    """向量存储管理器"""
    
    def __init__(self, store: FAISSStore):
        self.store = store
    
    def add_document_chunks(self, doc_id: str, chunks: List[Dict[str, Any]],
                           embeddings: np.ndarray) -> None:
        """
        添加文档块到向量存储
        
        Args:
            doc_id: 文档ID
            chunks: 块列表
            embeddings: 对应的向量
        """
        metadata_list = []
        
        for i, chunk in enumerate(chunks):
            metadata = {
                'doc_id': doc_id,
                'chunk_id': chunk.get('id'),
                'chunk_index': chunk.get('chunk_index'),
                'text': chunk.get('text'),
                'tickers': chunk.get('tickers', []),
                'published_at': chunk.get('published_at'),
                'source': chunk.get('source'),
                'url': chunk.get('url')
            }
            metadata_list.append(metadata)
        
        self.store.add_vectors(embeddings, metadata_list)
    
    def search_similar(self, query: str, k: int = 5,
                      ticker: Optional[str] = None,
                      time_range: Optional[Tuple[datetime, datetime]] = None) -> List[Dict[str, Any]]:
        """
        搜索相似内容
        
        Args:
            query: 查询文本
            k: 返回结果数量
            ticker: 股票代码过滤
            time_range: 时间范围过滤
            
        Returns:
            搜索结果列表
        """
        # 这里需要先对查询文本进行向量化
        # 暂时返回空列表，实际使用时需要集成embedder
        return []


if __name__ == "__main__":
    # 测试代码
    store = FAISSStore(dimension=384)
    
    # 创建测试向量
    test_vectors = np.random.rand(10, 384).astype('float32')
    test_metadata = [
        {'doc_id': f'doc_{i}', 'tickers': ['AAPL'], 'published_at': datetime.now()}
        for i in range(10)
    ]
    
    # 添加向量
    store.add_vectors(test_vectors, test_metadata)
    
    # 搜索
    query_vector = np.random.rand(1, 384).astype('float32')
    distances, indices = store.search(query_vector, k=3)
    
    print(f"Search results: {indices}")
    print(f"Distances: {distances}")
    
    # 保存索引
    store.save_index()
