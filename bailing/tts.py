import asyncio
import logging
import os
import re
import time
import uuid
import threading
from abc import ABC, ABCMeta, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
import torch
import soundfile as sf
import base64
import dashscope
from dashscope.audio.qwen_tts_realtime import QwenTtsRealtime, QwenTtsRealtimeCallback, AudioFormat

logger = logging.getLogger(__name__)


def filter_special_tokens(text: str) -> str:
    """过滤文本中的特殊控制标记，避免TTS朗读"""
    # 过滤<|...|>格式的特殊标记
    text = re.sub(r'<\|.*?\|>', '', text)
    return text.strip()


class AbstractTTS(ABC):
    """TTS 抽象基类，定义 TTS 接口"""
    __metaclass__ = ABCMeta

    @abstractmethod
    def to_tts(self, text: str) -> Optional[str]:
        """
        将文本转换为语音

        Args:
            text: 要转换的文本

        Returns:
            TTS 文件路径，失败返回 None
        """
        pass


class Qwen3TTS(AbstractTTS):
    """Qwen3 本地 TTS 模型（音色克隆）"""

    def __init__(self, config: Dict[str, Any]):
        """
        config keys:
          - model_path: 本地模型路径 (e.g. D:/bailing-main/Qwen3-TTS-12Hz-1.7B-Base)
          - ref_audio: 参考音频路径 (用于音色克隆)
          - ref_text: 参考音频文本
          - language: 语言 (e.g. "Chinese")
          - output_dir: 输出目录
          - dtype: 数据类型 (default: "bfloat16")
        """
        import torch
        from qwen_tts import Qwen3TTSModel
        
        self.model_path = config.get("model_path")
        self.ref_audio = config.get("ref_audio")
        self.ref_text = config.get("ref_text", "")
        self.language = config.get("language", "Chinese")
        self.output_dir = config.get("output_dir", "tmp/")
        self.dtype = config.get("dtype", "bfloat16")
        
        # 转换 dtype
        if self.dtype == "bfloat16":
            self.torch_dtype = torch.bfloat16
        else:
            self.torch_dtype = torch.float32
        
        # 加载模型
        logger.info(f"[Qwen3TTS] 正在加载模型: {self.model_path}")
        self.model = Qwen3TTSModel.from_pretrained(
            self.model_path,
            dtype=self.torch_dtype,
        )
        logger.info(f"[Qwen3TTS] 模型加载完成")
        
        # 创建音色克隆提示
        self.voice_clone_prompt = None
        
        # 先检查文件是否存在
        if self.ref_audio and not os.path.exists(self.ref_audio):
            logger.error(f"[Qwen3TTS] 参考音频不存在: {self.ref_audio}")
            raise FileNotFoundError(f"参考音频不存在: {self.ref_audio}")
        
        if self.ref_audio and self.ref_text:
            try:
                logger.info(f"[Qwen3TTS] 正在创建音色克隆，参考音频: {self.ref_audio}")
                self.voice_clone_prompt = self.model.create_voice_clone_prompt(
                    ref_audio=self.ref_audio,
                    ref_text=self.ref_text,
                )
                logger.info(f"[Qwen3TTS] 音色克隆提示创建成功")
            except Exception as e:
                logger.error(f"[Qwen3TTS] 音色克隆失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise  # 抛出错误，让问题更明显
    
    def _generate_filename(self) -> str:
        """生成唯一的输出文件名"""
        return os.path.join(self.output_dir, f"tts-{datetime.now().date()}@{uuid.uuid4().hex}.wav")
    
    def _log_execution_time(self, start_time: float) -> None:
        """记录执行时间"""
        end_time = time.time()
        execution_time = end_time - start_time
        logger.debug(f"[Qwen3TTS] Execution Time: {execution_time:.2f} seconds")
    
    def to_tts(self, text: str) -> Optional[str]:
        text = filter_special_tokens(text)
        if not text:
            return None
        output_file = self._generate_filename()
        start_time = time.time()
        
        try:
            if self.voice_clone_prompt is None:
                logger.error(f"[Qwen3TTS] voice_clone_prompt 为 None，请检查参考音频和文本配置")
                return None
                
            wavs, sr = self.model.generate_voice_clone(
                text=text,
                language=self.language,
                voice_clone_prompt=self.voice_clone_prompt,
                do_sample=False,
                max_audio_length=512,
            )
            
            sf.write(output_file, wavs[0], sr)
            end_time = time.time()
            execution_time = end_time - start_time
            logger.info(f"[Qwen3TTS] 语音合成完成，耗时: {execution_time:.2f}秒，文本长度: {len(text)}字，输出文件: {output_file}")
            return output_file
        except Exception as e:
            logger.error(f"[Qwen3TTS] Failed to generate TTS: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

class QwenTtsRealtimeAPI(AbstractTTS):
    """占位类，仅用于配置标识，实际流式TTS功能由QwenTtsRealtimeStream实现"""
    def __init__(self, config: Dict[str, Any]):
        pass
    
    def to_tts(self, text: str) -> Optional[str]:
        text = filter_special_tokens(text)
        if not text:
            return None
        return None

class QwenTtsRealtimeStream:
    """纯流式Qwen TTS API，边收文本边生成音频，直接喂给播放器"""

    def __init__(self, config: Dict[str, Any], stream_player):
        """
        初始化 QwenTtsRealtimeStream

        Args:
            config: 配置字典
            stream_player: 流式播放器实例
        """
        self.config = config
        self.api_key = config.get("api_key")
        self.model = config.get("model", "qwen3-tts-flash-realtime")
        self.voice = config.get("voice", "Cherry")
        self.url = config.get("url", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime")
        self.stream_player = stream_player
        self.client = None
        
        # 初始化API Key
        dashscope.api_key = self.api_key
        
        # 自定义回调，收到音频直接喂播放器
        class StreamCallback(QwenTtsRealtimeCallback):
            def __init__(self, player):
                super().__init__()
                self.player = player
                self.complete_event = threading.Event()
                self.is_connected = False  # 自己维护连接状态，避免依赖客户端内部状态误判

            def on_open(self) -> None:
                logger.debug("[QwenTtsStream] 连接已建立")
                self.is_connected = True

            def on_close(self, close_status_code, close_msg) -> None:
                logger.debug(f"[QwenTtsStream] 连接关闭 code={close_status_code}, msg={close_msg}")
                self.is_connected = False
                self.complete_event.set()

            def on_event(self, response: dict) -> None:
                try:
                    event_type = response.get('type', '')
                    if event_type == 'response.audio.delta':
                        # 收到音频块直接喂给播放器，实时播放
                        audio_data = base64.b64decode(response['delta'])
                        self.player.feed_audio(audio_data)
                    elif event_type == 'session.finished':
                        logger.debug("[QwenTtsStream] 音频生成完成")
                        # 发送完成信号到前端
                        if hasattr(self.player, 'finish'):
                            self.player.finish()
                        self.complete_event.set()
                    elif 'error' in response or event_type == 'error':
                        # 收到错误信息也直接结束会话，避免卡死
                        logger.error(f"[QwenTtsStream] TTS服务返回错误：{response.get('error', '未知错误')}")
                        self.complete_event.set()
                except Exception as e:
                    logger.error(f"[QwenTtsStream] 回调异常：{e}")
                    # 异常也要触发结束事件，避免死等
                    self.complete_event.set()
        
        self.callback = StreamCallback(stream_player)
        self.last_connect_time = 0  # 最后一次建连时间，避免短时间重复建连

    def connect(self) -> None:
        """建立TTS连接，每轮对话开始前调用一次，最多重试1次，每次间隔2秒"""
        max_retry = 1
        retry_count = 0
        while retry_count < max_retry:
            try:
                self.client = QwenTtsRealtime(
                    model=self.model,
                    callback=self.callback,
                    url=self.url
                )
                # 加连接超时，避免卡住
                connect_thread = threading.Thread(target=self.client.connect, daemon=True)
                connect_thread.start()
                connect_thread.join(timeout=10)
                if connect_thread.is_alive():
                    raise TimeoutError("TTS服务连接超时，请检查网络或API配置")
                # 配置会话
                session_config = {
                    "voice": self.voice,
                    "response_format": AudioFormat.PCM_24000HZ_MONO_16BIT,
                    "mode": "server_commit"
                }
                # 禁用TTS服务端的标点分句缓冲，强制收到文本就立刻合成，降低延迟
                if self.config.get("disable_tts_sentence_buffer", True):
                    session_config["enable_sentence_detection"] = False
                    session_config["first_packet_priority"] = True
                self.client.update_session(**session_config)
                self.callback.complete_event.clear()
                self.last_connect_time = time.time()  # 记录建连成功时间
                logger.info("[QwenTtsStream] TTS连接建立完成，准备接收文本")
                return
            except Exception as e:
                retry_count += 1
                self.callback.is_connected = False  # 连接失败标记为未连接
                logger.warning(f"[QwenTtsStream] TTS连接失败，第{retry_count}/{max_retry}次重试：{e}")
                if retry_count < max_retry:
                    time.sleep(2)  # 重试间隔2秒，避免触发更严格限流
                else:
                    logger.error(f"[QwenTtsStream] TTS连接失败超过{max_retry}次，放弃连接，请检查API配置或网络")
                    raise e

    def append_text(self, text: str) -> None:
        """追加流式输入的文本，LLM返回一个token就调用一次"""
        if self.client and text:
            # 过滤特殊控制标记，避免TTS朗读
            text = filter_special_tokens(text)
            if text:  # 过滤后如果为空就不发送
                self.client.append_text(text)
                logger.debug(f"[QwenTtsStream] 追加文本: {text}")

    def finish(self, timeout: int = 30) -> None:
        """文本全部输入完成，调用后等待音频生成播放完成，支持超时防止卡死"""
        if self.client:
            self.client.finish()
            # 等待所有音频生成播放完成，最多等timeout秒，超时直接结束
            try:
                finished = self.callback.complete_event.wait(timeout=timeout)
                if not finished:
                    logger.warning(f"[QwenTtsStream] TTS会话超时，已等待{timeout}秒未收到结束信号，强制结束")
            except Exception as e:
                logger.warning(f"[QwenTtsStream] 等待TTS结束异常: {e}")
            finally:
                # 不管有没有完成，都重置会话，不关闭连接保持复用
                self.reset()
                logger.debug("[QwenTtsStream] 本轮对话TTS处理完成，连接保持")

    def reset(self) -> None:
        """重置会话状态，不用关闭连接，下次直接复用"""
        if self.client:
            try:
                # 清空回调状态
                self.callback.complete_event.clear()
            except Exception:
                pass
        logger.debug("[QwenTtsStream] 会话已重置，连接保持")
        
    def is_alive(self) -> bool:
        """检查连接是否还存活，自己维护状态+60秒建连保护期，避免LLM长时间等待期间误判"""
        if not self.client or not self.callback.is_connected:
            return False
        # 建连成功60秒内直接认为存活，覆盖LLM首token延迟场景
        if time.time() - self.last_connect_time < 60:
            return True
        # 超过10秒再校验底层连接状态
        try:
            return hasattr(self.client, '_session') and self.client._session and self.client._session.active
        except Exception:
            return False

    def close(self) -> None:
        """关闭连接，程序退出时才调用"""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
        self.callback.is_connected = False
        logger.debug("[QwenTtsStream] TTS连接已关闭")

def create_instance(class_name: str, *args, **kwargs):
    """
    工厂函数，创建 TTS 实例

    Args:
        class_name: TTS 类名
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        TTS 实例

    Raises:
        ValueError: 类名不存在
    """
    # 获取类对象
    cls = globals().get(class_name)
    if cls:
        # 创建并返回实例
        return cls(*args, **kwargs)
    else:
        raise ValueError(f"Class {class_name} not found")
