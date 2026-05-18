import json
import os
import re
import signal
import sys
import queue
import threading
import uuid
from abc import ABC, abstractmethod
import logging
from concurrent.futures import ThreadPoolExecutor
import argparse
import time
from typing import Dict, Any, Optional, List
import numpy as np

from bailing.recorder import create_instance as create_recorder
from bailing.player import create_instance as create_player, PygameStreamPlayer
from bailing.asr import create_instance as create_asr
from bailing.llm import create_instance as create_llm
from bailing.tts import create_instance as create_tts, QwenTtsRealtimeStream
from bailing.vad import create_instance as create_vad
from bailing.memory import Memory
from bailing.dialogue import Message, Dialogue
from bailing.utils import read_config, extract_json_from_string
from bailing.prompt import sys_prompt
from bailing.listening_mode import ListeningModeManager
from bailing.bark_notify import BarkNotifier

logger = logging.getLogger(__name__)


class Robot(ABC):
    EXIT_TOKEN = "<|EXIT_PROGRAM|>"
    SWITCH_LISTEN_TOKEN = "<|SWITCH_LISTEN|>"
    PUSH_TOKEN = "<|PUSH_NOTIFICATION|>"

    def __init__(self, config_file: str, websocket: Optional[Any] = None, loop: Optional[Any] = None):
        config = read_config(config_file)
        self.audio_queue = queue.Queue()

        start_time = time.time()

        t1 = time.time()
        self.recorder = create_recorder(
            config["selected_module"]["Recorder"],
            config["Recorder"][config["selected_module"]["Recorder"]]
        )
        logger.info(f"[启动] 录音模块加载完成，耗时: {time.time()-t1:.2f}s")

        t2 = time.time()
        self.asr = create_asr(
            config["selected_module"]["ASR"],
            config["ASR"][config["selected_module"]["ASR"]]
        )
        logger.info(f"[启动] ASR语音识别模块加载完成，耗时: {time.time()-t2:.2f}s")

        t3 = time.time()
        self.llm = create_llm(
            config["selected_module"]["LLM"],
            config["LLM"][config["selected_module"]["LLM"]]
        )
        logger.info(f"[启动] LLM大模型模块加载完成，耗时: {time.time()-t3:.2f}s")

        t4 = time.time()
        self.tts = create_tts(
            config["selected_module"]["TTS"],
            config["TTS"][config["selected_module"]["TTS"]]
        )
        logger.info(f"[启动] TTS语音合成模块加载完成，耗时: {time.time()-t4:.2f}s")

        t5 = time.time()
        self.vad = create_vad(
            config["selected_module"]["VAD"],
            config["VAD"][config["selected_module"]["VAD"]]
        )
        logger.info(f"[启动] VAD语音端点检测模块加载完成，耗时: {time.time()-t5:.2f}s")

        t6 = time.time()
        self.player = create_player(
            config["selected_module"]["Player"],
            config["Player"][config["selected_module"]["Player"]]
        )
        logger.info(f"[启动] 播放器模块加载完成，耗时: {time.time()-t6:.2f}s")

        t7 = time.time()
        self.memory = Memory(config.get("Memory"))
        logger.info(f"[启动] 记忆模块加载完成，耗时: {time.time()-t7:.2f}s")

        # 初始化Bark推送器
        bark_config = config.get("BarkNotify", {})
        self.bark_notifier = BarkNotifier(
            device_key=bark_config.get("device_key", ""),
            base_url=bark_config.get("base_url", "https://api.day.app")
        )

        # 初始化监听模式管理器
        self.listening_manager = ListeningModeManager(config, self.llm, bark_notifier=self.bark_notifier)

        logger.info(f"[启动] 所有模块加载完成，总耗时: {time.time()-start_time:.2f}s")

        self.start_task_mode = config.get("StartTaskMode")
        if isinstance(self.start_task_mode, str):
            self.start_task_mode = self.start_task_mode.lower() == 'true'
        logger.info(f"工具调用功能状态：{'开启' if self.start_task_mode else '关闭'}")

        if not self.start_task_mode:
            self.prompt = re.sub(r'\n3\. 如果需要调用工具回答问题.*?```', '', sys_prompt, flags=re.DOTALL)
        else:
            self.prompt = sys_prompt
        self.prompt = self.prompt.replace("{memory}", self.memory.get_memory()).strip()

        self.vad_queue = queue.Queue()
        self.dialogue = Dialogue(config["Memory"]["dialogue_history_path"])
        self.dialogue.put(Message(role="system", content=self.prompt))

        self.vad_start = True

        self.INTERRUPT = config["interrupt"]
        self.silence_time_ms = int((1000 / 1000) * (16000 / 512))

        self.last_voice_time = time.time() * 1000
        self.max_silence_before_speech = config.get("VAD", {}).get("max_silence_before_speech", 2000)

        self.chat_lock = False

        self.stop_event = threading.Event()

        self.callback = None

        self.speech = []

        self.min_audio_energy = config.get("ASR", {}).get("min_audio_energy", 300)

        self.task_queue = None
        self.task_manager = None
        if self.start_task_mode:
            from plugins.task_manager import TaskManager
            self.task_queue = queue.Queue()
            self.task_manager = TaskManager(config.get("TaskManager"), self.task_queue)
            logger.info("工具模块已加载完成")
        else:
            logger.info("已跳过工具模块加载，启动速度优化")

        self.buffer_sound_config = config.get("BufferSound", {
            "enabled": True,
            "threshold_length": 15,
            "file_prefix": "voice",
            "file_dir": "voice_cache"
        })

        self.pending_shutdown = False

        selected_tts = config["selected_module"]["TTS"]
        self._is_streaming = (selected_tts == "QwenTtsRealtimeAPI")
        self._init_tts_specific(config)

    @abstractmethod
    def _init_tts_specific(self, config: Dict[str, Any]) -> None:
        """子类实现：初始化 TTS 相关属性"""
        ...

    @abstractmethod
    def _tts_priority(self) -> None:
        """子类实现：设置 TTS 优先级队列和线程"""
        ...

    @abstractmethod
    def interrupt_playback(self) -> None:
        """子类实现：中断播放和 TTS 生成"""
        ...

    @abstractmethod
    def _chat_reset_tts(self) -> None:
        """子类实现：chat 开始前重置 TTS 状态"""
        ...

    @abstractmethod
    def _chat_handle_token(self, content: str) -> None:
        """子类实现：处理每个 LLM token"""
        ...

    @abstractmethod
    def _chat_flush_tts(self) -> None:
        """子类实现：清空 TTS 缓冲池剩余内容"""
        ...

    @abstractmethod
    def _chat_submit_tts(self, full_response: str, need_exit: bool) -> None:
        """子类实现：提交完整回复到 TTS"""
        ...

    @abstractmethod
    def _chat_tool_token(self, content: str) -> None:
        """子类实现：工具调用时发送 token 到 TTS"""
        ...

    @abstractmethod
    def _cleanup_tts(self) -> None:
        """子类实现：清理 TTS 特定资源"""
        ...

    @abstractmethod
    def _on_llm_error(self) -> None:
        """子类实现：LLM 出错时重置 TTS"""
        ...

    def listen_dialogue(self, callback: Any):
        self.callback = callback

    def _stream_vad(self):
        def vad_thread():
            while not self.stop_event.is_set():
                try:
                    data = self.audio_queue.get()
                    vad_statue = self.vad.is_vad(data)
                    self.vad_queue.put({"voice": data, "vad_statue": vad_statue})
                except Exception as e:
                    logger.error(f"VAD 处理出错: {e}")
        consumer_audio = threading.Thread(target=vad_thread, daemon=True)
        consumer_audio.start()

    def _check_audio_energy(self, voice_data_list):

        if not voice_data_list:
            return 0.0

        all_data = []
        for data in voice_data_list:
            if isinstance(data, bytes):
                arr = np.frombuffer(data, dtype=np.int16)
                all_data.append(arr)

        if not all_data:
            return 0.0

        full_audio = np.concatenate(all_data)
        rms = np.sqrt(np.mean(full_audio.astype(np.float32) ** 2))

        return float(rms)

    def _shutdown_cleanup(self):
        logger.info("正在关闭系统，优先保存数据...")

        try:
            self.dialogue.dump_dialogue()
            logger.info("对话数据保存完成")
        except Exception as e:
            logger.error(f"对话保存失败：{e}", exc_info=True)

        try:
            self.memory.rebuild_full_memory(self.dialogue.dialogue_history_path)
            logger.info("记忆更新完成")
        except Exception as e:
            logger.error(f"记忆更新失败：{e}", exc_info=True)

        logger.info("开始关闭其他模块...")
        def _shutdown_worker():
            try:
                self.stop_event.set()
                self._cleanup_tts()
                try:
                    while not self.audio_queue.empty():
                        self.audio_queue.get_nowait()
                    while not self.vad_queue.empty():
                        self.vad_queue.get_nowait()
                    if self.task_queue is not None:
                        while not self.task_queue.empty():
                            self.task_queue.get_nowait()
                except Exception:
                    pass
                try:
                    self.recorder.stop_recording()
                except Exception as e:
                    logger.warning(f"录音器关闭失败: {e}")
                try:
                    self.player.shutdown()
                except Exception as e:
                    logger.warning(f"播放器关闭失败: {e}")
                logger.info("所有模块已安全关闭！")
            except Exception as e:
                logger.error(f"模块关闭过程出错: {e}", exc_info=True)

        shutdown_thread = threading.Thread(target=_shutdown_worker, daemon=True)
        shutdown_thread.start()
        shutdown_thread.join(timeout=3)

        logger.info("程序退出")
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            try:
                os._exit(0)
            except Exception:
                pass

    def start_recording_and_vad(self):
        self.recorder.start_recording(self.audio_queue)
        logger.info("Started recording.")
        self._stream_vad()
        self._tts_priority()

        self.last_asr_text = ""
        self.last_asr_time = 0
        self._asr_dedup_lock = threading.Lock()
        self._wakeup_playing = False

    def _process_asr_result(self, voice_data_list):
        """统一的 ASR 识别+过滤流程（异步，不阻塞 VAD 主循环）"""
        self.vad_start = False
        voice_data = [d["voice"] for d in voice_data_list]

        if self._check_audio_energy(voice_data) < self.min_audio_energy:
            logger.debug("音频能量过低，过滤纯杂音")
            return

        threading.Thread(target=self._async_asr_process, args=(voice_data,), daemon=True).start()

    def _async_asr_process(self, voice_data):
        """后台线程：ASR 识别 + 文本处理"""
        try:
            text, tmpfile = self.asr.recognizer(voice_data)
        except Exception as e:
            logger.error(f"ASR识别出错: {e}")
            return

        if not text.strip():
            logger.debug("识别结果为空，跳过处理。")
            return

        now = time.time()
        with self._asr_dedup_lock:
            if text.strip() == self.last_asr_text and now - self.last_asr_time < 1.0:
                logger.debug(f"重复识别结果已过滤：{text}")
                return
            self.last_asr_text = text.strip()
            self.last_asr_time = now

        end_time = time.time()
        start_time = end_time - len(voice_data) * 0.032

        processed_text, is_wake_transition = self.listening_manager.process_asr_result(text, start_time, end_time)

        if processed_text is not None and processed_text.strip():
            logger.debug(f"ASR识别结果(对话模式): {processed_text}")
            if self.chat_lock:
                logger.debug("对话模式已有对话进行中，忽略本次ASR结果")
                return
            if self.callback:
                self.callback({"role": "user", "content": str(processed_text)})
            self._submit_chat(processed_text, play_wakeup=is_wake_transition)
        else:
            logger.debug(f"ASR识别结果(监听模式): {text}")

    def _play_wakeup_sound(self) -> None:
        root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        wakeup_path = os.path.join(root_path, "voice_cache", "wakeup.wav")
        if os.path.exists(wakeup_path):
            logger.debug("播放唤醒音效")
            self.player.play(wakeup_path)
            while self.player.get_playing_status():
                time.sleep(0.05)
        else:
            logger.debug(f"唤醒音效文件不存在：{wakeup_path}")

    def _duplex(self) -> None:
        data = self.vad_queue.get()
        vad_status = data.get("vad_statue")
        current_time = time.time() * 1000

        if vad_status is not None:
            self.last_voice_time = current_time
            if hasattr(self, 'last_activity_time'):
                self.last_activity_time = time.time()

        if self.vad_start:
            if current_time - self.last_voice_time > self.max_silence_before_speech:
                logger.debug(f"静默超过{self.max_silence_before_speech}ms，自动结束本次录音")
                speech = self.speech
                self.speech = []
                self._process_asr_result(speech)
                return
            self.speech.append(data)
            self.last_voice_time = current_time

        if self.task_queue is not None and not self.task_queue.empty() and not self.vad_start \
                and not self.player.get_playing_status() and not self.chat_lock:
            result = self.task_queue.get()
            self._submit_task_tts(result.response)

        if vad_status is None:
            return

        if "start" in vad_status:
            self.last_voice_time = current_time
            if (self.player.get_playing_status() or self.chat_lock) and not getattr(self, '_wakeup_playing', False):
                if self.INTERRUPT:
                    self.chat_lock = False
                    self.interrupt_playback()
                    self.vad_start = True
                    self.speech = []
                    self.speech.append(data)
                else:
                    return
            else:
                self.vad_start = True
                self.speech = []
                self.speech.append(data)
        elif "end" in vad_status and len(self.speech) > 0:
            logger.debug(f"语音包的长度：{len(self.speech)}")
            speech = self.speech
            self.speech = []
            self._process_asr_result(speech)

    @abstractmethod
    def _submit_chat(self, text: str) -> None:
        """子类实现：提交 chat 任务"""
        ...

    @abstractmethod
    def _submit_task_tts(self, response: str) -> None:
        """子类实现：提交任务 TTS"""
        ...

    @abstractmethod
    def _submit_async_save(self, fn) -> None:
        """子类实现：提交异步保存任务"""
        ...

    @abstractmethod
    def _executor_for_prologue(self):
        """子类实现：返回用于开场白的 executor"""
        ...

    def run(self):
        try:
            self.start_recording_and_vad()

            self.player.play_prologue(executor=self._executor_for_prologue())

            while not self.stop_event.is_set():
                self._duplex()
        except KeyboardInterrupt:
            logger.info("Received KeyboardInterrupt. Exiting...")
        finally:
            self.shutdown()

    def speak_and_play(self, text: str) -> Optional[str]:
        if text is None or len(text) <= 0:
            logger.info(f"无需tts转换，query为空，{text}")
            return None

        text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
        text = text.replace('"', '').replace("'", "")

        tts_file = self.tts.to_tts(text)
        if tts_file is None:
            logger.error(f"tts转换失败，{text}")
            return None
        logger.debug(f"TTS 文件生成完毕{self.chat_lock}")
        return tts_file

    def chat_tool(self, query: str) -> List[str]:
        from plugins.registry import Action
        try:
            llm_responses = self.llm.response_call(self.dialogue.get_llm_dialogue(), functions_call=self.task_manager.get_functions())
        except Exception as e:
            logger.error(f"LLM 处理出错 {query}: {e}")
            self._on_llm_error()
            return []

        tool_call_flag = False
        response_message = []
        function_name = None
        function_id = None
        function_arguments = ""
        content_arguments = ""
        for chunk in llm_responses:
            content, tools_call = chunk
            if content is not None and len(content) > 0:
                if len(response_message) <= 0 and content == "```":
                    tool_call_flag = True
            if tools_call is not None:
                tool_call_flag = True
                if tools_call[0].id is not None:
                    function_id = tools_call[0].id
                if tools_call[0].function.name is not None:
                    function_name = tools_call[0].function.name
                if tools_call[0].function.arguments is not None:
                    function_arguments += tools_call[0].function.arguments
            if content is not None and len(content) > 0:
                if tool_call_flag:
                    content_arguments += content
                else:
                    response_message.append(content)
                    logger.debug(f"收到LLM token: {content}")
                    self._chat_tool_token(content)

        if not tool_call_flag:
            pass
        else:
            if function_id is None:
                a = extract_json_from_string(content_arguments)
                if a is not None:
                    content_arguments_json = json.loads(a)
                    function_name = content_arguments_json["function_name"]
                    function_arguments = json.dumps(content_arguments_json["args"], ensure_ascii=False)
                    function_id = str(uuid.uuid4().hex)
                else:
                    return []
            function_arguments = json.loads(function_arguments)
            logger.info(f"function_name={function_name}, function_id={function_id}, function_arguments={function_arguments}")
            result = self.task_manager.tool_call(function_name, function_arguments)
            if result.action == Action.NOTFOUND:
                logger.error(f"没有找到函数{function_name}")
                return []
            elif result.action == Action.NONE:
                return []
            elif result.action == Action.RESPONSE:
                self._chat_tool_token(result.response)
                return [result.response]
            elif result.action == Action.REQLLM:
                self.dialogue.put(Message(role='assistant',
                                          tool_calls=[{"id": function_id, "function": {"arguments": json.dumps(function_arguments, ensure_ascii=False),
                                                                                       "name": function_name},
                                                       "type": 'function', "index": 0}]))
                self.dialogue.put(Message(role="tool", tool_call_id=function_id, content=result.result))
                return self.chat_tool(query)
            elif result.action == Action.ADDSYSTEM:
                self.dialogue.put(Message(**result.result))
                return []
            elif result.action == Action.ADDSYSTEMSPEAK:
                self.dialogue.put(Message(role='assistant',
                                          tool_calls=[{"id": function_id, "function": {
                                              "arguments": json.dumps(function_arguments, ensure_ascii=False),
                                              "name": function_name},
                                                       "type": 'function', "index": 0}]))
                self.dialogue.put(Message(role="tool", tool_call_id=function_id, content=result.response))
                self.dialogue.put(Message(**result.result))
                self.dialogue.put(Message(role="user", content="ok"))
                return self.chat_tool(query)
            else:
                logger.error(f"not found action type: {result.action}")
        return response_message

    def chat(self, query: str, play_wakeup: bool = False) -> Optional[bool]:
        self.dialogue.put(Message(role="user", content=query))
        self.chat_lock = True

        self.listening_manager.notify_dialogue_activity()

        buffer_finish_event, buffer_played = threading.Event(), False
        buffer_finish_event.set()

        if play_wakeup:
            self._wakeup_playing = True
            self._play_wakeup_sound()
            buffer_played = True
        else:
            query_length = len(query.strip())
            threshold = self.buffer_sound_config.get("threshold_length", 15)
            if query_length >= threshold:
                buffer_finish_event, buffer_played = self.player.play_buffer_sound(
                    buffer_config=self.buffer_sound_config,
                    executor=self._executor_for_prologue()
                )
                if buffer_played:
                    logger.debug(f"问题长度{query_length}≥阈值{threshold}，已触发缓冲音效")

        self._chat_reset_tts()

        response_message = []
        need_exit = False
        need_switch_listen = False
        need_push = False

        if self.start_task_mode:
            response_message = self.chat_tool(query)
        else:
            self._wakeup_playing = False
            try:
                llm_responses = self.llm.response(self.dialogue.get_llm_dialogue())
            except Exception as e:
                self.chat_lock = False
                logger.error(f"LLM 处理出错 {query}: {e}")
                self._on_llm_error()
                return None

            for content in llm_responses:
                if content is None or len(content) == 0:
                    continue
                content = re.sub(r'```json.*?```', '', content, flags=re.DOTALL)
                content = re.sub(r'\{\"function_name\".*?\}', '', content, flags=re.DOTALL)
                if not content.strip():
                    continue
                response_message.append(content)
                logger.debug(f"收到LLM token: {content}")
                self._chat_handle_token(content)

        self._chat_flush_tts()

        raw_full_response = "".join(response_message).strip()
        logger.info(f"[LLM原始回答] {raw_full_response}")
        full_response = raw_full_response.replace(self.EXIT_TOKEN, "").strip()
        if self.EXIT_TOKEN in raw_full_response:
            need_exit = True
            logger.debug(f"检测到退出标记，已过滤，need_exit设为True")
        
        full_response = full_response.replace(self.SWITCH_LISTEN_TOKEN, "").strip()
        if self.SWITCH_LISTEN_TOKEN in raw_full_response:
            need_switch_listen = True
            logger.debug(f"检测到切换监听标记，已过滤，need_switch_listen设为True")

        full_response = full_response.replace(self.PUSH_TOKEN, "").strip()
        if self.PUSH_TOKEN in raw_full_response:
            need_push = True
            logger.debug(f"检测到推送标记，已过滤，need_push设为True")

        if full_response and len(full_response) > 2:
            end_char = full_response[-1]
            if end_char not in ['。', '！', '？', '.', '!', '?', '”', '"', '）', ')']:
                full_response += "。"

            logger.info(f"[LLM回答] {full_response}")

            def _async_save_dialogue():
                try:
                    dialogue_history = self.dialogue.get_llm_dialogue()
                    need_save = True
                    if dialogue_history and len(dialogue_history) > 0:
                        last_msg = dialogue_history[-1]
                        if last_msg.get("role") == "assistant" and last_msg.get("content", "").strip() == full_response:
                            need_save = False
                    if need_save:
                        self.dialogue.put(Message(role="assistant", content=full_response))
                        self.dialogue.dump_dialogue()
                        logger.debug("对话内容已异步保存完成，不依赖TTS播放结果")
                    else:
                        logger.debug("重复回答已过滤，无需保存")
                except Exception as e:
                    logger.error(f"对话保存失败: {e}")
            self._submit_async_save(_async_save_dialogue)

            if self.callback:
                self.callback({"role": "assistant", "content": full_response})

            if buffer_played:
                logger.debug("等待缓冲音效播放完成，准备输出TTS...")
                buffer_finish_event.wait(timeout=1)
                pause_time = self.buffer_sound_config.get("pause_after_buffer")
                if pause_time > 0:
                    logger.debug(f"缓冲音效结束，停顿{pause_time}秒后开始输出回答...")
                    time.sleep(pause_time)

            self._chat_submit_tts(full_response, need_exit)
        else:
            logger.warning("LLM生成内容为空或过短，不发送给TTS")
            self._chat_flush_tts()

        self.chat_lock = False
        
        if need_switch_listen:
            logger.info("LLM主动触发切换监听模式")
            self.listening_manager.switch_to_listening()

        if need_push:
            threading.Thread(target=self._do_push_notification, args=(full_response,), daemon=True).start()
        
        logger.info(f"回答完成，总长度: {len(full_response)} 字")

        return True

    def shutdown(self):
        try:
            self._shutdown_cleanup()
            logger.info("程序正常退出，再见~")
        except Exception as e:
            logger.error(f"清理资源时出现错误: {e}", exc_info=True)

        finally:
            try:
                sys.exit(0)
            except:
                os._exit(0)

    def stop(self):
        try:
            if self.player is not None:
                if hasattr(self.player, "stop"):
                    self.player.stop()
                if hasattr(self.player, "close"):
                    self.player.close()
            if hasattr(self, "stop_event") and self.stop_event is not None:
                self.stop_event.set()
            if hasattr(self, "recorder") and self.recorder is not None:
                if hasattr(self.recorder, "stop"):
                    self.recorder.stop()
                if hasattr(self.recorder, "close"):
                    self.recorder.close()
        except Exception as e:
            logger.debug(f"清理资源时出现非关键错误: {e}")


