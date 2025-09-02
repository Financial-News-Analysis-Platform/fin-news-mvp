"""
Index模块 - 金融新闻分析平台的核心索引构建模块

主要功能：
1. 文本分块 - 将长文档分割成适合向量化的块
2. 文本向量化 - 使用预训练模型生成文本向量
3. 向量存储 - 使用FAISS进行高效的向量索引和搜索
4. 批量处理 - 支持大规模文档的批量索引构建

核心组件：
- TextChunker: 智能文本分块器
- TextEmbedder: 文本向量化器
- FAISSStore: FAISS向量存储管理器
- build_index_aws: 生产级AWS索引构建器
"""

# 核心组件
from .chunk import TextChunker, Chunk
from .embed import TextEmbedder, EmbeddingCache
from .faiss_store import FAISSStore, VectorStoreManager
from .models import Document, ProcessingResult, DocumentStatus, SourceType

# 生产级索引构建器
from .build_index_aws import IndexBuilder

__all__ = [
    # 核心组件
    'TextChunker',
    'Chunk',
    'TextEmbedder', 
    'EmbeddingCache',
    'FAISSStore',
    'VectorStoreManager',
    
    # 数据模型
    'Document',
    'ProcessingResult',
    'DocumentStatus',
    'SourceType',
    
    # 生产级索引构建器
    'IndexBuilder'
]
