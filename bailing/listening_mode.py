import time
import logging
import threading
from typing import Dict, Any, Optional
from bailing.summary import SummaryManager
from bailing.prompt import listening_summary_prompt

logger = logging.getLogger(__name__)


class ListeningModeManager:
    """
    监听模式管理器，管理监听模式和对话模式之间的切换，
    以及监听池的自动总结
    """

    def __init__(self, config: Dict[str, Any], llm):
        """
        初始化监听模式管理器

        Args:
            config: 配置字典，包含 WakeWord 和 ListeningMode 配置
            llm: LLM 实例，用于生成监听内容总结
        """
        self.config = config
        self.llm = llm
        self.summary_manager = SummaryManager(config)

        self.mode = "listening"
        self.wake_word = config.get("WakeWord", "塔菲")
        # 唤醒词同音字变体（ASR 可能识别为同音不同字）
        self.wake_word_variants = {
            self.wake_word,
            # 标准变体
            "塔飞", "塔霏",
            # 常见误识别
            "踏菲", "她菲", "他菲",
                # 近音字
            "泰菲", "太菲", "台菲"
        }

        listening_config = config.get("ListeningMode", {})
        self.summary_interval = listening_config.get("summary_interval", 300)
        self.summary_word_threshold = listening_config.get("summary_word_threshold", 500)
        self.dialogue_idle_timeout = listening_config.get("dialogue_idle_timeout", 120)

        self.last_summary_time = time.time()
        self.last_dialogue_time = time.time()
        self.total_word_count = 0
        self._summarizing = False
        self._lock = threading.Lock()

        logger.info(f"ListeningModeManager initialized，初始化完成")

    def is_listening_mode(self) -> bool:
        """
        查询当前是否为监听模式

        Returns:
            True 表示监听模式，False 表示对话模式
        """
        with self._lock:
            return self.mode == "listening"

    def switch_to_listening(self):
        """切换到监听模式"""
        with self._lock:
            self.mode = "listening"
        logger.info("切换到监听模式")

    def switch_to_dialogue(self):
        """切换到对话模式"""
        with self._lock:
            self.mode = "dialogue"
            self.last_dialogue_time = time.time()
        logger.info("切换到对话模式")

    def notify_dialogue_activity(self):
        """标记对话活动，用于检测对话模式空闲超时"""
        with self._lock:
            self.last_dialogue_time = time.time()

    def _match_wake_word(self, text: str) -> Optional[str]:
        """
        检查文本是否匹配唤醒词（含同音字变体）

        Args:
            text: 待检查的文本

        Returns:
            匹配到的变体字符串，未匹配返回 None
        """
        for variant in self.wake_word_variants:
            if variant in text:
                return variant
        return None

    def process_asr_result(
        self, text: str, start_time: float, end_time: float
    ) -> tuple[Optional[str], bool]:
        with self._lock:
            return self._process_asr_result_locked(text, start_time, end_time)

    def _process_asr_result_locked(
        self, text: str, start_time: float, end_time: float
    ) -> tuple[Optional[str], bool]:
        if self.mode == "listening":
            matched = self._match_wake_word(text.strip())
            if matched is not None:
                self.mode = "dialogue"
                self.last_dialogue_time = time.time()
                logger.info("切换到对话模式")
                cleaned = text.strip().replace(matched, "").strip()
                if not cleaned:
                    logger.debug("仅检测到唤醒词，无后续内容，忽略")
                    return None, False
                return cleaned, True

            self.summary_manager.add_listening_item(text, start_time, end_time)
            self.total_word_count += len(text)
            self._check_trigger_summary_locked()
            return None, False
        else:
            current_time = time.time()
            if current_time - self.last_dialogue_time >= self.dialogue_idle_timeout:
                logger.info(f"对话模式空闲超过{self.dialogue_idle_timeout}秒，自动切回监听模式")
                self.mode = "listening"
                return self._process_as_listening_locked(text, start_time, end_time)

            self.last_dialogue_time = current_time
            return text, False

    def _process_as_listening_locked(
        self, text: str, start_time: float, end_time: float
    ) -> tuple[Optional[str], bool]:
        matched = self._match_wake_word(text.strip())
        if matched is not None:
            self.mode = "dialogue"
            self.last_dialogue_time = time.time()
            logger.info("切换到对话模式")
            cleaned = text.strip().replace(matched, "").strip()
            if not cleaned:
                return None, False
            return cleaned, True

        self.summary_manager.add_listening_item(text, start_time, end_time)
        self.total_word_count += len(text)
        self._check_trigger_summary_locked()
        return None, False

    def _check_trigger_summary_locked(self):
        """检查是否满足触发总结的条件（定时或定量）"""
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
        """
        调用 LLM 生成监听内容总结

        在后台线程中异步执行，不阻塞主线程
        """
        raw_text = self.summary_manager.get_raw_text()
        if not raw_text:
            with self._lock:
                self._summarizing = False
            return

        def do_summary():
            try:
                llm_response = self.llm.response(
                    [
                        {"role": "system", "content": listening_summary_prompt},
                        {"role": "user", "content": f"请总结以下内容：\n{raw_text}"}
                    ]
                )
                final_summary = "".join(llm_response)
                logger.info(f"监听内容总结完成：\n{final_summary}")

                self.summary_manager.add_summary(final_summary)
                with self._lock:
                    self.total_word_count = 0
                    self.last_summary_time = time.time()
            except Exception as e:
                logger.error(f"总结失败：{e}")
            finally:
                with self._lock:
                    self._summarizing = False

        threading.Thread(target=do_summary, daemon=True).start()

    def clear_pool(self):
        """清空监听池，重置计数器"""
        with self._lock:
            self.summary_manager.clear()
            self.total_word_count = 0
            self.last_summary_time = time.time()