# ============================================================
# StreamRobot：流式 TTS 机器人（QwenTtsRealtimeAPI）
# ============================================================
class StreamRobot(Robot):
    def _init_tts_specific(self, config: Dict[str, Any]) -> None:
        self.stream_player: Optional[PygameStreamPlayer] = None
        self.stream_tts_config: Optional[Dict[str, Any]] = None
        self.current_tts_stream: Optional[QwenTtsRealtimeStream] = None

        self.tts_consecutive_fail_count = 0
        self.MAX_TTS_RETRY = 1
        self.last_tts_retry_time = 0
        self.TTS_RETRY_CD = 60

        self.stream_buffer = ""
        self.last_stream_flush_time = time.time()
        self._tts_initialized = False

        selected_tts = config["selected_module"]["TTS"]
        self.stream_player = PygameStreamPlayer()
        self.stream_tts_config = config["TTS"][selected_tts]
        self.stream_buffer_duration = self.stream_tts_config.get("stream_buffer_duration", 0.3)
        
        # 首次缓冲机制 - 从 TTS 配置中读取
        self.is_first_buffer = True  # 是否是首次缓冲
        self.first_buffer_start_time = 0.0  # 首次缓冲开始时间
        self.first_buffer_duration = self.stream_tts_config.get("first_buffer_duration", 2.0)  # 首次超长缓冲时间（秒），默认2秒
        
        # 空闲检测 - 长时间无活动自动断开TTS连接
        self.last_activity_time = time.time()  # 最后活动时间
        self.idle_timeout = 300  # 空闲超时时间，单位秒（5分钟）
        self.idle_check_interval = 60  # 空闲检查间隔，单位秒（1分钟）
        self._tts_lock = threading.RLock()  # 保护 current_tts_stream 的读写（可重入，避免同一线程重复申请死锁）
        
        self.current_tts_stream = QwenTtsRealtimeStream(self.stream_tts_config, self.stream_player)
        logger.info(f"已启用流式TTS模式，首次对话自动建连，首次缓冲时间: {self.first_buffer_duration}秒，普通缓冲时间: {self.stream_buffer_duration}秒，空闲超时: {self.idle_timeout}秒")

    def _tts_priority(self) -> None:
        def shutdown_watcher():
            while not self.stop_event.is_set():
                if self.pending_shutdown:
                    if not self.player.get_playing_status():
                        logger.info("告别语音播放完成，程序即将关闭...")
                        self.shutdown()
                time.sleep(0.2)

        watcher = threading.Thread(target=shutdown_watcher, daemon=True)
        watcher.start()
        
        def idle_watcher():
            while not self.stop_event.is_set():
                try:
                    current_time = time.time()
                    if current_time - self.last_activity_time >= self.idle_timeout:
                        with self._tts_lock:
                            if (self.current_tts_stream 
                                and self.current_tts_stream.is_alive()
                                and current_time - self.last_activity_time >= self.idle_timeout):
                                logger.info(f"空闲超时{self.idle_timeout}秒，断开TTS连接以节省资源")
                                self.current_tts_stream.close()
                                self.current_tts_stream = None
                                self._tts_initialized = False
                except Exception as e:
                    logger.debug(f"空闲检测出错: {e}")
                
                time.sleep(self.idle_check_interval)

        idle_watcher_thread = threading.Thread(target=idle_watcher, daemon=True)
        idle_watcher_thread.start()

    def interrupt_playback(self) -> None:
        logger.info("Interrupting current playback and TTS generation.")
        self.pending_shutdown = False
        with self._tts_lock:
            if self.current_tts_stream:
                self.current_tts_stream.reset()
        self.stream_player.clear_buffer()
        self.player.stop()

    def _chat_reset_tts(self) -> None:
        self.stream_player.clear_buffer()
        self.is_first_buffer = True
        self.first_buffer_start_time = 0.0
        self.stream_buffer = ""
        self.last_stream_flush_time = time.time()
        
        with self._tts_lock:
            if self.current_tts_stream and self.current_tts_stream.is_alive():
                self.current_tts_stream.reset()
                self._tts_initialized = True
            else:
                self._tts_initialized = False
                if self.tts_consecutive_fail_count < self.MAX_TTS_RETRY:
                    self._init_stream_connection()
                    if self.current_tts_stream and self.current_tts_stream.is_alive():
                        self._tts_initialized = True

    def _chat_handle_token(self, content: str) -> None:
        if self.current_tts_stream is None:
            if self.tts_consecutive_fail_count < self.MAX_TTS_RETRY:
                self._init_stream_connection()
            if self.current_tts_stream is None:
                return
        
        if self.tts_consecutive_fail_count < self.MAX_TTS_RETRY:
            self._check_and_reconnect_stream()
            self.stream_buffer += content
            current_time = time.time()
            
            if self.is_first_buffer:
                self._process_first_buffer(current_time)
            else:
                self._process_normal_buffer(current_time)
    
    def _process_first_buffer(self, current_time: float) -> None:
        """处理首次缓冲：超长等待并过滤特殊token"""
        if self.first_buffer_start_time == 0:
            self.first_buffer_start_time = current_time
            logger.debug(f"首次缓冲开始，等待{self.first_buffer_duration}秒检查特殊token")
        
        # 首次缓冲必须等待足够时间
        if current_time - self.first_buffer_start_time >= self.first_buffer_duration:
            self._send_buffer_content(is_first=True)
            self.is_first_buffer = False
    
    def _process_normal_buffer(self, current_time: float) -> None:
        """处理普通缓冲：时间或字数触发"""
        if (current_time - self.last_stream_flush_time >= self.stream_buffer_duration 
            or len(self.stream_buffer) >= 5):
            self._send_buffer_content(is_first=False)
    
    def _send_buffer_content(self, is_first: bool = False) -> None:
        """过滤并发送缓冲池内容到TTS"""
        filtered_content = self._filter_special_tokens(self.stream_buffer)
        
        if (filtered_content.strip() 
            and self.current_tts_stream is not None 
            and self.tts_consecutive_fail_count < self.MAX_TTS_RETRY):
            try:
                self.current_tts_stream.append_text(filtered_content)
                if is_first:
                    logger.debug(f"首次缓冲发送完成，过滤前:{len(self.stream_buffer)}字，过滤后:{len(filtered_content)}字")
            except Exception as e:
                logger.error(f"发送缓冲内容到TTS失败: {e}")
        
        self.stream_buffer = ""
        self.last_stream_flush_time = time.time()
    
    def _filter_special_tokens(self, content: str) -> str:
        """过滤特殊token"""
        filtered = content.replace(self.EXIT_TOKEN, "")
        filtered = filtered.replace(self.SWITCH_LISTEN_TOKEN, "")
        filtered = filtered.replace(self.PUSH_TOKEN, "")
        filtered = re.sub(
            r'(?:标题[：:].*?(?=时间[：:]|地点[：:]|内容[：:]|好|请|已|收|记|$))'
            r'|(?:时间[：:].*?(?=地点[：:]|内容[：:]|好|请|已|收|记|$))'
            r'|(?:地点[：:].*?(?=内容[：:]|好|请|已|收|记|$))'
            r'|(?:内容[：:].*?(?=好|请|已|收|记|$))',
            '', filtered, flags=re.DOTALL
        )
        if not self.start_task_mode:
            filtered = re.sub(r'```json.*?```', '', filtered, flags=re.DOTALL)
            filtered = re.sub(r'\{\"function_name\".*?\}', '', filtered, flags=re.DOTALL)
        return filtered

    def _init_stream_connection(self) -> None:
        try:
            need_connect = False
            with self._tts_lock:
                if (self.current_tts_stream is None
                    or self.current_tts_stream.client is None
                    or not self.current_tts_stream.is_alive()):
                    need_connect = True
                else:
                    self.current_tts_stream.reset()
                    logger.debug("复用已有TTS连接")
                    self.tts_consecutive_fail_count = 0
                    return
            
            if need_connect:
                now = time.time()
                if now - self.last_tts_retry_time < self.TTS_RETRY_CD:
                    logger.debug(f"TTS重连冷却中，剩余{self.TTS_RETRY_CD - (now - self.last_tts_retry_time):.0f}秒，放弃本次连接")
                    return
                new_stream = QwenTtsRealtimeStream(self.stream_tts_config, self.stream_player)
                new_stream.connect()
                with self._tts_lock:
                    self.current_tts_stream = new_stream
                    self.last_tts_retry_time = 0
                    self.tts_consecutive_fail_count = 0
                logger.debug("TTS连接初始化完成")
        except Exception as e:
            self.tts_consecutive_fail_count += 1
            logger.error(f"TTS初始化失败（第{self.tts_consecutive_fail_count}次）: {e}")
            if self.tts_consecutive_fail_count >= self.MAX_TTS_RETRY:
                logger.error(f"TTS连续失败{self.MAX_TTS_RETRY}次，放弃本次TTS播放，请检查服务状态")

    def _check_and_reconnect_stream(self) -> None:
        if self.current_tts_stream.is_alive():
            return
        
        now = time.time()
        if now - self.last_tts_retry_time < self.TTS_RETRY_CD:
            logger.debug(f"TTS重连冷却中，剩余{self.TTS_RETRY_CD - (now - self.last_tts_retry_time):.0f}秒，放弃本次重连")
            return
        try:
            self.current_tts_stream.connect()
            self.last_tts_retry_time = 0
            logger.debug("TTS连接断开，自动重连成功")
        except Exception as e:
            self.last_tts_retry_time = now
            self.tts_consecutive_fail_count += 1
            logger.error(f"TTS重连失败（第{self.tts_consecutive_fail_count}次）: {e}")
            if self.tts_consecutive_fail_count >= self.MAX_TTS_RETRY:
                logger.error(f"TTS连续失败{self.MAX_TTS_RETRY}次，放弃本次TTS播放，请检查服务状态")
                with self._tts_lock:
                    self.current_tts_stream = None

    def _chat_flush_tts(self) -> None:
        if self.current_tts_stream is not None and self.tts_consecutive_fail_count < self.MAX_TTS_RETRY:
            if self.stream_buffer.strip():
                filtered_content = self._filter_special_tokens(self.stream_buffer)
                if filtered_content.strip():
                    try:
                        self.current_tts_stream.append_text(filtered_content)
                        if self.is_first_buffer:
                            logger.debug(f"首次缓冲提前刷新发送，过滤前:{len(self.stream_buffer)}字，过滤后:{len(filtered_content)}字")
                    except Exception as e:
                        logger.error(f"发送剩余缓冲内容到TTS失败: {e}")
            self.is_first_buffer = False
            self.stream_buffer = ""
            self.last_stream_flush_time = time.time()
        if self.tts_consecutive_fail_count >= self.MAX_TTS_RETRY:
            self.tts_consecutive_fail_count = 0

    def _chat_submit_tts(self, full_response: str, need_exit: bool) -> None:
        logger.info(f"LLM回答生成完成，总长度{len(full_response)}字，已流式发送给TTS")
        if self.current_tts_stream is not None:
            self.current_tts_stream.finish(timeout=60)
        else:
            logger.warning("TTS连接不可用，跳过快结束")
        if need_exit:
            logger.info("检测到用户退出意图，等流式播放完成后自动关闭...")
            self.pending_shutdown = True

    def _do_push_notification(self, content: str) -> None:
        if self.bark_notifier is None:
            logger.warning("Bark推送器未初始化，跳过推送")
            return
        try:
            self.bark_notifier.send_formatted(content)
        except Exception as e:
            logger.error(f"Bark推送异常: {e}")

    def _chat_tool_token(self, content: str) -> None:
        with self._tts_lock:
            if self.current_tts_stream is not None:
                self.current_tts_stream.append_text(content)

    def _cleanup_tts(self) -> None:
        with self._tts_lock:
            if self.current_tts_stream:
                try:
                    self.current_tts_stream.close()
                except Exception:
                    pass
                self.current_tts_stream = None
        if self.stream_player is not None:
            try:
                self.stream_player.stop()
            except Exception as e:
                logger.warning(f"流式播放器关闭失败: {e}")

    def _on_llm_error(self) -> None:
        if self.current_tts_stream is not None:
            self.current_tts_stream.reset()

    def _submit_chat(self, text: str, play_wakeup: bool = False) -> None:
        self.last_activity_time = time.time()
        t = threading.Thread(target=self.chat, args=(text, play_wakeup), daemon=True)
        t.start()

    def _submit_task_tts(self, response: str) -> None:
        pass

    def _submit_async_save(self, fn) -> None:
        t = threading.Thread(target=fn, daemon=True)
        t.start()

    def _executor_for_prologue(self):
        return None


