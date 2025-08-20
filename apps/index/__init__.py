"""
Index模块 - 负责文本分块、向量化和FAISS索引管理
"""

from .chunk import TextChunker, Chunk
from .embed import TextEmbedder, EmbeddingCache
from .faiss_store import FAISSStore, VectorStoreManager
from .run_index import IndexingPipeline
from .models import (
    SourceType, DocumentStatus, Document, Chunk as ChunkModel,
    Story, SearchResult, ProcessingResult,
    BatchProcessingRequest, BatchProcessingResponse
)

__all__ = [
    'TextChunker',
    'Chunk', 
    'TextEmbedder',
    'EmbeddingCache',
    'FAISSStore',
    'VectorStoreManager',
    'IndexingPipeline',
    # 数据模型
    'SourceType',
    'DocumentStatus', 
    'Document',
    'ChunkModel',
    'Story',
    'SearchResult',
    'ProcessingResult',
    'BatchProcessingRequest',
    'BatchProcessingResponse'
]

__version__ = '0.1.0'
