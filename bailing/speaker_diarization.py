import os
import wave
import logging
import tempfile
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


class SpeakerDiarizer(ABC):
    @abstractmethod
    def identify(self, audio_data: List[bytes]) -> Optional[str]:
        pass

    @abstractmethod
    def diarize(self, audio_data: List[bytes]) -> List[Dict[str, Any]]:
        pass


class FunASRSpeakerDiarizer(SpeakerDiarizer):
    def __init__(self, config: Dict[str, Any]):
        self.model_dir = config.get("model_dir", "iic/speech_eres2net_speaker_verification_16k")
        self.similarity_threshold = config.get("similarity_threshold", 0.65)
        self.max_speakers = config.get("max_speakers", 6)
        self._speaker_embeddings: List[np.ndarray] = []
        self._speaker_labels: List[str] = []
        self._speaker_counter = 0
        self._registered_speakers: Dict[str, np.ndarray] = {}

        from funasr import AutoModel
        self.model = AutoModel(
            model=self.model_dir,
            disable_update=True,
            hub="hf"
        )
        logger.info(f"[启动] 说话人分离模型加载完成: {self.model_dir}")

    def register_speaker(self, name: str, audio_data: List[bytes]) -> bool:
        try:
            embedding = self._extract_embedding(audio_data)
            if embedding is None:
                logger.error(f"注册说话人 {name} 失败：无法提取声纹")
                return False
            self._registered_speakers[name] = embedding
            if name not in self._speaker_labels:
                self._speaker_embeddings.append(embedding)
                self._speaker_labels.append(name)
            else:
                idx = self._speaker_labels.index(name)
                self._speaker_embeddings[idx] = embedding
            logger.info(f"已注册说话人: {name}")
            return True
        except Exception as e:
            logger.error(f"注册说话人 {name} 出错: {e}")
            return False

    def identify(self, audio_data: List[bytes]) -> Optional[str]:
        try:
            embedding = self._extract_embedding(audio_data)
            if embedding is None:
                return None

            if self._registered_speakers:
                best_name = None
                best_score = -1.0
                for name, reg_emb in self._registered_speakers.items():
                    score = self._cosine_similarity(embedding, reg_emb)
                    if score > best_score:
                        best_score = score
                        best_name = name
                if best_score >= self.similarity_threshold:
                    return best_name

            if self._speaker_embeddings:
                best_idx = -1
                best_score = -1.0
                for i, stored_emb in enumerate(self._speaker_embeddings):
                    score = self._cosine_similarity(embedding, stored_emb)
                    if score > best_score:
                        best_score = score
                        best_idx = i
                if best_score >= self.similarity_threshold:
                    return self._speaker_labels[best_idx]

            if len(self._speaker_labels) < self.max_speakers:
                self._speaker_counter += 1
                label = f"说话人{self._speaker_counter}"
            else:
                label = f"说话人{self._speaker_counter}"
            self._speaker_embeddings.append(embedding)
            self._speaker_labels.append(label)
            logger.info(f"新说话人: {label}")
            return label

        except Exception as e:
            logger.error(f"说话人识别出错: {e}")
            return None

    def diarize(self, audio_data: List[bytes]) -> List[Dict[str, Any]]:
        return [{"speaker": self.identify(audio_data), "start": 0.0, "end": 0.0}]

    def reset(self):
        self._speaker_embeddings = []
        self._speaker_labels = []
        self._speaker_counter = 0
        registered = dict(self._registered_speakers)
        self._registered_speakers = {}
        for name, emb in registered.items():
            self._speaker_embeddings.append(emb)
            self._speaker_labels.append(name)

    def _extract_embedding(self, audio_data: List[bytes]) -> Optional[np.ndarray]:
        tmpfile = None
        try:
            tmpfile = os.path.join(
                tempfile.gettempdir(),
                f"spk_{os.getpid()}_{id(audio_data)}.wav"
            )
            with wave.open(tmpfile, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b''.join(audio_data))

            res = self.model.generate(input=tmpfile, batch_size_s=60)
            if res and len(res) > 0:
                embedding = res[0].get("spk_embedding")
                if embedding is not None:
                    return np.array(embedding).flatten()
            return None
        except Exception as e:
            logger.error(f"提取声纹嵌入出错: {e}")
            return None
        finally:
            if tmpfile and os.path.exists(tmpfile):
                try:
                    os.remove(tmpfile)
                except Exception:
                    pass

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))


class NoOpSpeakerDiarizer(SpeakerDiarizer):
    def identify(self, audio_data: List[bytes]) -> Optional[str]:
        return None

    def diarize(self, audio_data: List[bytes]) -> List[Dict[str, Any]]:
        return []


def create_instance(class_name: str, *args, **kwargs):
    cls = globals().get(class_name)
    if cls:
        return cls(*args, **kwargs)
    else:
        raise ValueError(f"Class {class_name} not found")
