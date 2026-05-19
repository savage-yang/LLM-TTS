import os
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from bailing.utils import write_json_file

logger = logging.getLogger(__name__)


class Message:
    """消息对象，存储单条对话消息的完整信息"""

    def __init__(
        self,
        role: str,
        content: Optional[str] = None,
        uniq_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        audio_file: Optional[str] = None,
        tts_file: Optional[str] = None,
        vad_status: Optional[list] = None,
        tool_calls: Optional[Any] = None,
        tool_call_id: Optional[str] = None
    ):
        """
        初始化消息对象
        
        Args:
            role: 消息角色 (user/assistant/tool/system)
            content: 消息内容
            uniq_id: 消息唯一ID，自动生成
            start_time: 消息开始时间
            end_time: 消息结束时间
            audio_file: 关联的音频文件路径
            tts_file: 关联的TTS音频文件路径
            vad_status: VAD状态列表
            tool_calls: 工具调用信息
            tool_call_id: 工具调用ID
        """
        self.uniq_id = uniq_id or str(uuid.uuid4())
        self.role = role
        self.content = content
        self.start_time = start_time
        self.end_time = end_time
        self.audio_file = audio_file
        self.tts_file = tts_file
        self.vad_status = vad_status
        self.tool_calls = tool_calls
        self.tool_call_id = tool_call_id


class Dialogue:
    """对话管理类，管理整个会话的消息历史"""

    def __init__(self, dialogue_history_path: str):
        """
        初始化对话管理器
        
        Args:
            dialogue_history_path: 对话历史保存目录
        """
        self.dialogue_history_path = dialogue_history_path
        self.dialogue: List[Message] = []
        self.session_file_name = os.path.join(
            self.dialogue_history_path,
            f"dialogue-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
        )

    def put(self, message: Message) -> None:
        """
        添加一条消息到对话历史
        
        Args:
            message: Message对象
        """
        self.dialogue.append(message)

    def get_llm_dialogue(self, max_rounds: int = 20) -> List[Dict[str, Any]]:
        """
        获取LLM格式的对话列表，用于发送给大模型
        
        Args:
            max_rounds: 最大保留对话轮数（1轮=user+assistant），超出则截断旧对话
        
        Returns:
            符合OpenAI API格式的对话列表
        """
        dialogue = []
        for msg in self.dialogue:
            if msg.tool_calls is not None:
                dialogue.append({
                    "role": msg.role,
                    "tool_calls": msg.tool_calls
                })
            elif msg.role == "tool":
                dialogue.append({
                    "role": msg.role,
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content
                })
            else:
                dialogue.append({
                    "role": msg.role,
                    "content": msg.content
                })

        if len(dialogue) > max_rounds * 2 + 1:
            system_msg = dialogue[0] if dialogue and dialogue[0]["role"] == "system" else None
            rest = dialogue[1:] if system_msg else dialogue
            rest = rest[-(max_rounds * 2):]
            if system_msg:
                rest.insert(0, system_msg)
            dialogue = rest

        return dialogue

    def dump_dialogue(self) -> None:
        """
        保存本次会话的对话到JSON文件
        
        只保存user和assistant的对话，忽略其他角色
        如果只有系统prompt则不保存
        """
        if len(self.dialogue) <= 1:
            return

        dialogue_data = []
        for item in self.get_llm_dialogue():
            if item["role"] in ("user", "assistant"):
                dialogue_data.append(item)

        if dialogue_data:
            write_json_file(self.session_file_name, dialogue_data)
            logger.info(f"本次会话对话已保存: {self.session_file_name}")


if __name__ == "__main__":
    dialogue = Dialogue("../tmp/")
    dialogue.put(Message(role="user", content="你好"))
    dialogue.dump_dialogue()