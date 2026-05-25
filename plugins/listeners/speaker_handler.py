import logging
import os
import sys

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.registry import register_listener

logger = logging.getLogger(__name__)


@register_listener("SPEAKER")
def handle_speaker(content: str):
    """
    处理 <|SPEAKER|> 标记：记录人物信息到监听总结上下文
    后续生成监听总结时，人物笔记会汇入 LLM 输入，使总结包含人物关系
    """
    if not content.strip():
        return
    from bailing.summary import SummaryManager
    SummaryManager.add_speaker_note(content.strip())