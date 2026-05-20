import os
import uuid
import wave
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
import logging
from datetime import datetime
import numpy as np
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

logger = logging.getLogger(__name__)


class ASR(ABC):
    """ASR（自动语音识别）抽象基类"""

    @staticmethod
    def _save_audio_to_file(audio_data: List[bytes], file_path: str) -> None:
        """
        将音频数据保存为 WAV 文件

        Args:
            audio_data: 音频数据列表
            file_path: 输出文件路径

        Raises:
            Exception: 保存失败时抛出异常
        """
        try:
            with wave.open(file_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b''.join(audio_data))
            logger.info(f"ASR识别文件录音保存到：{file_path}")
        except Exception as e:
            logger.error(f"保存音频文件时发生错误: {e}")
            raise

    @abstractmethod
    def recognizer(self, stream_in_audio: List[bytes]) -> Tuple[Optional[str], Optional[str]]:
        """
        处理输入音频流并返回识别的文本

        Args:
            stream_in_audio: 输入音频数据列表

        Returns:
            (识别的文本, 临时文件路径)
        """
        pass


class FunASR(ASR):
    """FunASR 语音识别器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 FunASR

        Args:
            config: 配置字典，包含:
                - model_dir: 模型目录
                - output_file: 输出目录
        """
        self.model_dir = config.get("model_dir")
        self.output_dir = config.get("output_file")

        self.model = AutoModel(
            model=self.model_dir,
            vad_kwargs={"max_single_segment_time": 30000},
            disable_update=True,
            hub="hf"
        )

        self._warmup()

    def _warmup(self):
        """预热ASR模型，触发推理引擎内部懒加载（ONNX Runtime Session创建、JIT编译等）"""
        try:
            warmup_file = os.path.join(self.output_dir, ".warmup_silence.wav")
            self._save_warmup_audio(warmup_file)
            self.model.generate(
                input=warmup_file,
                cache={},
                language="auto",
                use_itn=True,
                batch_size_s=60,
            )
            if os.path.exists(warmup_file):
                os.remove(warmup_file)
            logger.info("ASR模型预热完成")
        except Exception as e:
            logger.warning(f"ASR模型预热失败（不影响正常使用）: {e}")

    @staticmethod
    def _save_warmup_audio(file_path: str) -> None:
        """生成100ms静音WAV文件用于预热"""
        sample_rate = 16000
        duration_ms = 100
        num_samples = int(sample_rate * duration_ms / 1000)
        silence_data = (np.zeros(num_samples, dtype=np.int16)).tobytes()

        with wave.open(file_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(silence_data)

    def recognizer(self, stream_in_audio: List[bytes]) -> Tuple[Optional[str], Optional[str]]:
        """
        识别音频流内容

        Args:
            stream_in_audio: 输入音频数据列表

        Returns:
            (识别的文本, 临时文件路径)
        """
        try:
            tmpfile = os.path.join(self.output_dir, f"asr-{datetime.now().date()}@{uuid.uuid4().hex}.wav")
            self._save_audio_to_file(stream_in_audio, tmpfile)

            res = self.model.generate(
                input=tmpfile,
                cache={},
                language="auto",  # 语言选项: "zn", "en", "yue", "ja", "ko", "nospeech"
                use_itn=True,
                batch_size_s=60,
            )

            text = rich_transcription_postprocess(res[0]["text"])
            logger.info(f"识别文本: {text}")
            return text, tmpfile

        except Exception as e:
            logger.error(f"ASR识别过程中发生错误: {e}")
            return None, None


def create_instance(class_name: str, *args, **kwargs):
    """
    工厂函数，创建 ASR 实例

    Args:
        class_name: ASR 类名
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        ASR 实例

    Raises:
        ValueError: 类名不存在
    """
    cls = globals().get(class_name)
    if cls:
        return cls(*args, **kwargs)
    else:
        raise ValueError(f"Class {class_name} not found")