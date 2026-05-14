import yaml
import json
import re
from typing import Dict, Any, Optional, Tuple, List


import logging

logger = logging.getLogger(__name__)


def load_prompt(prompt_path: str) -> str:
    """
    读取提示词文件并返回内容

    Args:
        prompt_path: 提示词文件路径

    Returns:
        去除首尾空白的提示词内容
    """
    with open(prompt_path, "r", encoding="utf-8") as file:
        prompt = file.read()
    return prompt.strip()


def read_json_file(file_path: str) -> Optional[Dict[str, Any]]:
    """
    读取 JSON 文件并返回内容

    Args:
        file_path: JSON 文件路径

    Returns:
        解析后的字典数据，解析失败返回 None
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        try:
            data = json.load(file)
            return data
        except json.JSONDecodeError as e:
            logger.error(f"解析 JSON 时出错: {e}")
            return None


def write_json_file(file_path: str, data: Dict[str, Any]) -> None:
    """
    将数据写入 JSON 文件

    Args:
        file_path: JSON 文件路径
        data: 要写入的数据
    """
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def read_config(config_path: str) -> Dict[str, Any]:
    """
    读取 YAML 配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        解析后的配置字典
    """
    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    return config


def is_segment(tokens: str) -> bool:
    """
    判断最后一个字符是否是句子结束符

    Args:
        tokens: 文本内容

    Returns:
        True 如果最后一个字符是结束符，否则 False
    """
    if tokens[-1] in (",", ".", "?", "，", "。", "？", "！", "!", ";", "；", ":", "："):
        return True
    return False


def is_segment_sentence(tokens: str, start_index: int) -> Tuple[bool, Optional[int]]:
    """
    从后向前搜索句子结束符

    Args:
        tokens: 文本内容
        start_index: 起始索引

    Returns:
        (是否找到结束符, 结束符位置)
    """
    for i in range(len(tokens) - 1, start_index - 1, -1):
        if tokens[i] in (",", ".", "?", "，", "。", "？", "！", "!", ";", "；", ":", "："):
            return True, i
    return False, None


def is_interrupt(query: str) -> bool:
    """
    判断输入是否包含中断词

    Args:
        query: 用户输入文本

    Returns:
        True 如果包含中断词，否则 False
    """
    for interrupt_word in ("停一下", "听我说", "不要说了", "stop", "hold on", "excuse me"):
        if query.lower().find(interrupt_word) >= 0:
            return True
    return False


def extract_json_from_string(input_string: str) -> Optional[str]:
    """
    提取字符串中的 JSON 部分

    Args:
        input_string: 输入文本

    Returns:
        提取到的 JSON 字符串，未找到返回 None
    """
    pattern = r'(\{.*\})'
    match = re.search(pattern, input_string)
    if match:
        return match.group(1)
    return None
