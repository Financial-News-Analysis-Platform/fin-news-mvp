"""
文本分块模块 - 将长文本分割成适合向量化的片段
优化版本：专为金融新闻RAG场景设计
支持 BlingFire 句子分割器，自动回退到正则表达式分割器
"""
import re
import logging
from typing import List, Dict, Any
from dataclasses import dataclass
import tiktoken
import hashlib

# 设置日志
logger = logging.getLogger(__name__)

@dataclass
class Chunk:
    """文本块数据结构"""
    id: str
    doc_id: str
    chunk_index: int
    text: str
    tokens: int
    metadata: Dict[str, Any]


# 使用 cl100k_base 编码器进行 token 计数
ENC = tiktoken.get_encoding("cl100k_base")

# 改进的正则表达式句子分割器（回退方案）
# 减少缩写、小数等周围的错误分割
_SENT_SPLIT = re.compile(
    r'(?<=[。！？；…!?;])\s+|(?<=[\.\?\!])\s+(?=[A-Z0-9"("])'
)

# 样板文本清理模式
BOILERPLATE_PAT = re.compile(
    r"(subscribe|sign up|copyright|all rights reserved|share this|follow us|newsletter|cookie|privacy policy|terms of service|contact us|advertisement|sponsored|click here|read more|continue reading)",
    re.I
)

def clean_body(text: str) -> str:
    """清理文本中的样板内容"""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    lines = [ln for ln in lines if not BOILERPLATE_PAT.search(ln)]
    return "\n".join(lines)

def _tok_len(s: str) -> int:
    """计算文本的 token 数量"""
    return len(ENC.encode(s or ""))

def _tail_tokens(text: str, n_tokens: int) -> str:
    """获取文本末尾的 n_tokens 个 token"""
    toks = ENC.encode(text or "")
    return ENC.decode(toks[max(0, len(toks)-n_tokens):])

