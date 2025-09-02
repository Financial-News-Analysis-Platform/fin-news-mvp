"""
LLM客户端工具 - 提供统一的LLM接口，支持OpenAI和本地开发
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM客户端，支持OpenAI和本地模拟"""
    
    def __init__(self):
        """初始化LLM客户端"""
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_available = bool(self.openai_api_key)
        
        if self.openai_available:
            logger.info("OpenAI API key found, using OpenAI for LLM calls")
        else:
            logger.info("No OpenAI API key found, using mock responses for local development")
    
    def summarize(self, context_items: List[Dict[str, Any]], instruction: str, model: str = "gpt-4o-mini") -> Dict[str, Any]:
        """
        生成摘要，支持OpenAI和本地模拟
        
        Args:
            context_items: 上下文项目列表，每个包含title, url, published_utc, text_snippet
            instruction: 摘要指令
            model: 模型名称（仅OpenAI使用）
            
        Returns:
            包含摘要信息的字典
        """
        start_time = datetime.now()
        
        try:
            if self.openai_available:
                return self._call_openai(context_items, instruction, model)
            else:
                return self._generate_mock_summary(context_items, instruction)
                
        except Exception as e:
            logger.error(f"LLM summarization failed: {e}")
            # 返回错误响应，但保持结构一致
            return {
                "summary": f"Error generating summary: {str(e)}",
                "bullets": ["Error occurred during summarization"],
                "sentiment": "neu",
                "sources": [],
                "error": str(e)
            }
        finally:
            llm_ms = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"LLM call completed in {llm_ms:.1f}ms")
    
    def _call_openai(self, context_items: List[Dict[str, Any]], instruction: str, model: str) -> Dict[str, Any]:
        """调用OpenAI API"""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=self.openai_api_key)
            
            # 构建上下文文本
            context_text = self._build_context_text(context_items)
            
            # 构建完整的提示
            full_prompt = f"""Based on the following news articles and context, {instruction}

Context:
{context_text}

Please provide:
1. A concise summary (1-2 sentences)
2. 5-7 key bullet points (facts, numbers, guidance, risks)
3. Overall sentiment (pos/neg/neu)
4. Source citations (title and URL for each source)

Format your response as JSON:
{{
    "summary": "your summary here",
    "bullets": ["point 1", "point 2", ...],
    "sentiment": "pos|neg|neu",
    "sources": [{{"title": "title1", "url": "url1"}}, ...]
}}"""

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a financial news analyst. Provide accurate, concise analysis in the requested JSON format."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            # 解析响应
            content = response.choices[0].message.content
            try:
                # 尝试提取JSON部分
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end != -1:
                        content = content[json_start:json_end].strip()
                
                result = json.loads(content)
                return result
                
            except json.JSONDecodeError:
                # 如果JSON解析失败，尝试从文本中提取信息
                logger.warning("Failed to parse OpenAI response as JSON, extracting from text")
                return self._extract_from_text(content, context_items)
                
        except ImportError:
            logger.error("OpenAI package not installed. Install with: pip install openai")
            return self._generate_mock_summary(context_items, instruction)
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return self._generate_mock_summary(context_items, instruction)
    
    def _generate_mock_summary(self, context_items: List[Dict[str, Any]], instruction: str) -> Dict[str, Any]:
        """生成模拟摘要（用于本地开发）"""
        # 基于上下文项目生成确定性的模拟响应
        titles = [item.get("title", "") for item in context_items]
        urls = [item.get("url", "") for item in context_items]
        
        # 简单的模拟逻辑
        if "earnings" in instruction.lower() or "revenue" in instruction.lower():
            sentiment = "pos"
            summary = "Company reported strong financial performance with positive outlook."
            bullets = [
                "Revenue exceeded analyst expectations",
                "Strong growth in key business segments",
                "Positive guidance for upcoming quarters",
                "Market reaction was favorable",
                "Competitive position remains strong"
            ]
        elif "risk" in instruction.lower() or "concern" in instruction.lower():
            sentiment = "neg"
            summary = "Several risk factors identified that require attention."
            bullets = [
                "Regulatory challenges ahead",
                "Supply chain disruptions possible",
                "Market volatility concerns",
                "Competition intensifying",
                "Economic headwinds expected"
            ]
        else:
            sentiment = "neu"
            summary = "Mixed developments with both positive and negative factors."
            bullets = [
                "Company announced new strategic initiatives",
                "Market conditions remain uncertain",
                "Analyst opinions are divided",
                "Performance metrics show mixed results",
                "Future outlook depends on external factors"
            ]
        
        sources = [{"title": title, "url": url} for title, url in zip(titles, urls) if title and url and str(url) != 'nan']
        
        return {
            "summary": summary,
            "bullets": bullets,
            "sentiment": sentiment,
            "sources": sources
        }
    
    def _build_context_text(self, context_items: List[Dict[str, Any]]) -> str:
        """构建上下文文本"""
        context_parts = []
        
        for i, item in enumerate(context_items, 1):
            title = item.get("title", "")
            url = item.get("url", "")
            published_utc = item.get("published_utc", "")
            text_snippet = item.get("text_snippet", "")
            
            # 截断文本片段到约300个token（粗略估计：1 token ≈ 4字符）
            if len(text_snippet) > 1200:
                text_snippet = text_snippet[:1200] + "..."
            
            context_part = f"""Source {i}:
Title: {title}
URL: {url}
Published: {published_utc}
Content: {text_snippet}

"""
            context_parts.append(context_part)
        
        return "\n".join(context_parts)
    
    def _extract_from_text(self, text: str, context_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """从文本响应中提取信息（备用方案）"""
        # 简单的文本解析逻辑
        sentiment = "neu"
        if "positive" in text.lower() or "good" in text.lower() or "strong" in text.lower():
            sentiment = "pos"
        elif "negative" in text.lower() or "bad" in text.lower() or "weak" in text.lower():
            sentiment = "neg"
        
        # 提取标题和URL作为来源
        sources = []
        for item in context_items:
            title = item.get("title", "")
            url = item.get("url", "")
            if title and url and str(url) != 'nan':
                sources.append({"title": title, "url": url})
        
        return {
            "summary": text[:200] + "..." if len(text) > 200 else text,
            "bullets": [text[i:i+100] for i in range(0, min(len(text), 500), 100)],
            "sentiment": sentiment,
            "sources": sources
        }


# 全局LLM客户端实例
llm_client = LLMClient()
