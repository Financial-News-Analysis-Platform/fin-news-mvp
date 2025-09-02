"""
文本向量化模块 - 将文本转换为向量表示
"""
import os
import numpy as np
from typing import List, Union, Optional
from sentence_transformers import SentenceTransformer
import torch
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_norm(vecs: np.ndarray):
    norms = np.linalg.norm(vecs, axis=1)
    return float(norms.mean()), float(np.percentile(norms,5)), float(np.percentile(norms,95))

class TextEmbedder:
    """文本向量化器"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", 
                 device: Optional[str] = None):
        """
        初始化向量化器
        
        Args:
            model_name: 模型名称
            device: 设备类型 ('cpu', 'cuda', 'mps')
        """
        self.model_name = model_name
        self.device = device or self._get_device()
        
        logger.info(f"Loading model: {model_name}")
        self.model = SentenceTransformer(model_name, device=self.device)
        logger.info(f"Model loaded successfully on {self.device}")
    
    def _get_device(self) -> str:
        """自动检测最佳设备"""
        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return "mps"
        else:
            return "cpu"
    
    def encode(self, texts: Union[str, List[str]], 
               normalize: bool = True) -> np.ndarray:
        """
        将文本编码为向量
        
        Args:
            texts: 单个文本或文本列表
            normalize: 是否归一化向量
            
        Returns:
            向量数组
        """
        if isinstance(texts, str):
            texts = [texts]
        
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            
            if normalize:
                embeddings = self._normalize_embeddings(embeddings)
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Error encoding texts: {e}")
            raise
    
    def encode_batch(self, texts: List[str], batch_size: int = 64,  # 优化：从32改为64
                     normalize: bool = True) -> np.ndarray:
        """
        批量编码文本
        
        Args:
            texts: 文本列表
            batch_size: 批处理大小
            normalize: 是否归一化向量
            
        Returns:
            向量数组
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self.encode(batch, normalize=normalize)
            all_embeddings.append(batch_embeddings)
        
        return np.vstack(all_embeddings)
    
    def _normalize_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """归一化向量"""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # 避免除零
        return embeddings / norms
    
    def get_embedding_dimension(self) -> int:
        """获取向量维度"""
        return self.model.get_sentence_embedding_dimension()
    
    def similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算两个向量的余弦相似度"""
        if vec1.ndim == 1:
            vec1 = vec1.reshape(1, -1)
        if vec2.ndim == 1:
            vec2 = vec2.reshape(1, -1)
        
        # 确保向量已归一化
        vec1_norm = vec1 / np.linalg.norm(vec1, axis=1, keepdims=True)
        vec2_norm = vec2 / np.linalg.norm(vec2, axis=1, keepdims=True)
        
        return np.dot(vec1_norm, vec2_norm.T)[0, 0]


class EmbeddingCache:
    """向量缓存管理器"""
    
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def save_embeddings(self, embeddings: np.ndarray, 
                        filename: str) -> str:
        """保存向量到文件"""
        filepath = os.path.join(self.cache_dir, filename)
        np.save(filepath, embeddings)
        return filepath
    
    def load_embeddings(self, filename: str) -> np.ndarray:
        """从文件加载向量"""
        filepath = os.path.join(self.cache_dir, filename)
        return np.load(filepath)
    
    def get_cache_path(self, filename: str) -> str:
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, filename)


if __name__ == "__main__":
    # 测试代码
    embedder = TextEmbedder()
    
    test_texts = [
        "Apple Inc. reported strong quarterly earnings today.",
        "The company's revenue exceeded analyst expectations by 15%.",
        "iPhone sales were particularly strong with a 20% increase."
    ]
    
    # 编码单个文本
    single_embedding = embedder.encode(test_texts[0])
    print(f"Single embedding shape: {single_embedding.shape}")
    
    # 批量编码
    batch_embeddings = embedder.encode_batch(test_texts)
    print(f"Batch embeddings shape: {batch_embeddings.shape}")
    
    # 计算相似度
    sim = embedder.similarity(batch_embeddings[0], batch_embeddings[1])
    print(f"Similarity between first two texts: {sim:.4f}")
