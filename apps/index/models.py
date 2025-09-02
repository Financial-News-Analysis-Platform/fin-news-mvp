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
    """统一新闻文档模型 - 用于索引处理"""
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


class Chunk(BaseModel):
    """文本分块模型"""
    id: str = Field(..., description="分块唯一ID")
    document_id: str = Field(..., description="所属文档ID")
    chunk_index: int = Field(..., description="分块索引")
    text: str = Field(..., description="分块文本内容")
    tokens: int = Field(..., description="token数量")
    start_char: int = Field(..., description="起始字符位置")
    end_char: int = Field(..., description="结束字符位置")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ProcessingResult(BaseModel):
    """文档处理结果"""
    document_id: str = Field(..., description="文档ID")
    status: DocumentStatus = Field(..., description="处理状态")
    chunks_created: int = Field(..., description="创建的分块数量")
    embeddings_generated: int = Field(..., description="生成的向量数量")
    processing_time: float = Field(..., description="处理耗时（秒）")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        } 