# ============================================================
# LocalRobot：本地非流式 TTS 机器人（Qwen3TTS 等）
# ============================================================
class LocalRobot(Robot):
    def _init_tts_specific(self, config: Dict[str, Any]) -> None:
        self.tts_queue = queue.Queue()
        self.play_queue = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1)

        self.current_tts_future = None
        self.skip_current_tts = False
        self._tts_generating = False

        selected_tts = config["selected_module"]["TTS"]
        logger.info(f"已启用非流式TTS模式，当前模型：{selected_tts}")

    def _tts_priority(self) -> None:
        def tts_result_thread():
            while not self.stop_event.is_set():
                try:
                    future = self.tts_queue.get()
                    try:
                        tts_file = future.result()
                    except Exception as e:
                        logger.error(f"TTS 任务出错: {e}")
                        self._tts_generating = False
                        continue
                    self._tts_generating = False
                    if tts_file is None or self.skip_current_tts:
                        if self.skip_current_tts:
                            logger.debug("Skipped TTS task due to interrupt.")
                        continue
                    self.play_queue.put(tts_file)
                except Exception as e:
                    logger.error(f"tts_result_thread: {e}")

        def play_thread():
            while not self.stop_event.is_set():
                try:
                    tts_file = self.play_queue.get(timeout=0.1)
                    if tts_file is not None:
                        self.player.play(tts_file)
                    if (self.pending_shutdown and self.tts_queue.empty()
                        and self.play_queue.empty() and not self.player.get_playing_status()
                        and not self._tts_generating):
                        logger.info("告别语音播放完成，程序即将关闭...")
                        self.shutdown()
                except queue.Empty:
                    if self.pending_shutdown and self.tts_queue.empty() \
                        and self.play_queue.empty() and not self.player.get_playing_status() \
                        and not self._tts_generating:
                        logger.info("告别语音播放完成，程序即将关闭...")
                        self.shutdown()
                    continue
                except Exception as e:
                    logger.error(f"play_thread: {e}")

        tts_result_worker = threading.Thread(target=tts_result_thread, daemon=True)
        tts_result_worker.start()
        play_worker = threading.Thread(target=play_thread, daemon=True)
        play_worker.start()

    def interrupt_playback(self) -> None:
        logger.info("Interrupting current playback and TTS generation.")
        self.pending_shutdown = False
        self.skip_current_tts = True
        self._tts_generating = False
        if self.current_tts_future is not None and not self.current_tts_future.done():
            self.current_tts_future.cancel()
            self.current_tts_future = None
            logger.info("Canceled pending TTS generation task.")
        try:
            while not self.tts_queue.empty():
                self.tts_queue.get_nowait()
            while not self.play_queue.empty():
                self.play_queue.get_nowait()
            logger.info("Cleared all pending TTS and play tasks.")
        except Exception as e:
            logger.debug(f"Clear queue error: {e}")

        try:
            self.executor.shutdown(wait=False, cancel_futures=True)
        except:
            pass
        self.executor = ThreadPoolExecutor(max_workers=1)
        logger.info("Rebuilt thread pool for new TTS tasks.")
        self.player.stop()

    def _chat_reset_tts(self) -> None:
        pass

    def _chat_handle_token(self, content: str) -> None:
        pass

    def _chat_flush_tts(self) -> None:
        pass

    def _chat_submit_tts(self, full_response: str, need_exit: bool) -> None:
        self.skip_current_tts = False
        self._tts_generating = True
        future = self.executor.submit(self.tts.to_tts, full_response)
        self.current_tts_future = future
        self.tts_queue.put(future)
        logger.info(f"LLM回答生成完成，总长度{len(full_response)}字，已加入TTS任务队列")
        if need_exit:
            logger.info("检测到用户退出意图，等TTS播完后自动关闭...")
            self.pending_shutdown = True

    def _chat_tool_token(self, content: str) -> None:
        pass

    def _cleanup_tts(self) -> None:
        try:
            self.executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self.executor.shutdown(wait=False)
        except Exception:
            pass
        try:
            while not self.tts_queue.empty():
                self.tts_queue.get_nowait()
            while not self.play_queue.empty():
                self.play_queue.get_nowait()
        except Exception:
            pass

    def _on_llm_error(self) -> None:
        pass

    def _submit_chat(self, text: str, play_wakeup: bool = False) -> None:
        self.executor.submit(self.chat, text, play_wakeup)

    def _submit_task_tts(self, response: str) -> None:
        self._tts_generating = True
        future = self.executor.submit(self.speak_and_play, response)
        self.tts_queue.put(future)

    def _submit_async_save(self, fn) -> None:
        self.executor.submit(fn)

    def _executor_for_prologue(self):
        return self.executor


def create_robot(config_file: str, websocket: Optional[Any] = None, loop: Optional[Any] = None) -> Robot:
    config = read_config(config_file)
    selected_tts = config["selected_module"]["TTS"]
    if selected_tts == "QwenTtsRealtimeAPI":
        return StreamRobot(config_file, websocket, loop)
    else:
        return LocalRobot(config_file, websocket, loop)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小爱机器人")
    parser.add_argument('config_path', type=str, help="配置文件", default=None)
    args = parser.parse_args()
    config_path = args.config_path

    robot = create_robot(config_path)
    robot.run()
