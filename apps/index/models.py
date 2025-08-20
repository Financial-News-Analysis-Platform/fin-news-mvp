"""
数据模型定义 - 金融新闻分析平台的核心数据结构
"""
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum


class SourceType(str, Enum):
    """数据源类型"""
    YAHOO_FINANCE = "yahoo_finance"
    REUTERS = "reuters"
    SEC_EDGAR = "sec_edgar"
    BLOOMBERG = "bloomberg"
    CNBC = "cnbc"


class DocumentStatus(str, Enum):
    """文档处理状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(BaseModel):
    """原始新闻文档模型"""
    id: str = Field(..., description="唯一文档ID")
    title: str = Field(..., description="新闻标题")
    body: str = Field(..., description="新闻正文内容")
    published_at: datetime = Field(..., description="发布时间")
    url: str = Field(..., description="新闻链接")
    source: SourceType = Field(..., description="数据源")
    tickers: List[str] = Field(default_factory=list, description="相关股票代码")
    
    # 元数据字段
    author: Optional[str] = Field(None, description="作者")
    summary: Optional[str] = Field(None, description="摘要")
    category: Optional[str] = Field(None, description="新闻分类")
    sentiment: Optional[float] = Field(None, description="情感分数", ge=-1, le=1)
    
    # 处理状态
    status: DocumentStatus = Field(default=DocumentStatus.PENDING, description="处理状态")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    
    @validator('tickers')
    def validate_tickers(cls, v):
        """验证股票代码格式"""
        for ticker in v:
            if not ticker.isalpha():
                raise ValueError(f"Invalid ticker format: {ticker}")
        return [ticker.upper() for ticker in v]
    
    @validator('body')
    def validate_body(cls, v):
        """验证正文不为空"""
        if not v or len(v.strip()) < 10:
            raise ValueError("Document body must be at least 10 characters")
        return v.strip()
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class Chunk(BaseModel):
    """文本分块模型"""
    id: str = Field(..., description="唯一块ID")
    doc_id: str = Field(..., description="所属文档ID")
    chunk_index: int = Field(..., description="块在文档中的索引")
    text: str = Field(..., description="块文本内容")
    tokens: int = Field(..., description="token数量")
    
    # 向量相关
    embedding: Optional[List[float]] = Field(None, description="向量表示")
    embedding_dimension: Optional[int] = Field(None, description="向量维度")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    start_sentence: int = Field(0, description="起始句子索引")
    end_sentence: int = Field(0, description="结束句子索引")
    overlap: int = Field(0, description="与前一块的重叠大小")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    
    @validator('text')
    def validate_text(cls, v):
        """验证文本不为空"""
        if not v or len(v.strip()) < 5:
            raise ValueError("Chunk text must be at least 5 characters")
        return v.strip()
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class Story(BaseModel):
    """新闻故事模型 - RAG生成的结果"""
    id: str = Field(..., description="唯一故事ID")
    title: str = Field(..., description="故事标题")
    summary: str = Field(..., description="故事摘要")
    
    # 关联信息
    doc_ids: List[str] = Field(..., description="相关文档ID列表")
    chunk_ids: List[str] = Field(..., description="相关块ID列表")
    tickers: List[str] = Field(..., description="相关股票代码")
    
    # 结构化数据
    key_events: List[Dict[str, Any]] = Field(default_factory=list, description="关键事件")
    entities: List[Dict[str, Any]] = Field(default_factory=list, description="实体信息")
    sentiment: Optional[float] = Field(None, description="整体情感分数", ge=-1, le=1)
    
    # 时间信息
    event_date: Optional[datetime] = Field(None, description="事件发生时间")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    
    # 来源信息
    sources: List[str] = Field(default_factory=list, description="数据源列表")
    confidence_score: float = Field(..., description="置信度分数", ge=0, le=1)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SearchResult(BaseModel):
    """搜索结果模型"""
    rank: int = Field(..., description="排名")
    similarity_score: float = Field(..., description="相似度分数")
    chunk: Chunk = Field(..., description="相关文本块")
    document: Document = Field(..., description="相关文档")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ProcessingResult(BaseModel):
    """文档处理结果模型"""
    doc_id: str = Field(..., description="文档ID")
    status: DocumentStatus = Field(..., description="处理状态")
    chunks_created: int = Field(0, description="创建的块数量")
    embeddings_generated: int = Field(0, description="生成的向量数量")
    error: Optional[str] = Field(None, description="错误信息")
    processing_time: Optional[float] = Field(None, description="处理时间（秒）")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# 批量处理模型
class BatchProcessingRequest(BaseModel):
    """批量处理请求模型"""
    documents: List[Document] = Field(..., description="待处理文档列表")
    chunk_size: int = Field(default=500, description="分块大小")
    overlap: int = Field(default=50, description="重叠大小")
    model_name: str = Field(default="all-MiniLM-L6-v2", description="向量化模型名称")


class BatchProcessingResponse(BaseModel):
    """批量处理响应模型"""
    total_documents: int = Field(..., description="总文档数")
    successful: int = Field(..., description="成功处理数")
    failed: int = Field(..., description="失败处理数")
    results: List[ProcessingResult] = Field(..., description="处理结果列表")
    total_processing_time: float = Field(..., description="总处理时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# 导出所有模型
__all__ = [
    'SourceType',
    'DocumentStatus', 
    'Document',
    'Chunk',
    'Story',
    'SearchResult',
    'ProcessingResult',
    'BatchProcessingRequest',
    'BatchProcessingResponse'
] 