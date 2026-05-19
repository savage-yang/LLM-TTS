import time
from abc import ABC, abstractmethod
import threading
import queue
import logging
import pyaudio
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AbstractRecorder(ABC):
    """录音器抽象基类，定义通用接口"""

    @abstractmethod
    def start_recording(self, audio_queue: queue.Queue) -> None:
        """
        开始录音
        
        Args:
            audio_queue: 音频数据队列
        """
        pass

    @abstractmethod
    def stop_recording(self) -> None:
        """停止录音"""
        pass


class RecorderPyAudio(AbstractRecorder):
    """使用PyAudio的录音器实现"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化录音器
        
        Args:
            config: 配置字典（可选）
        """
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000
        self.chunk = 512
        self.py_audio = pyaudio.PyAudio()
        self.stream = None
        self.thread = None
        self.running = False

    def start_recording(self, audio_queue: queue.Queue) -> None:
        """
        开始录音并将音频数据放入队列
        
        Args:
            audio_queue: 音频数据队列
        
        Raises:
            RuntimeError: 录音流已在运行
        """
        if self.running:
            raise RuntimeError("Stream already running")

        def stream_thread() -> None:
            """录音线程主函数"""
            try:
                self.stream = self.py_audio.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.rate,
                    input=True,
                    frames_per_buffer=self.chunk
                )
                self.running = True
                while self.running:
                    data = self.stream.read(self.chunk, exception_on_overflow=False)
                    audio_queue.put(data)
            except Exception as e:
                logger.error(f"Error in stream: {e}")
            finally:
                self.stop_recording()

        self.thread = threading.Thread(target=stream_thread, daemon=True)
        self.thread.start()

    def stop_recording(self) -> None:
        """停止录音并释放资源"""
        if not self.running:
            return

        self.running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if self.py_audio:
            self.py_audio.terminate()

        if self.thread:
            self.thread.join()
            self.thread = None

    def __del__(self) -> None:
        """析构函数，确保资源被清理"""
        self.stop_recording()



class WebSocketRecorder(AbstractRecorder):
    """通过WebSocket接收前端音频，并进行后端分帧处理"""

    def __init__(self, config):
        self.running = True
        self.audio_queue: queue.Queue = None
        self._buffer = bytearray()
        self._frame_size_bytes = 512 * 2  # 512 samples × 2 bytes/sample for 16kHz Int16 PCM

    def start_recording(self, audio_queue: queue.Queue):
        self.audio_queue = audio_queue
        self.running = True

    def put_audio(self, data: bytes):
        """接收原始 PCM 数据，将其缓冲并分帧后存入 audio_queue"""
        if not self.running:
            logger.info(f"录音已暂停，丢弃数据")
            return
        # 累积数据
        self._buffer.extend(data)

        # 按 512 样本（1024 字节）分片
        while len(self._buffer) >= self._frame_size_bytes:
            chunk = bytes(self._buffer[:self._frame_size_bytes])
            # 放入队列
            try:
                self.audio_queue.put(chunk, block=False)
            except queue.Full:
                logger.warning("audio_queue 已满，丢弃一帧音频")
            # 移除已用数据
            del self._buffer[:self._frame_size_bytes]

    def stop_recording(self):
        """停止录音，并将缓冲区剩余数据清理"""
        self.running = False
        if hasattr(self, '_buffer'):
            if self._buffer:
                logger.info(f"剩余缓冲数据未满一帧：{len(self._buffer)} 字节，将被丢弃")
            self._buffer.clear()
        logger.info("录音已停止")





def create_instance(class_name: str, *args: Any, **kwargs: Any) -> AbstractRecorder:
    """
    创建录音器实例的工厂函数
    
    Args:
        class_name: 录音器类名
        *args: 位置参数
        **kwargs: 关键字参数
    
    Returns:
        录音器实例
    
    Raises:
        ValueError: 类名不存在
    """
    cls = globals().get(class_name)
    if cls:
        return cls(*args, **kwargs)
    raise ValueError(f"Class {class_name} not found")


if __name__ == "__main__":
    audio_queue = queue.Queue()
    recorderPyAudio = RecorderPyAudio()
    recorderPyAudio.start_recording(audio_queue)
    time.sleep(10)

