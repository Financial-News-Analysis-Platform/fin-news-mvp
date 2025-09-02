#!/usr/bin/env python3
"""
AWS数据读取器 - 从DynamoDB和S3读取新闻数据
"""
import os
import json
import boto3
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class AWSDataReader:
    """AWS数据读取器"""
    
    def __init__(self, 
                 table_name: str = "news_documents",
                 bucket_name: str = "fin-news-raw-yz",
                 region: str = "us-east-2"):
        """
        初始化AWS数据读取器
        
        Args:
            table_name: DynamoDB表名
            bucket_name: S3存储桶名
            region: AWS区域
        """
        self.table_name = table_name
        self.bucket_name = bucket_name
        self.region = region
        
        # 初始化AWS客户端
        try:
            self.ddb = boto3.resource('dynamodb', region_name=region).Table(table_name)
            self.s3 = boto3.client('s3', region_name=region)
            logger.info(f"AWS客户端初始化成功: {table_name}, {bucket_name}")
        except Exception as e:
            logger.error(f"AWS客户端初始化失败: {e}")
            raise
    
    def get_document_metadata(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        从DynamoDB获取文档元数据
        
        Args:
            doc_id: 文档ID
            
        Returns:
            文档元数据字典，如果不存在返回None
        """
        try:
            response = self.ddb.get_item(Key={"doc_id": doc_id})
            if "Item" in response:
                return response["Item"]
            return None
        except Exception as e:
            logger.error(f"获取文档元数据失败 {doc_id}: {e}")
            return None
    
    def get_document_body(self, s3_key: str) -> Optional[str]:
        """
        从S3获取文档正文
        
        Args:
            s3_key: S3对象键
            
        Returns:
            文档正文文本，如果获取失败返回None
        """
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            body = response['Body'].read().decode('utf-8')
            return body
        except Exception as e:
            logger.error(f"获取文档正文失败 {s3_key}: {e}")
            return None
    
    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        获取完整文档（元数据+正文）
        
        Args:
            doc_id: 文档ID
            
        Returns:
            完整文档字典，包含所有字段
        """
        try:
            # 1. 获取元数据
            metadata = self.get_document_metadata(doc_id)
            if not metadata:
                logger.warning(f"文档元数据不存在: {doc_id}")
                return None
            
            # 2. 获取正文
            s3_key = metadata.get('s3_key')
            if not s3_key:
                logger.warning(f"文档缺少S3键: {doc_id}")
                return None
            
            body = self.get_document_body(s3_key)
            if not body:
                logger.warning(f"文档正文获取失败: {doc_id}")
                return None
            
            # 3. 合并数据
            document = metadata.copy()
            document['body'] = body
            
            # 4. 字段映射（适配现有代码）
            document['published_at'] = metadata.get('published_utc', '')
            document['provider'] = metadata.get('source', '')  # 临时映射
            
            logger.info(f"成功获取文档: {doc_id}, 正文长度: {len(body)}")
            return document
            
        except Exception as e:
            logger.error(f"获取完整文档失败 {doc_id}: {e}")
            return None
    
    def list_documents(self, limit: int = 100) -> List[str]:
        """
        列出可用的文档ID列表
        
        Args:
            limit: 最大返回数量
            
        Returns:
            文档ID列表
        """
        try:
            response = self.ddb.scan(
                Limit=limit,
                ProjectionExpression="doc_id"
            )
            
            doc_ids = [item['doc_id'] for item in response.get('Items', [])]
            logger.info(f"找到 {len(doc_ids)} 个文档")
            return doc_ids
            
        except Exception as e:
            logger.error(f"列出文档失败: {e}")
            return []
    
    def get_documents_batch(self, doc_ids: List[str]) -> List[Dict[str, Any]]:
        """
        批量获取文档
        
        Args:
            doc_ids: 文档ID列表
            
        Returns:
            文档列表
        """
        documents = []
        for doc_id in doc_ids:
            doc = self.get_document(doc_id)
            if doc:
                documents.append(doc)
            else:
                logger.warning(f"跳过失败的文档: {doc_id}")
        
        logger.info(f"成功获取 {len(documents)}/{len(doc_ids)} 个文档")
        return documents


# 测试函数
def test_aws_reader():
    """测试AWS数据读取器"""
    try:
        # 创建读取器
        reader = AWSDataReader()
        
        # 列出文档
        doc_ids = reader.list_documents(limit=5)
        print(f"找到文档: {doc_ids}")
        
        if doc_ids:
            # 获取第一个文档
            doc = reader.get_document(doc_ids[0])
            if doc:
                print(f"文档标题: {doc.get('title', 'N/A')}")
                print(f"文档正文长度: {len(doc.get('body', ''))}")
                print(f"股票代码: {doc.get('matched_tickers', [])}")
                print(f"关联强度: {doc.get('link_strength', 'N/A')}")
        
    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    test_aws_reader() 