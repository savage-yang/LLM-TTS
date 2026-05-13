import numpy as np
import torch
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
from silero_vad import load_silero_vad, VADIterator

logger = logging.getLogger(__name__)


class VAD(ABC):
    """VAD（语音活动检测）抽象基类"""

    @abstractmethod
    def is_vad(self, data: bytes) -> Optional[Dict[str, Any]]:
        """
        判断是否有语音活动

        Args:
            data: 音频数据

        Returns:
            VAD 检测结果，无语音返回 None
        """
        pass

    def reset_states(self) -> None:
        """重置 VAD 状态"""
        pass


class SileroVAD(VAD):
    """Silero 语音活动检测器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 SileroVAD

        Args:
            config: 配置字典，包含:
                - sampling_rate: 采样率
                - threshold: 阈值
                - min_silence_duration_ms: 最小静音时长（毫秒）
        """
        logger.debug(f"SileroVAD initialized with config: {config}")
        self.model = load_silero_vad()
        self.sampling_rate = config.get("sampling_rate")
        self.threshold = config.get("threshold")
        self.min_silence_duration_ms = config.get("min_silence_duration_ms")
        self.vad_iterator = VADIterator(
            self.model,
            threshold=self.threshold,
            sampling_rate=self.sampling_rate,
            min_silence_duration_ms=self.min_silence_duration_ms
        )
        logger.debug(f"VAD Iterator initialized")

    @staticmethod
    def int2float(sound: np.ndarray) -> np.ndarray:
        """
        将 int16 音频数据转换为 float32

        Args:
            sound: int16 格式的音频数组

        Returns:
            float32 格式的音频数组
        """
        sound = sound.astype(np.float32) / 32768.0
        return sound

    def is_vad(self, data: bytes) -> Optional[Dict[str, Any]]:
        try:
            audio_int16 = np.frombuffer(data, dtype=np.int16)
            audio_float32 = self.int2float(audio_int16)
            vad_output = self.vad_iterator(torch.from_numpy(audio_float32))
            if vad_output is not None:
                logger.debug(f"VAD output: {vad_output}")
            return vad_output
        except Exception as e:
            logger.error(f"Error in VAD processing: {e}")
            return None

    def reset_states(self) -> None:
        """重置 VAD 内部状态"""
        try:
            self.vad_iterator.reset_states()
            logger.debug("VAD states reset.")
        except Exception as e:
            logger.error(f"Error resetting VAD states: {e}")


def create_instance(class_name: str, *args, **kwargs):
    """
    工厂函数，创建 VAD 实例

    Args:
        class_name: VAD 类名
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        VAD 实例

    Raises:
        ValueError: 类名不存在
    """
    cls = globals().get(class_name)
    if cls:
        return cls(*args, **kwargs)
    else:
        raise ValueError(f"Class {class_name} not found")
