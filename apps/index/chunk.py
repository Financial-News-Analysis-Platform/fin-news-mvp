"""
文本分块模块 - 将长文本分割成适合向量化的片段
"""
import re
from typing import List, Dict, Any
from dataclasses import dataclass
import hashlib


@dataclass
class Chunk:
    """文本块数据结构"""
    id: str
    doc_id: str
    chunk_index: int
    text: str
    tokens: int
    metadata: Dict[str, Any]


class TextChunker:
    """文本分块器"""
    
    def __init__(self, max_tokens: int = 500, overlap: int = 50):
        self.max_tokens = max_tokens
        self.overlap = overlap
    
    def split_text(self, text: str, doc_id: str) -> List[Chunk]:
        """
        将文本分割成块
        
        Args:
            text: 输入文本
            doc_id: 文档ID
            
        Returns:
            Chunk列表
        """
        # 按句子分割
        sentences = self._split_sentences(text)
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        chunk_index = 0
        
        for sentence in sentences:
            sentence_tokens = len(sentence.split())  # 简单token计数
            
            if current_tokens + sentence_tokens > self.max_tokens and current_chunk:
                # 创建当前块
                chunk = self._create_chunk(
                    current_chunk, doc_id, chunk_index, current_tokens
                )
                chunks.append(chunk)
                
                # 保留重叠部分
                overlap_sentences = self._get_overlap_sentences(current_chunk)
                current_chunk = overlap_sentences
                current_tokens = sum(len(s.split()) for s in overlap_sentences)
                chunk_index += 1
            
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
        
        # 处理最后一个块
        if current_chunk:
            chunk = self._create_chunk(
                current_chunk, doc_id, chunk_index, current_tokens
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_sentences(self, text: str) -> List[str]:
        """按句子分割文本"""
        # 简单的句子分割规则
        sentence_pattern = r'[.!?]+'
        sentences = re.split(sentence_pattern, text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _get_overlap_sentences(self, sentences: List[str]) -> List[str]:
        """获取重叠的句子"""
        if len(sentences) <= self.overlap:
            return sentences
        return sentences[-self.overlap:]
    
    def _create_chunk(self, sentences: List[str], doc_id: str, 
                      chunk_index: int, tokens: int) -> Chunk:
        """创建Chunk对象"""
        text = ' '.join(sentences)
        chunk_id = self._generate_chunk_id(doc_id, chunk_index)
        
        return Chunk(
            id=chunk_id,
            doc_id=doc_id,
            chunk_index=chunk_index,
            text=text,
            tokens=tokens,
            metadata={
                'start_sentence': 0,
                'end_sentence': len(sentences),
                'overlap': self.overlap
            }
        )
    
    def _generate_chunk_id(self, doc_id: str, chunk_index: int) -> str:
        """生成唯一的块ID"""
        content = f"{doc_id}_{chunk_index}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


def estimate_tokens(text: str) -> int:
    """估算文本的token数量（简单版本）"""
    return len(text.split())


if __name__ == "__main__":
    # 测试代码
    chunker = TextChunker(max_tokens=300, overlap=30)
    
    sample_text = """
    Apple Inc. reported strong quarterly earnings today. The company's revenue 
    exceeded analyst expectations by 15%. iPhone sales were particularly strong, 
    with a 20% increase year-over-year. CEO Tim Cook expressed optimism about 
    the upcoming product launches. The stock price rose 5% in after-hours trading.
    
    Analysts are revising their price targets upward. Many believe Apple's 
    services business will continue to grow rapidly. The company's ecosystem 
    approach has proven successful in retaining customers.
    """
    
    chunks = chunker.split_text(sample_text, "doc_001")
    for chunk in chunks:
        print(f"Chunk {chunk.chunk_index}: {chunk.text[:100]}...")
        print(f"Tokens: {chunk.tokens}")
        print("---")
