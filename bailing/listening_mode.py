import time
import logging
import threading
import importlib
import pkgutil
from typing import Dict, Any, Optional
from bailing.summary import SummaryManager
from bailing.prompt import listening_summary_prompt, listening_analyzer_prompt
from plugins.registry import listener_registry

logger = logging.getLogger(__name__)


def _auto_import_listeners():
    package = importlib.import_module("plugins.listeners")
    for importer, modname, ispkg in pkgutil.walk_packages(package.__path__, prefix="plugins.listeners."):
        try:
            importlib.import_module(modname)
        except Exception as e:
            logger.debug(f"导入监听处理器 {modname} 失败: {e}")

_auto_import_listeners()


class ListeningModeManager:
    """
    监听模式管理器

    两种模式：
    - dialogue（对话模式）：ASR 结果直接提交给 chat_tool，支持全部工具
    - listening（静默模式）：ASR 结果先由轻量 LLM 分析，检测到重要事件
      （日程、提醒、新说话人）则触发对应动作，普通内容积累后定时总结
    """

    PUSH_TOKEN = "<|PUSH_NOTIFICATION|>"

    def __init__(self, config: Dict[str, Any], llm, bark_notifier=None, event_callback=None, event_loop=None):
        self.config = config
        self.llm = llm
        self.bark_notifier = bark_notifier
        self.event_callback = event_callback
        self._event_loop = event_loop
        self.summary_manager = SummaryManager(config)

        self.mode = "listening"
        self.wake_word = config.get("WakeWord", "小爱")
        self.wake_word_variants = {
            self.wake_word,
            "小艾", "小暧", "晓爱", "筱爱",
            "肖爱", "笑爱", "孝爱"
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
        self._stop_event = threading.Event()
        self._timer_thread = threading.Thread(target=self._summary_timer_loop, daemon=True)
        self._timer_thread.start()

        logger.info("ListeningModeManager initialized")

    def is_listening_mode(self) -> bool:
        with self._lock:
            return self.mode == "listening"

    def switch_to_listening(self):
        with self._lock:
            self.mode = "listening"
        logger.info("切换到监听模式")
        self._notify_mode_change("listening", "manual")

    def switch_to_dialogue(self):
        with self._lock:
            self.mode = "dialogue"
            self.last_dialogue_time = time.time()
        logger.info("切换到对话模式")
        self._notify_mode_change("dialogue", "manual")

    def _notify_mode_change(self, mode: str, reason: str):
        if self.event_callback:
            try:
                import asyncio as _asyncio
                _loop = self._event_loop or _asyncio.get_event_loop()
                if _loop.is_running():
                    _asyncio.run_coroutine_threadsafe(
                        self.event_callback({"type": "mode_change", "mode": mode, "reason": reason}),
                        _loop
                    )
            except Exception as e:
                logger.debug(f"发送模式切换通知失败: {e}")

    def notify_dialogue_activity(self):
        with self._lock:
            self.last_dialogue_time = time.time()

    def _match_wake_word(self, text: str) -> Optional[str]:
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
                self._notify_mode_change("dialogue", "wake_word")
                cleaned = text.strip().replace(matched, "").strip()
                if not cleaned:
                    logger.debug("仅检测到唤醒词，无后续内容，忽略")
                    return None, False
                return cleaned, True

            self.summary_manager.add_listening_item(text, start_time, end_time)
            self.total_word_count += len(text)

            self._check_trigger_summary_locked()
            self._trigger_listening_analysis(text)
            return None, False
        else:
            current_time = time.time()
            if current_time - self.last_dialogue_time >= self.dialogue_idle_timeout:
                logger.info(f"对话模式空闲超过{self.dialogue_idle_timeout}秒，自动切回监听模式")
                self.mode = "listening"
                self._notify_mode_change("listening", "idle_timeout")
                logger.debug("模式切换时的ASR结果不加入监听池")
                return None, False

            self.last_dialogue_time = current_time
            return text, False

    def _trigger_listening_analysis(self, text: str):
        """后台异步分析当前句子，不阻塞主流程"""
        def _do_analyze():
            try:
                result = self._analyze_sentence(text)
                if result is None:
                    return
                token, content = result
                logger.info(f"[监听分析] 检测到标记: {token} | 内容: {content}")
                self._dispatch_listener(token, content)
            except Exception as e:
                logger.debug(f"监听分析出错（不影响主流程）: {e}")

        threading.Thread(target=_do_analyze, daemon=True).start()

    def _analyze_sentence(self, text: str) -> Optional[tuple[str, str]]:
        """调用 LLM 分析单句话，输出特殊标记"""
        try:
            llm_response = self.llm.response([
                {"role": "system", "content": listening_analyzer_prompt},
                {"role": "user", "content": text}
            ])
            result = "".join(llm_response).strip()
            logger.debug(f"[监听分析] LLM返回: {result}")

            if result == "无" or not result:
                return None

            from plugins.registry import listener_registry
            for token_name in listener_registry:
                tag = f"<|{token_name}|>"
                if tag in result:
                    content = result.split(tag, 1)[-1].strip()
                    return token_name, content
            return None
        except Exception as e:
            logger.debug(f"LLM分析调用失败: {e}")
            return None

    def _dispatch_listener(self, token: str, content: str):
        """根据特殊 token 路由到对应的监听处理器"""
        from plugins.registry import listener_registry
        handler = listener_registry.get(token)
        if handler:
            try:
                handler(content)
            except Exception as e:
                logger.error(f"监听处理器 '{token}' 执行失败: {e}")
        else:
            logger.warning(f"未注册的监听标记: {token}")

    def _summary_timer_loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(5)
            with self._lock:
                if self.mode == "listening":
                    self._check_trigger_summary_locked()
                elif self.mode == "dialogue":
                    current_time = time.time()
                    if current_time - self.last_dialogue_time >= self.dialogue_idle_timeout:
                        logger.info(f"对话模式空闲超过{self.dialogue_idle_timeout}秒，自动切回监听模式")
                        self.mode = "listening"
                        self._notify_mode_change("listening", "idle_timeout")

    def _check_trigger_summary_locked(self):
        if self._summarizing:
            return
        current_time = time.time()
        need_summary = False
        reason = ""
        if current_time - self.last_summary_time >= self.summary_interval:
            need_summary = True
            reason = "定时总结"
        elif self.total_word_count >= self.summary_word_threshold:
            need_summary = True
            reason = "字数达标总结"
        if need_summary:
            self._summarizing = True
            logger.info(f"触发总结：{reason}")
            self.generate_summary()

    def generate_summary(self):
        raw_text = self.summary_manager.get_raw_text()
        if not raw_text:
            self._summarizing = False
            self.last_summary_time = time.time()
            return

        speaker_notes = self.summary_manager.get_speaker_notes()

        def do_summary():
            try:
                user_content = f"请总结以下内容：\n{raw_text}"
                if speaker_notes:
                    user_content = f"对话中涉及以下人物：\n{speaker_notes}\n\n{user_content}"
                llm_response = self.llm.response(
                    [
                        {"role": "system", "content": listening_summary_prompt},
                        {"role": "user", "content": user_content}
                    ]
                )
                final_summary = "".join(llm_response)
                logger.info(f"监听内容总结完成：\n{final_summary}")

                if self.PUSH_TOKEN in final_summary:
                    push_content = final_summary.replace(self.PUSH_TOKEN, "").strip()
                    if push_content and self.bark_notifier:
                        self.bark_notifier.send_formatted(push_content)
                    final_summary = push_content

                if final_summary:
                    self.summary_manager.add_summary(final_summary)
                    self._sync_to_robot_memory(final_summary)
                with self._lock:
                    self.total_word_count = 0
                    self.last_summary_time = time.time()
            except Exception as e:
                logger.error(f"总结失败：{e}")
            finally:
                self.summary_manager.clear_speaker_notes()
                with self._lock:
                    self._summarizing = False

        threading.Thread(target=do_summary, daemon=True).start()

    def _sync_to_robot_memory(self, summary_text: str):
        """将监听总结同步到 Robot 的长期记忆"""
        try:
            from bailing.robot import Robot
            from bailing.utils import write_json_file
            robot = Robot._instance
            if robot and hasattr(robot, 'memory') and robot.memory:
                robot.memory.memory["memory"] += f"\n[监听记忆] {summary_text}"
                write_json_file(robot.memory.memory_file, robot.memory.memory)
                logger.info("监听总结已同步到长期记忆")
        except Exception as e:
            logger.debug(f"同步到长期记忆失败（不影响主流程）: {e}")

    def clear_pool(self):
        with self._lock:
            self.summary_manager.clear()
            self.total_word_count = 0
            self.last_summary_time = time.time()