class TextChunker:
    """
    文本分块器 - 专为金融新闻RAG优化
    
    关键特性：
    - 基于 token 计数，非单词计数
    - 可选 BlingFire 句子分割器，自动回退到正则表达式
    - 智能句子分割，减少错误分割
    - 重叠机制，提高检索连续性
    - 孤儿块处理，确保块大小合理
    
    参数说明：
    - target_tokens: 目标块大小（新闻场景最佳点）
    - max_tokens: 最大块大小
    - overlap_tokens: 重叠 token 数
    - min_tokens: 最小块大小
    - use_blingfire: 是否使用 BlingFire 句子分割器
    """
    
    def __init__(self,
                 target_tokens: int = 360,      # 目标块大小（新闻场景最佳点）
                 max_tokens: int = 460,         # 最大块大小
                 overlap_tokens: int = 40,      # 重叠 token 数
                 min_tokens: int = 200,         # 最小块大小
                 use_blingfire: bool = True):   # 是否使用 BlingFire 分割器
        self.target = target_tokens
        self.max = max_tokens
        self.overlap = overlap_tokens
        self.min_tokens = min_tokens
        self.use_blingfire = use_blingfire

    def _split_sentences_bf(self, text: str) -> List[str]:
        """
        使用 BlingFire 进行句子分割
        
        如果 BlingFire 可用，使用其进行高质量句子分割
        对中文标点符号进行额外处理
        """
        try:
            from blingfire import text_to_sentences
            raw = text_to_sentences(text or "").splitlines()
            
            # 对中文标点符号进行额外分割
            chinese_split = re.compile(r'(?<=[。！？；…])\s*')
            sentences = []
            for line in raw:
                if line.strip():
                    # 按中文标点进一步分割
                    chinese_sents = chinese_split.split(line)
                    sentences.extend([s.strip() for s in chinese_sents if s.strip()])
            
            return sentences
            
        except ImportError:
            raise ImportError("BlingFire not available")
        except Exception as e:
            raise Exception(f"BlingFire error: {e}")

    def _split_sentences(self, text: str) -> List[str]:
        """
        智能句子分割方法
        
        优先使用 BlingFire（如果可用且启用），否则使用正则表达式回退
        处理中英文混合文本，减少缩写、小数等周围的错误分割
        """
        if self.use_blingfire:
            try:
                return self._split_sentences_bf(text)
            except (ImportError, Exception) as e:
                logger.debug(f"BlingFire unavailable, falling back to regex splitter: {e}")
                # 回退到正则表达式分割器
                pass
        
        # 使用正则表达式分割器
        sents = _SENT_SPLIT.split((text or "").strip())
        return [s.strip() for s in sents if s and s.strip()]

    def split_text(self, text: str, doc_id: str, title: str = "") -> List["Chunk"]:
        """
        主要的分块逻辑
        
        流程：
        1. 清理样板内容
        2. 标题并入首块（提升检索召回率）
        3. 按句子分块，控制 token 数量
        4. 处理孤儿块（借用 token 或合并）
        5. 重新编号和计算 token 数量
        
        关键特性：
        - 基于 token 的大小控制
        - 首块包含标题
        - token 级别的重叠机制
        - 智能孤儿块处理：先借用，再合并（如果可能）
        """
        # 1) 清理样板内容
        text = clean_body(text)
        
        # 2) 标题并入首块，提升检索召回率
        if title:
            text = (title.strip() + " —— " + (text or "")).strip()

        sents = self._split_sentences(text)
        chunks, cur, cur_tok = [], [], 0
        idx = 0

        for s in sents:
            sl = _tok_len(s)
            
            # 如果当前块加上新句子会超过 max_tokens，则创建新块
            if cur and cur_tok + sl > self.max:
                # 创建当前块
                chunk_text = " ".join(cur)
                chunks.append(self._create_chunk(chunk_text, doc_id, idx))
                idx += 1
                
                # 新块起始添加重叠内容
                if self.overlap > 0:
                    tail = _tail_tokens(chunk_text, self.overlap)
                    cur = [tail, s]
                    cur_tok = _tok_len(tail) + sl
                else:
                    cur = [s]
                    cur_tok = sl
            else:
                cur.append(s)
                cur_tok += sl

        # 处理最后一个块
        if cur:
            chunk_text = " ".join(cur)
            chunks.append(self._create_chunk(chunk_text, doc_id, idx))

        # 3) 处理孤儿块
        chunks = self._handle_orphan_chunks(chunks, doc_id)

        # 4) 重新编号 chunk_index 和重新计算 token 数量
        for i, c in enumerate(chunks):
            c.chunk_index = i
            c.tokens = _tok_len(c.text)  # 重新计算 token 数量

        return chunks

    def _handle_orphan_chunks(self, chunks: List["Chunk"], doc_id: str) -> List["Chunk"]:
        """
        处理孤儿块：确保最后一块达到最小 token 要求
        
        策略：
        1. 尝试从前一块借用 token（有安全下限保护）
        2. 如果借用后仍太小，且合并后不超过 max_tokens，则合并
        3. 否则保持分离
        
        安全机制：
        - safe_prev_floor = max(0, target_tokens - 40) 防止过度借用
        - 只在前一块有足够 token 时才借用
        """
        if len(chunks) < 2:
            return chunks
            
        last_chunk = chunks[-1]
        prev_chunk = chunks[-2]
        
        # 如果最后一块太小
        if last_chunk.tokens < self.min_tokens:
            # 计算需要的 token 数量
            need = self.min_tokens - last_chunk.tokens
            
            # 安全下限：防止过度借用
            safe_prev_floor = max(0, self.target - 40)
            
            # 计算前一块可以给出的 token 数量
            can_give = max(0, prev_chunk.tokens - safe_prev_floor)
            
            # 实际借用的 token 数量
            give = min(need, can_give)
            
            if give > 0:
                # 从前一块借用 token
                borrowed_text = _tail_tokens(prev_chunk.text, give + self.overlap)
                new_last_text = borrowed_text + " " + last_chunk.text
                
                # 更新前一块
                prev_chunk.text = prev_chunk.text[:-len(borrowed_text)].strip()
                prev_chunk.tokens = _tok_len(prev_chunk.text)
                
                # 更新最后一块
                last_chunk.text = new_last_text
                last_chunk.tokens = _tok_len(new_last_text)
                
                # 检查是否可以合并
                if prev_chunk.tokens + last_chunk.tokens <= self.max:
                    # 合并到前一块
                    merged_text = (prev_chunk.text + " " + last_chunk.text).strip()
                    prev_chunk.text = merged_text
                    prev_chunk.tokens = _tok_len(merged_text)
                    chunks.pop()  # 移除最后一块
                
        return chunks

    def _create_chunk(self, text: str, doc_id: str, chunk_index: int) -> "Chunk":
        """创建文本块对象"""
        chunk_id = self._generate_chunk_id(doc_id, chunk_index)
        return Chunk(
            id=chunk_id,
            doc_id=doc_id,
            chunk_index=chunk_index,
            text=text,
            tokens=_tok_len(text),
            metadata={"overlap_tokens": self.overlap}
        )

    def _generate_chunk_id(self, doc_id: str, chunk_index: int) -> str:
        """生成唯一的块ID"""
        content = f"{doc_id}_{chunk_index}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


def estimate_tokens(text: str) -> int:
    """估算文本的token数量（使用 tiktoken）"""
    return _tok_len(text)


if __name__ == "__main__":
    # 测试代码
    chunker = TextChunker(
        target_tokens=360,
        max_tokens=460, 
        overlap_tokens=40,
        min_tokens=200,
        use_blingfire=True  # 启用 BlingFire（如果可用）
    )
    
    sample_text = """
    Apple Inc. reported strong quarterly earnings today. The company's revenue 
    exceeded analyst expectations by 15%. iPhone sales were particularly strong, 
    with a 20% increase year-over-year. CEO Tim Cook expressed optimism about 
    the upcoming product launches. The stock price rose 5% in after-hours trading.
    
    Analysts are revising their price targets upward. Many believe Apple's 
    services business will continue to grow rapidly. The company's ecosystem 
    approach has proven successful in retaining customers.
    
    美联储或将按兵不动。美联储表示在通胀回落和就业市场稳定的情况下，
    可能维持当前利率水平不变。市场预期美联储将在下次会议上保持利率不变。
    """
    
    chunks = chunker.split_text(sample_text, "doc_001", title="Apple Q3 Earnings Beat Expectations")
    for chunk in chunks:
        print(f"Chunk {chunk.chunk_index}: {chunk.text[:100]}...")
        print(f"Tokens: {chunk.tokens}")
        print("---")
