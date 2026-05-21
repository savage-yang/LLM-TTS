from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator, Tuple
import openai
import requests
import json
import logging

logger = logging.getLogger(__name__)


class LLM(ABC):
    """LLM 抽象基类，定义通用接口"""

    @abstractmethod
    def response(self, dialogue: List[Dict[str, str]]) -> Generator[str, None, None]:
        """
        流式生成文本响应
        
        Args:
            dialogue: 对话历史列表
        
        Yields:
            生成的文本片段
        """
        pass

    @abstractmethod
    def response_call(
        self, 
        dialogue: List[Dict[str, str]], 
        functions_call: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[Tuple[Optional[str], Optional[Any]], None, None]:
        """
        流式生成响应，支持工具调用
        
        Args:
            dialogue: 对话历史列表
            functions_call: 工具定义列表 (兼容旧接口)
            tools: 工具定义列表
        
        Yields:
            (content, tool_calls) 元组
        """
        pass


class OpenAILLM(LLM):
    """OpenAI API 实现，兼容 DeepSeek 等兼容 API"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 OpenAI 客户端

        Args:
            config: 配置字典，包含 model_name, api_key, url, enable_thinking
        """
        self.model_name = config.get("model_name")
        self.api_key = config.get("api_key")
        self.base_url = config.get("url")
        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

        self.extra_body = {}
        enable_thinking = config.get("enable_thinking")
        if enable_thinking is not None:
            self.extra_body["enable_thinking"] = enable_thinking

        self._warmup()

    def _warmup(self):
        """预热LLM连接，触发HTTP/TLS握手和API服务端冷启动"""
        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "hi"}],
                stream=False,
                max_tokens=1,
                extra_body=self.extra_body,
            )
            logger.info(f"LLM预热完成，模型: {self.model_name}")
        except Exception as e:
            logger.warning(f"LLM预热失败（不影响正常使用）: {e}")

    def response(self, dialogue: List[Dict[str, str]]) -> Generator[str, None, None]:
        try:
            responses = self.client.chat.completions.create(
                model=self.model_name,
                messages=dialogue,
                stream=True,
                extra_body=self.extra_body
            )
            for chunk in responses:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            logger.error(f"OpenAILLM response error: {e}")
            raise

    def response_call(
        self,
        dialogue: List[Dict[str, str]],
        functions_call: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[Tuple[Optional[str], Optional[Any]], None, None]:
        actual_tools = tools or functions_call
        try:
            responses = self.client.chat.completions.create(
                model=self.model_name,
                messages=dialogue,
                stream=True,
                tools=actual_tools,
                **self.extra_body
            )
            for chunk in responses:
                delta = chunk.choices[0].delta
                yield delta.content, delta.tool_calls
        except Exception as e:
            logger.error(f"OpenAILLM response_call error: {e}")
            raise


class LocalLLM(LLM):
    """通用本地LLM客户端，兼容所有OpenAI Chat Completions API格式的推理服务
    支持：Ollama、vLLM、LM Studio、FastChat、Text Generation WebUI等
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化本地LLM客户端
        
        Args:
            config: 配置字典，包含 model_name, url, api_key(可选)
        """
        self.model_name = config.get("model_name", "qwen2.5")
        self.base_url = config.get("url", "http://localhost:11434/api/chat")
        self.api_key = config.get("api_key", None)
        self._warmup()

    def _warmup(self):
        """预热本地LLM连接，触发服务端模型加载"""
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "max_tokens": 1,
            }
            resp = requests.post(self.base_url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            logger.info(f"本地LLM预热完成，模型: {self.model_name}")
        except Exception as e:
            logger.warning(f"本地LLM预热失败（不影响正常使用）: {e}")

    def response(self, dialogue: List[Dict[str, str]]) -> Generator[str, None, None]:
        payload = {
            "model": self.model_name,
            "messages": dialogue,
            "stream": True,
            "temperature": 0.7
        }
        headers = {
            "Content-Type": "application/json"
        }
        # 只有配置了API Key的时候才加Authorization头
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.post(self.base_url, json=payload, headers=headers, stream=True, timeout=30)
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                data = json.loads(line.decode())
                content = data.get("message", {}).get("content")
                if content:
                    yield content
        except Exception as e:
            logger.error(f"LocalLLM response error: {e}")
            raise

    def response_call(
        self, 
        dialogue: List[Dict[str, str]], 
        functions_call: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Generator[Tuple[Optional[str], Optional[Any]], None, None]:
        """
        支持流式工具调用
        
        Args:
            dialogue: 对话历史列表
            functions_call: 工具定义列表 (兼容旧接口)
            tools: 工具定义列表
        
        Yields:
            (content, tool_calls) 元组
        """
        actual_tools = tools or functions_call
        payload = {
            "model": self.model_name,
            "messages": dialogue,
            "stream": True,
            "tools": actual_tools,
            "temperature": 0.1
        }
        headers = {
            "Content-Type": "application/json"
        }
        # 只有配置了API Key的时候才加Authorization头
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.post(self.base_url, json=payload, headers=headers, stream=True, timeout=30)
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                data = json.loads(line.decode())
                msg = data.get("message", {})
                content = msg.get("content")
                tool_calls = msg.get("tool_calls")
                yield content, tool_calls
        except Exception as e:
            logger.error(f"LocalLLM response_call error: {e}")
            raise


def create_instance(class_name: str, *args: Any, **kwargs: Any) -> LLM:
    """
    创建 LLM 实例的工厂函数
    
    Args:
        class_name: 类名 (OpenAILLM 或 LocalLLM，兼容旧名OllamaLLM)
        *args: 位置参数
        **kwargs: 关键字参数
    
    Returns:
        LLM 实例
    
    Raises:
        ValueError: 类名不存在
    """
    # 兼容旧配置的OllamaLLM类名
    if class_name == "OllamaLLM":
        class_name = "LocalLLM"
    cls = globals().get(class_name)
    if cls and issubclass(cls, LLM):
        return cls(*args, **kwargs)
    raise ValueError(f"LLM class '{class_name}' not found")


if __name__ == "__main__":
    config = {
        "model_name": "deepseek-chat",
        "api_key": "your_api_key",
        "url": "https://api.deepseek.com"
    }

    llm = create_instance("OpenAILLM", config)

    dialogue = [{"role": "user", "content": "杭州天气怎么样"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取某个地点的天气，用户应先提供一个位置，比如用户说杭州天气，参数为：zhejiang/hangzhou，比如用户说北京天气怎么样，参数为：beijing/beijing",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市，zhejiang/hangzhou"
                        }
                    },
                    "required": ["city"]
                }
            }
        }
    ]

    for content, tool_calls in llm.response_call(dialogue, tools):
        print(content, tool_calls)