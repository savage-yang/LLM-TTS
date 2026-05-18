import logging
import platform
import queue
import threading
import wave
import random
from pydub import AudioSegment
import pygame
import numpy as np
import os
import time
import pyaudio
import io
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class AbstractPlayer(object):
    """音频播放器抽象基类，定义通用接口"""

    def __init__(self, *args: Any, **kwargs: Any):
        super(AbstractPlayer, self).__init__()
        self.is_playing = False
        self.play_queue = queue.Queue()
        self._stop_event = threading.Event()
        self.consumer_thread = threading.Thread(target=self._playing, daemon=True)
        self.consumer_thread.start()

    @staticmethod
    def to_wav(audio_file: str) -> str:
        """
        将音频文件转换为WAV格式
        
        Args:
            audio_file: 输入音频文件路径
        
        Returns:
            WAV格式文件路径
        """
        if audio_file.endswith(".wav"):
            return audio_file
        tmp_file = audio_file + ".wav"
        wav_file = AudioSegment.from_file(audio_file)
        wav_file.export(tmp_file, format="wav")
        return tmp_file

    def _playing(self) -> None:
        """播放线程主循环"""
        while not self._stop_event.is_set():
            data = self.play_queue.get()
            self.is_playing = True
            try:
                self.do_playing(data)
            except Exception as e:
                logger.error(f"播放音频失败: {e}")
            finally:
                self.play_queue.task_done()
                self.is_playing = False

    def play(self, data: str) -> None:
        """
        播放音频文件
        
        Args:
            data: 音频文件路径
        """
        logger.info(f"play file {data}")
        audio_file = self.to_wav(data)
        self.play_queue.put(audio_file)

    def stop(self) -> None:
        """停止播放，清空队列"""
        self._clear_queue()

    def shutdown(self) -> None:
        """关闭播放器，释放资源"""
        self._clear_queue()
        self._stop_event.set()
        if self.consumer_thread.is_alive():
            self.consumer_thread.join()

    def get_playing_status(self) -> bool:
        """
        检查是否正在播放
        
        Returns:
            正在播放返回True，否则返回False
        """
        return self.is_playing or (not self.play_queue.empty())

    def _clear_queue(self) -> None:
        """清空播放队列"""
        with self.play_queue.mutex:
            self.play_queue.queue.clear()

    def do_playing(self, audio_file: str) -> None:
        """
        播放音频的具体实现，由子类实现
        
        Args:
            audio_file: 音频文件路径
        """
        raise NotImplementedError("Subclasses must implement do_playing")

    def feed_audio(self, audio_data: bytes) -> None:
        """
        流式播放：喂入PCM音频块，默认不支持
        
        Args:
            audio_data: PCM音频数据
        """
        raise NotImplementedError("This player does not support stream playback")

    def clear_buffer(self) -> None:
        """流式播放：清空缓冲区，默认不支持"""
        raise NotImplementedError("This player does not support stream buffer operation")

    def play_prologue(self, executor: Optional[Any] = None) -> bool:
        """
        播放启动开场白音效，非阻塞异步播放
        
        Args:
            executor: 线程池执行器
        
        Returns:
            是否成功播放
        """
        root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prologue_path = os.path.join(root_path, "voice_cache", "prologue.wav")
        if os.path.exists(prologue_path):
            logger.info("正在播放启动音效...")
            if executor:
                executor.submit(self.play, prologue_path)
            else:
                self.play(prologue_path)
            return True
        else:
            logger.debug(f"启动音效文件不存在：{prologue_path}，跳过播放")
            return False

    def play_buffer_sound(
        self,
        buffer_config: Dict[str, Any],
        executor: Optional[Any] = None
    ) -> Tuple[threading.Event, bool]:
        """
        智能播放缓冲音效，返回等待事件和是否播放状态
        
        Args:
            buffer_config: 缓冲音效配置
            executor: 线程池执行器
        
        Returns:
            (等待事件, 是否播放) 元组
        """
        finish_event = threading.Event()
        finish_event.set()
        played = False

        if not buffer_config.get("enabled", True):
            return finish_event, played

        buffer_dir = buffer_config.get("file_dir", "voice_cache")
        prefix = buffer_config.get("file_prefix", "voice")
        root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_buffer_dir = os.path.join(root_path, buffer_dir)

        # 找所有符合条件的音效文件
        sound_files = []
        if os.path.exists(full_buffer_dir):
            for f in os.listdir(full_buffer_dir):
                if f.lower().startswith(prefix.lower()) and f.lower().endswith(".wav"):
                    sound_files.append(os.path.join(full_buffer_dir, f))

        if not sound_files:
            return finish_event, played

        # 随机选一个音效
        selected_sound = random.choice(sound_files)
        finish_event.clear()
        played = True

        def _play() -> None:
            try:
                logger.debug(f"播放缓冲音效：{os.path.basename(selected_sound)}")
                self.play(selected_sound)
                # 等待播放完成
                while self.get_playing_status():
                    time.sleep(0.05)
            except Exception as e:
                logger.warning(f"缓冲音效播放失败：{e}")
            finally:
                finish_event.set()

        if executor:
            executor.submit(_play)
        else:
            _play()

        return finish_event, played


