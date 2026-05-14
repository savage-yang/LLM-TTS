import time
import logging
import threading
from typing import Dict, Any, Optional
from bailing.summary import SummaryManager

logger = logging.getLogger(__name__)


class ListeningModeManager:
    def __init__(self, config: Dict[str, Any], llm):
        self.config = config
        self.llm = llm
        self.summary_manager = SummaryManager(config)

        self.mode = "listening"  # "listening" | "dialogue"
        self.wake_word = config.get("WakeWord", "百聆")

        listening_config = config.get("ListeningMode", {})
        self.summary_interval = listening_config.get("summary_interval", 300)
        self.summary_word_threshold = listening_config.get("summary_word_threshold", 500)
        self.dialogue_idle_timeout = listening_config.get("dialogue_idle_timeout", 120)

        self.last_summary_time = time.time()
        self.last_dialogue_time = time.time()
        self.total_word_count = 0
        self._summarizing = False  # 防止并发总结

        logger.info(f"ListeningModeManager initialized，初始化完成")

    def is_listening_mode(self) -> bool:
        return self.mode == "listening"

    def switch_to_listening(self):
        logger.info("切换到监听模式")
        self.mode = "listening"

    def switch_to_dialogue(self):
        logger.info("切换到对话模式")
        self.mode = "dialogue"
        self.last_dialogue_time = time.time()

    def notify_dialogue_activity(self):
        """标记对话活动（chat 开始时调用）"""
        self.last_dialogue_time = time.time()

    def process_asr_result(
        self, text: str, start_time: float, end_time: float
    ) -> Optional[str]:
        """
        处理 ASR 结果：根据模式返回行为
        返回：None 表示监听模式已处理，非空字符串表示需要进入对话
        """
        if self.mode == "listening":
            if self.wake_word in text.strip():
                self.switch_to_dialogue()
                cleaned = text.replace(self.wake_word, "").strip()
                if not cleaned:
                    logger.debug("仅检测到唤醒词，无后续内容，忽略")
                    return None
                return cleaned

            self.summary_manager.add_listening_item(text, start_time, end_time)
            self.total_word_count += len(text)

            self._check_trigger_summary()
            return None
        else:
            current_time = time.time()
            if current_time - self.last_dialogue_time >= self.dialogue_idle_timeout:
                logger.info(f"对话模式空闲超过{self.dialogue_idle_timeout}秒，自动切回监听模式")
                self.switch_to_listening()
                return self._process_as_listening(text, start_time, end_time)

            self.last_dialogue_time = current_time
            return text

    def _process_as_listening(self, text: str, start_time: float, end_time: float) -> Optional[str]:
        """从对话超时切回监听后，重新按监听模式处理"""
        if self.wake_word in text.strip():
            self.switch_to_dialogue()
            cleaned = text.replace(self.wake_word, "").strip()
            if not cleaned:
                return None
            return cleaned

        self.summary_manager.add_listening_item(text, start_time, end_time)
        self.total_word_count += len(text)
        self._check_trigger_summary()
        return None

    def _check_trigger_summary(self):
        if self._summarizing:
            return
        current_time = time.time()
        need_summary = False
        reason = ""
        if current_time - self.last_summary_time >= self.summary_interval:
            need_summary = True
            reason = f"定时总结"
        if self.total_word_count >= self.summary_word_threshold:
            need_summary = True
            reason = f"字数达标总结"
        if need_summary:
            self._summarizing = True
            logger.info(f"触发总结：{reason}")
            self.generate_summary()

    def generate_summary(self):
        raw_text = self.summary_manager.get_raw_text()
        if not raw_text:
            self._summarizing = False
            return

        system_prompt = """你是一个专业的会议记录员。
请根据给定的录音文本，生成一份结构化的总结：
- 包含时间戳
- 分点列出要点
- 语言简洁清晰
"""

        def do_summary():
            try:
                llm_response = self.llm.response(
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"请总结以下内容：\n{raw_text}"}
                    ]
                )
                final_summary = "".join(llm_response)
                logger.info(f"监听内容总结完成：\n{final_summary}")

                self.summary_manager.add_summary(final_summary)

                self.total_word_count = 0
                self.last_summary_time = time.time()
            except Exception as e:
                logger.error(f"总结失败：{e}")
            finally:
                self._summarizing = False

        threading.Thread(target=do_summary, daemon=True).start()

    def clear_pool(self):
        self.summary_manager.clear()
        self.total_word_count = 0
        self.last_summary_time = time.time()