class PygamePlayer(AbstractPlayer):
    """使用Pygame播放音频（支持淡入淡出避免爆音）"""

    def __init__(self, *args: Any, **kwargs: Any):
        super(PygamePlayer, self).__init__(*args, **kwargs)
        pygame.mixer.init()
        # 初始化后播放250ms静音预加载，充分预热声卡设备，完全避免开头爆音
        self._play_silence(duration=250)

    def _play_silence(self, duration: int = 100) -> None:
        """
        播放静音帧，用于预加载和避免爆音
        
        Args:
            duration: 静音时长（毫秒）
        """
        try:
            sample_rate = 24000
            silence = np.zeros(int(sample_rate * duration / 1000), dtype=np.int16)
            buffer = io.BytesIO()
            import wave
            with wave.open(buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(silence.tobytes())
            buffer.seek(0)
            pygame.mixer.music.load(buffer)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        except Exception as e:
            logger.debug(f"静音预加载失败: {e}")

    def do_playing(self, audio_file: str) -> None:
        """
        使用Pygame播放音频（带淡入）
        
        Args:
            audio_file: 音频文件路径
        """
        try:
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(100)
            logger.debug("PygamePlayer 加载音频中")
            pygame.mixer.music.load(audio_file)
            logger.debug("PygamePlayer 加载音频结束，开始播放")
            # 开头100ms淡入，避免爆音
            pygame.mixer.music.set_volume(0)
            pygame.mixer.music.play()
            start_time = time.time()
            while time.time() - start_time < 0.1:
                volume = (time.time() - start_time) * 10
                pygame.mixer.music.set_volume(min(volume, 1.0))
                pygame.time.Clock().tick(100)
            pygame.mixer.music.set_volume(1.0)
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(100)
            logger.debug(f"播放完成：{audio_file}")
        except Exception as e:
            logger.error(f"播放音频失败: {e}")

    def get_playing_status(self) -> bool:
        """
        检查是否正在播放
        
        Returns:
            正在播放返回True，否则返回False
        """
        return self.is_playing or (not self.play_queue.empty()) or pygame.mixer.music.get_busy()

    def stop(self) -> None:
        """停止播放（带淡出避免爆音）"""
        super().stop()
        # 停止前先50ms淡出，避免咔哒爆音
        if pygame.mixer.music.get_busy():
            start_time = time.time()
            while time.time() - start_time < 0.05:
                volume = 1.0 - (time.time() - start_time) * 20
                pygame.mixer.music.set_volume(max(volume, 0.0))
                pygame.time.Clock().tick(100)
        pygame.mixer.music.stop()
        pygame.mixer.music.set_volume(1.0)


class PygameStreamPlayer(AbstractPlayer):
    """实时PCM流播放器，支持边接收边播放，无文件落地"""

    def __init__(self, config: Optional[Dict[str, Any]] = None, *args: Any, **kwargs: Any):
        """
        初始化流式播放器
        
        Args:
            config: 配置字典
        """
        super(PygameStreamPlayer, self).__init__(*args, **kwargs)
        # 从配置读取参数，默认值适配Qwen流式TTS
        sample_rate = config.get('sample_rate', 24000) if config else 24000
        channels = config.get('channels', 1) if config else 1

        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=sample_rate,
            output=True,
            frames_per_buffer=1024
        )
        self.audio_queue = queue.Queue()
        self.running = True
        self.play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self.play_thread.start()
        logger.info("[StreamPlayer] 流式播放器初始化完成")

    def _play_loop(self) -> None:
        """播放循环，从队列取音频块实时播放"""
        while self.running:
            try:
                audio_data = self.audio_queue.get(timeout=0.1)
                self.stream.write(audio_data)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[StreamPlayer] 播放异常: {e}")

    def feed_audio(self, audio_data: bytes) -> None:
        """
        喂入PCM音频块，自动播放
        
        Args:
            audio_data: PCM音频数据
        """
        self.audio_queue.put(audio_data)

    def stop(self) -> None:
        """停止播放，清空缓冲区"""
        super().stop()
        self.running = False
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        # 清空队列
        self.clear_buffer()
        logger.info("[StreamPlayer] 流式播放器已停止")

    def clear_buffer(self) -> None:
        """清空播放缓冲区，用于打断场景"""
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except Exception:
                pass
        logger.debug("[StreamPlayer] 播放缓冲区已清空")

    def do_playing(self, audio_file: str) -> None:
        """
        也支持播放完整音频文件，兼容原有接口
        
        Args:
            audio_file: 音频文件路径
        """
        try:
            with wave.open(audio_file, 'rb') as wf:
                data = wf.readframes(1024)
                while data:
                    self.feed_audio(data)
                    data = wf.readframes(1024)
            logger.debug(f"播放完成：{audio_file}")
        except Exception as e:
            logger.error(f"播放音频失败: {e}")


def create_instance(class_name: str, *args: Any, **kwargs: Any) -> AbstractPlayer:
    """
    创建播放器实例的工厂函数
    
    Args:
        class_name: 播放器类名
        *args: 位置参数
        **kwargs: 关键字参数
    
    Returns:
        播放器实例
    
    Raises:
        ValueError: 类名不存在
    """
    cls = globals().get(class_name)
    if cls:
        return cls(*args, **kwargs)
    raise ValueError(f"Player class {class_name} not found")
