#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小爱智能语音助手 - Web 服务端
支持 ASR + VAD + LLM + TTS 全链路
"""

import asyncio
import json
import logging
import sys
import time
import threading
import struct
import wave
import io
import base64
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

sys.path.insert(0, str(Path(__file__).parent))

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bailing.llm import OpenAILLM, LocalLLM
from bailing.prompt import sys_prompt, listening_summary_prompt
from bailing.tts import QwenTtsRealtimeStream, filter_special_tokens

# ============================================================
# 日志全局配置（与 main.py 一致）
# ============================================================
def setup_logging(config_path: str = "config/config.yaml") -> None:
    log_level = logging.INFO
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            level_str = config.get('logging', {}).get('level', 'INFO').upper()
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR
            }
            log_level = level_map.get(level_str, logging.INFO)
    except Exception as e:
        print(f"读取日志配置失败，使用默认INFO级别: {e}")

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    os.makedirs("tmp", exist_ok=True)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('tmp/web_server.log', encoding='utf-8'),
        ],
        force=True
    )

    third_party_loggers = [
        "torch", "transformers", "funasr", "silero_vad",
        "pyaudio", "pygame", "urllib3", "requests", "httpx",
        "httpcore", "websocket", "websockets", "dashscope",
        "pydub", "sounddevice", "uvicorn", "uvicorn.access",
        "uvicorn.error", "fastapi", "av"
    ]
    for logger_name in third_party_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


logger = logging.getLogger("web_server")
vad_logger = logging.getLogger("web_server.vad")
asr_logger = logging.getLogger("web_server.asr")
tts_logger = logging.getLogger("web_server.tts")
audio_logger = logging.getLogger("web_server.audio")

app = FastAPI(title="XiaoAi Web Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


config = load_config()
llm_config = config.get("LLM", {})
selected_llm = config.get("selected_module", {}).get("LLM", "OpenAILLM")

if selected_llm == "LocalLLM":
    llm = LocalLLM(llm_config.get("LocalLLM", {}))
else:
    llm = OpenAILLM(llm_config.get("OpenAILLM", {}))

SYSTEM_PROMPT = sys_prompt

logger.info("=" * 50)
logger.info("XiaoAi Web Server 初始化中...")
logger.info(f"LLM 模块: {selected_llm}")
logger.info(f"唤醒词: {config.get('WakeWord', '小爱')}")
logger.info("=" * 50)


# ============================================================
# Web TTS Collector - 收集 Qwen TTS 流式 PCM 数据
# ============================================================
class WebTtsCollector:
    def __init__(self):
        self.pcm_data = bytearray()

    def feed_audio(self, audio_data: bytes) -> None:
        self.pcm_data.extend(audio_data)

    def get_pcm(self) -> bytes:
        return bytes(self.pcm_data)

    def clear(self) -> None:
        self.pcm_data = bytearray()

    @staticmethod
    def pcm_to_wav_base64(pcm_data: bytes, sample_rate=24000, channels=1, sample_width=2) -> str:
        if not pcm_data:
            return ""
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        buf.seek(0)
        wav_bytes = buf.read()
        return base64.b64encode(wav_bytes).decode('ascii')


# ============================================================
# 音频缓冲区 + WebM 解码器
# ============================================================
class AudioBuffer:
    def __init__(self):
        self.chunks: List[bytes] = []
        self._lock = threading.Lock()

    def append(self, data: bytes):
        with self._lock:
            self.chunks.append(data)

    def get_and_clear(self) -> List[bytes]:
        with self._lock:
            chunks = self.chunks[:]
            self.chunks = []
            return chunks

    @property
    def size(self) -> int:
        return sum(len(c) for c in self.chunks)


def decode_webm_to_pcm(webm_bytes: bytes) -> Optional[bytes]:
    """将前端发来的 WebM/Opus 音频解码为 16kHz 16bit mono PCM"""
    try:
        import av
        container = av.open(io.BytesIO(webm_bytes), 'r')
        pcm_chunks = []
        resampler = None

        for frame in container.decode(audio=0):
            if frame.format.name != 's16':
                if resampler is None:
                    layout = frame.layout
                    resampler = av.AudioResampler(
                        format='s16',
                        layout='mono',
                        rate=16000,
                    )
                frames = resampler.resample(frame)
                for f in frames:
                    pcm_chunks.append(f.to_ndarray().tobytes())
            else:
                if frame.rate != 16000 or frame.layout != 'mono':
                    if resampler is None:
                        resampler = av.AudioResampler(
                            format='s16',
                            layout='mono',
                            rate=16000,
                        )
                    frames = resampler.resample(frame)
                    for f in frames:
                        pcm_chunks.append(f.to_ndarray().tobytes())
                else:
                    pcm_chunks.append(frame.to_ndarray().tobytes())

        container.close()
        result = b''.join(pcm_chunks) if pcm_chunks else None
        audio_logger.debug(f"WebM 解码完成: 输入 {len(webm_bytes)} 字节 → PCM {len(result) if result else 0} 字节")
        return result
    except ImportError:
        audio_logger.warning("PyAV 未安装，尝试使用 ffmpeg 命令行解码")
        return decode_webm_to_pcm_ffmpeg(webm_bytes)
    except Exception as e:
        audio_logger.error(f"WebM 解码失败: {e}")
        return None


def decode_webm_to_pcm_ffmpeg(webm_bytes: bytes) -> Optional[bytes]:
    try:
        import subprocess
        tmp_input = os.path.join("tmp", f"webm_{threading.current_thread().ident}.webm")
        tmp_output = os.path.join("tmp", f"pcm_{threading.current_thread().ident}.raw")
        os.makedirs("tmp", exist_ok=True)

        with open(tmp_input, 'wb') as f:
            f.write(webm_bytes)

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_input, "-f", "s16le",
             "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", tmp_output],
            capture_output=True, timeout=10
        )

        try:
            os.unlink(tmp_input)
        except:
            pass

        if result.returncode == 0 and os.path.exists(tmp_output):
            with open(tmp_output, 'rb') as f:
                pcm = f.read()
            try:
                os.unlink(tmp_output)
            except:
                pass
            audio_logger.debug(f"FFmpeg 解码完成: {len(pcm)} 字节")
            return pcm
        return None
    except Exception as e:
        audio_logger.error(f"FFmpeg 解码失败: {e}")
        return None


# ============================================================
# 会话状态管理
# ============================================================
class SessionState:
    def __init__(self):
        self.mode: str = "listening"
        self.dialogue: list = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.word_count: int = 0
        self._last_summary_time: float = time.time()
        self._last_dialogue_time: float = time.time()
        self._summarizing: bool = False
        self._lock = threading.Lock()

        listening_config = config.get("ListeningMode", {})
        self.summary_interval: int = listening_config.get("summary_interval", 60)
        self.summary_word_threshold: int = listening_config.get("summary_word_threshold", 300)
        self.dialogue_idle_timeout: int = listening_config.get("dialogue_idle_timeout", 150)
        self.wake_word: str = config.get("WakeWord", "小爱")
        self.wake_word_variants = {
            self.wake_word, "小艾", "小暧", "晓爱", "筱爱",
            "肖爱", "笑爱", "孝爱"
        }

        self.listening_raw: list = []
        self.tts_collector: Optional[WebTtsCollector] = None
        self.tts_stream: Optional[QwenTtsRealtimeStream] = None
        self.tts_enabled: bool = True
        self.audio_buffer = AudioBuffer()

        # VAD + ASR 模块（懒加载）
        self.vad_instance = None
        self.asr_instance = None
        self._modules_loaded = False

        # VAD 语音片段收集
        self.speech_segments: List[bytes] = []
        self.is_speaking = False

        logger.info(f"会话初始化完成 | 模式={self.mode} | 唤醒词={self.wake_word} "
                     f"| 对话超时={self.dialogue_idle_timeout}s | 总结间隔={self.summary_interval}s")

    def _load_modules(self):
        """懒加载 VAD 和 ASR 模块"""
        if self._modules_loaded:
            return
        try:
            vad_config = config.get("VAD", {}).get("SileroVAD", {})
            from bailing.vad import create_instance as create_vad
            self.vad_instance = create_vad("SileroVAD", vad_config)
            vad_logger.info(f"VAD 模块加载成功 | threshold={vad_config.get('threshold', 0.65)}")

            asr_config = config.get("ASR", {}).get("FunASR", {})
            from bailing.asr import create_instance as create_asr
            self.asr_instance = create_asr("FunASR", asr_config)
            asr_logger.info(f"ASR 模块加载成功 | model_dir={asr_config.get('model_dir', '')}")

            self._modules_loaded = True
            logger.info("VAD + ASR 模块全部就绪")
        except Exception as e:
            logger.error(f"VAD/ASR 模块加载失败: {e}", exc_info=True)

    def _match_wake_word(self, text: str) -> Optional[str]:
        for variant in self.wake_word_variants:
            if variant in text:
                return variant
        return None

    def process_input(self, text: str) -> tuple[Optional[str], bool, str]:
        with self._lock:
            text_stripped = text.strip()
            if self.mode == "listening":
                matched = self._match_wake_word(text_stripped)
                if matched:
                    self.mode = "dialogue"
                    self._last_dialogue_time = time.time()
                    logger.info(f"🎯 检测到唤醒词「{matched}」→ 切换到对话模式 | 文本: \"{text_stripped}\"")
                    cleaned = text_stripped.replace(matched, "").strip()
                    if cleaned:
                        return cleaned, True, "dialogue"
                    return None, True, "dialogue"
                else:
                    self.listening_raw.append({
                        "text": text_stripped,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    self.word_count += len(text_stripped)
                    logger.debug(f"👂 监听记录: \"{text_stripped[:30]}...\" ({len(text_stripped)}字, 累计{self.word_count}字)")
                    should_summarize = self._check_trigger_summary()
                    return None, False, "listening" if not should_summarize else "summarizing"
            else:
                self._last_dialogue_time = time.time()
                logger.info(f"💬 用户输入: \"{text_stripped[:40]}{'...' if len(text_stripped)>40 else ''}\"")
                return text_stripped, False, "dialogue"

    def _check_trigger_summary(self) -> bool:
        if self._summarizing:
            return False
        now = time.time()
        if now - self._last_summary_time >= self.summary_interval:
            logger.info(f"⏱️ 触发定时总结（间隔 {self.summary_interval}s，累计 {self.word_count} 字）")
            self._summarizing = True
            return True
        if self.word_count >= self.summary_word_threshold:
            logger.info(f"📝 触发字数总结（阈值 {self.summary_word_threshold} 字，当前 {self.word_count} 字）")
            self._summarizing = True
            return True
        return False

    def get_and_reset_listening_raw(self) -> str:
        with self._lock:
            if not self.listening_raw:
                return ""
            raw_text = "\n".join(f"[{item['timestamp']}] {item['text']}" for item in self.listening_raw)
            self.listening_raw = []
            self.word_count = 0
            self._last_summary_time = time.time()
            self._summarizing = False
            return raw_text

    def check_dialogue_idle(self) -> bool:
        with self._lock:
            if self.mode != "dialogue":
                return False
            idle_seconds = int(time.time() - self._last_dialogue_time)
            if idle_seconds >= self.dialogue_idle_timeout:
                self.mode = "listening"
                logger.info(f"💤 对话模式空闲 {idle_seconds}s > {self.dialogue_idle_timeout}s 阈值，自动切回监听模式")
                return True
            return False

    def switch_to_listening(self):
        with self._lock:
            old_mode = self.mode
            self.mode = "listening"
            if old_mode != "listening":
                logger.info("↩️ 手动切换回监听模式")

    def switch_to_dialogue(self):
        with self._lock:
            old_mode = self.mode
            self.mode = "dialogue"
            self._last_dialogue_time = time.time()
            if old_mode != "dialogue":
                logger.info("➡️ 手动切换到对话模式")

    def get_status(self) -> dict:
        with self._lock:
            return {
                "mode": self.mode,
                "word_count": self.word_count,
                "wake_word": self.wake_word,
                "tts_enabled": self.tts_enabled,
                "modules_loaded": self._modules_loaded,
            }

    def init_tts(self):
        try:
            tts_config = config.get("TTS", {}).get("QwenTtsRealtimeAPI", {})
            if not tts_config.get("api_key"):
                logger.warning("未配置 TTS API Key，禁用语音播报")
                self.tts_enabled = False
                return
            self.tts_collector = WebTtsCollector()
            self.tts_stream = QwenTtsRealtimeStream(tts_config, self.tts_collector)
            self.tts_stream.connect()
            tts_logger.info(f"TTS 模块初始化成功 | model={tts_config.get('model', 'Cherry')}")
        except Exception as e:
            logger.error(f"TTS 初始化失败: {e}")
            self.tts_enabled = False

    async def generate_tts_and_send(self, ws: WebSocket, text: str):
        if not self.tts_enabled or not self.tts_stream or not self.tts_collector:
            return
        filtered_text = filter_special_tokens(text)
        if not filtered_text.strip():
            tts_logger.debug("TTS 跳过：过滤后文本为空")
            return
        try:
            tts_logger.info(f"🔊 TTS 开始合成 | 文本长度: {len(filtered_text)} 字符")
            await ws.send_json({"type": "tts_start"})
            self.tts_collector.clear()
            loop = asyncio.get_event_loop()

            def do_tts():
                try:
                    self.tts_stream.connect()
                    self.tts_stream.append_text(filtered_text)
                    self.tts_stream.finish(timeout=30)
                except Exception as e:
                    tts_logger.error(f"TTS 合成异常: {e}")

            await loop.run_in_executor(None, do_tts)

            pcm_data = self.tts_collector.get_pcm()
            tts_logger.info(f"TTS 合成完成 | PCM 大小: {len(pcm_data) if pcm_data else 0} 字节")

            if pcm_data:
                wav_b64 = WebTtsCollector.pcm_to_wav_base64(pcm_data)
                if wav_b64:
                    chunk_size = 8000
                    total_chunks = (len(wav_b64) + chunk_size - 1) // chunk_size
                    tts_logger.info(f"TTS WAV 发送中 | Base64 大小: {len(wav_b64)} 字节, 分 {total_chunks} 个包")
                    for i in range(0, len(wav_b64), chunk_size):
                        await ws.send_json({
                            "type": "tts_audio_chunk",
                            "chunk_id": i // chunk_size,
                            "total_chunks": total_chunks,
                            "data": wav_b64[i:i + chunk_size],
                            "is_last": i + chunk_size >= len(wav_b64),
                        })
                        await asyncio.sleep(0.005)
            tts_logger.info("TTS 全部发送完毕")
            await ws.send_json({"type": "tts_end"})
        except Exception as e:
            tts_logger.error(f"TTS 发送失败: {e}")
            try:
                await ws.send_json({"type": "tts_error", "error": str(e)})
            except:
                pass

    async def process_audio(self, ws: WebSocket):
        """
        完整音频处理链路：
        收集 WebM 音频 → 解码为 PCM → VAD 检测说话段 → ASR 识别文字
        """
        self._load_modules()
        if not self.vad_instance or not self.asr_instance:
            return

        chunks = self.audio_buffer.get_and_clear()
        if not chunks:
            return

        webm_data = b''.join(chunks)
        total_size = len(webm_data)
        if total_size < 1000:
            audio_logger.debug(f"音频数据过小({total_size}B)，跳过处理")
            return

        audio_logger.info(f"🎙️ 开始处理音频 | WebM 大小: {total_size / 1024:.1f}KB, 包数: {len(chunks)}")
        start_time = time.time()

        loop = asyncio.get_event_loop()

        def decode_and_process():
            try:
                pcm_data = decode_webm_to_pcm(webm_data)
                if not pcm_data or len(pcm_data) < 100:
                    audio_logger.debug("PCM 解码结果为空或过小")
                    return []

                audio_logger.info(f"解码完成 | PCM: {len(pcm_data) / 1024:.1f}KB | 时长: ~{len(pcm_data)/32000:.2f}s")

                FRAME_SIZE_MS = 30
                SAMPLE_RATE = 16000
                BYTES_PER_SAMPLE = 2
                frame_size = int(SAMPLE_RATE * FRAME_SIZE_MS / 1000 * BYTES_PER_SAMPLE)

                results = []
                offset = 0
                frame_count = 0
                speech_frame_count = 0

                while offset < len(pcm_data):
                    chunk = pcm_data[offset:offset + frame_size]
                    offset += frame_size
                    frame_count += 1
                    if len(chunk) < frame_size:
                        chunk = chunk.ljust(frame_size, b'\x00')

                    vad_result = self.vad_instance.is_vad(chunk)

                    if vad_result is not None:
                        if not self.is_speaking:
                            self.is_speaking = True
                            vad_logger.info("🔴 VAD: 开始检测到语音")
                        self.speech_segments.append(chunk)
                        speech_frame_count += 1
                    else:
                        if self.is_speaking:
                            self.is_speaking = False
                            vad_logger.info(f"⚪ VAD: 语音结束 ({speech_frame_count} 帧, ~{speech_frame_count * 30 / 1000:.1f}s)")
                            if self.speech_segments:
                                full_speech = b''.join(self.speech_segments)
                                self.speech_segments = []
                                results.append(full_speech)

                audio_logger.info(f"VAD 处理完成 | 总帧数: {frame_count} | 识别出 {len(results)} 个语音段")
                return results

            except Exception as e:
                audio_logger.error(f"音频处理出错: {e}", exc_info=True)
                return []

        speech_segments = await loop.run_in_executor(None, decode_and_process)

        elapsed = time.time() - start_time
        audio_logger.info(f"音频总处理耗时: {elapsed:.2f}s | 识别出 {len(speech_segments)} 段语音")

        for idx, speech_pcm in enumerate(speech_segments):
            if len(speech_pcm) < 200:
                continue

            asr_logger.info(f"--- ASR 第 {idx+1}/{len(speech_segments)} 段 | PCM: {len(speech_pcm)} 字节 ---")

            def do_asr(pcm):
                t0 = time.time()
                try:
                    text, _ = self.asr_instance.recognizer([pcm])
                    dt = time.time() - t0
                    asr_logger.info(f"✅ ASR 结果: \"{text}\" | 耗时: {dt:.2f}s")
                    return text
                except Exception as e:
                    asr_logger.error(f"❌ ASR 识别出错: {e}", exc_info=True)
                    return ""

            text = await loop.run_in_executor(None, lambda p=speech_pcm: do_asr(p))

            if text and text.strip():
                processed_text, is_wake, mode_after = self.process_input(text.strip())

                if mode_after == "listening":
                    await ws.send_json({
                        "type": "listening_recorded",
                        "text": text.strip(),
                        "word_count": self.word_count,
                    })
                elif mode_after == "summarizing":
                    await ws.send_json({
                        "type": "listening_recorded",
                        "text": text.strip(),
                        "word_count": self.word_count,
                        "summarizing": True,
                    })
                    raw_text = self.get_and_reset_listening_raw()
                    if raw_text:
                        asyncio.create_task(generate_summary_and_send(ws, raw_text, self))
                elif is_wake:
                    await ws.send_json({
                        "type": "mode_change",
                        "mode": "dialogue",
                        "reason": "wake_word",
                    })
                    if processed_text and processed_text.strip():
                        await self.run_dialogue(ws, processed_text.strip())
                elif processed_text and processed_text.strip():
                    await self.run_dialogue(ws, processed_text.strip())

    async def run_dialogue(self, ws: WebSocket, user_msg: str):
        """执行完整对话流程：用户消息 → LLM → TTS"""
        self.dialogue.append({"role": "user", "content": user_msg})

        await ws.send_json({
            "type": "message",
            "role": "user",
            "content": user_msg,
            "is_final": True,
        })

        full_response = ""
        llm_start = time.time()
        logger.info(f"🤖 LLM 开始生成回复...")

        try:
            chunk_idx = 0
            for chunk in llm.response(self.dialogue):
                if chunk:
                    full_response += chunk
                    chunk_idx += 1
                    await ws.send_json({
                        "type": "message",
                        "role": "assistant",
                        "content": chunk,
                        "is_final": False,
                        "emotion": "speaking",
                    })
                    await asyncio.sleep(0.01)

            elapsed = time.time() - llm_start
            full_response = full_response.strip()

            if not full_response:
                full_response = "抱歉，我没有理解你的意思，能再说一遍吗？"

            logger.info(f"🤖 LLM 回复完成 | 耗时: {elapsed:.2f}s | 字符数: {len(full_response)} | 分片: {chunk_idx}")

            need_exit = "<|EXIT_PROGRAM|>" in full_response
            need_switch = "<|SWITCH_LISTEN|>" in full_response
            need_push = "<|PUSH_NOTIFICATION|>" in full_response

            cleaned = full_response
            cleaned = cleaned.replace("<|EXIT_PROGRAM|>", "").strip()
            cleaned = cleaned.replace("<|SWITCH_LISTEN|>", "").strip()
            cleaned = cleaned.replace("<|PUSH_NOTIFICATION|>", "").strip()

            if not cleaned:
                cleaned = full_response

            await ws.send_json({
                "type": "message",
                "role": "assistant",
                "content": cleaned,
                "is_final": True,
                "emotion": "happy" if full_response else "idle",
            })

            self.dialogue.append({"role": "assistant", "content": cleaned})
            logger.info(f"💬 AI 回复已发送: \"{cleaned[:50]}{'...' if len(cleaned)>50 else ''}\"")

            if need_switch:
                self.switch_to_listening()
                await ws.send_json({
                    "type": "mode_change",
                    "mode": "listening",
                    "reason": "llm_switch",
                })

            if need_push:
                logger.info("检测到推送标记 <|PUSH_NOTIFICATION|>，已过滤")

            if cleaned and len(cleaned) > 2:
                await self.generate_tts_and_send(ws, cleaned)

        except Exception as e:
            logger.error(f"❌ LLM 处理异常: {e}", exc_info=True)
            await ws.send_json({
                "type": "message",
                "role": "assistant",
                "content": f"抱歉，我遇到了一个错误：{str(e)}",
                "is_final": True,
                "emotion": "idle",
            })


# ============================================================
# 后台空闲检测任务
# ============================================================
async def idle_checker(ws: WebSocket, session: SessionState):
    while True:
        try:
            await asyncio.sleep(5)
            if session.check_dialogue_idle():
                await ws.send_json({
                    "type": "mode_change",
                    "mode": "listening",
                    "reason": "idle_timeout"
                })
        except Exception:
            break


async def audio_processor(ws: WebSocket, session: SessionState):
    """后台定时器：定期处理音频缓冲区中的数据"""
    while True:
        try:
            await asyncio.sleep(4)
            buf_size = session.audio_buffer.size
            if buf_size > 2000:
                logger.debug(f"音频处理器触发 | 缓冲区大小: {buf_size / 1024:.1f}KB")
                await session.process_audio(ws)
        except Exception:
            break


# ============================================================
# WebSocket 端点
# ============================================================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    client_id = id(ws)
    await ws.accept()
    logger.info(f"🔗 [客户端 #{client_id % 10000}] WebSocket 连接已建立")

    session = SessionState()
    session.init_tts()

    idle_task = asyncio.create_task(idle_checker(ws, session))
    audio_process_task = asyncio.create_task(audio_processor(ws, session))

    try:
        status = session.get_status()
        await ws.send_json({
            "type": "status",
            **status,
        })

        while True:
            data = await ws.receive()

            # 处理二进制音频数据（WebM 格式）
            if isinstance(data, bytes):
                session.audio_buffer.append(data)
                continue

            # 处理文本 JSON 消息
            msg_type = data.get("type", "") if isinstance(data, dict) else ""

            if msg_type == "connect":
                status = session.get_status()
                await ws.send_json({"type": "connected", "status": "ok", **status})
                logger.debug(f"[#{client_id % 10000}] 收到 connect 握手")
                continue

            if msg_type == "switch_mode":
                target = data.get("mode", "")
                reason = "manual"
                if target == "listening":
                    session.switch_to_listening()
                elif target == "dialogue":
                    session.switch_to_dialogue()
                else:
                    continue
                await ws.send_json({"type": "mode_change", "mode": target, "reason": reason})
                logger.info(f"[#{client_id % 10000}] 模式切换: {target} ({reason})")
                continue

            if msg_type == "message":
                user_content = data.get("content", "").strip()
                if not user_content:
                    continue

                processed_text, is_wake, mode_after = session.process_input(user_content)

                if mode_after == "listening":
                    await ws.send_json({
                        "type": "listening_recorded",
                        "text": user_content,
                        "word_count": session.word_count,
                    })
                    continue

                if mode_after == "summarizing":
                    await ws.send_json({
                        "type": "listening_recorded",
                        "text": user_content,
                        "word_count": session.word_count,
                        "summarizing": True,
                    })
                    raw_text = session.get_and_reset_listening_raw()
                    if raw_text:
                        asyncio.create_task(generate_summary_and_send(ws, raw_text, session))
                    continue

                if is_wake:
                    await ws.send_json({
                        "type": "mode_change",
                        "mode": "dialogue",
                        "reason": "wake_word",
                    })

                if processed_text is None or not processed_text.strip():
                    continue

                await session.run_dialogue(ws, processed_text.strip())

    except WebSocketDisconnect:
        logger.info(f"🔌 [客户端 #{client_id % 10000}] WebSocket 断开连接")
    except Exception as e:
        logger.error(f"❌ [客户端 #{client_id % 10000}] WebSocket 异常: {e}", exc_info=True)
    finally:
        idle_task.cancel()
        audio_process_task.cancel()
        try:
            await idle_task
            await audio_process_task
        except (asyncio.CancelledError, StopAsyncIteration):
            pass
        if session.tts_stream:
            try:
                session.tts_stream.close()
            except:
                pass
        try:
            await ws.close()
        except Exception:
            pass


async def generate_summary_and_send(ws: WebSocket, raw_text: str, session: SessionState):
    logger.info(f"📋 开始生成监听总结 | 原始数据长度: {len(raw_text)} 字符")
    await ws.send_json({
        "type": "summary_start",
        "word_count": session.word_count,
    })
    try:
        loop = asyncio.get_event_loop()

        def do_summary_sync():
            t0 = time.time()
            try:
                llm_response = llm.response([
                    {"role": "system", "content": listening_summary_prompt},
                    {"role": "user", "content": f"请总结以下内容：\n{raw_text}"}
                ])
                result = "".join(llm_response)
                dt = time.time() - t0
                logger.info(f"📋 监听总结生成完成 | 耗时: {dt:.2f}s | 长度: {len(result)} 字符")
                return result
            except Exception as e:
                logger.error(f"监听总结生成失败: {e}", exc_info=True)
                return None

        summary = await loop.run_in_executor(None, do_summary_sync)

        if summary:
            cleaned = summary.strip()
            if "<|PUSH_NOTIFICATION|>" in cleaned:
                cleaned = cleaned.replace("<|PUSH_NOTIFICATION|>", "").strip()
            await ws.send_json({
                "type": "summary",
                "content": cleaned,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            logger.info(f"📋 监听总结已发送: \"{cleaned[:50]}{'...' if len(cleaned)>50 else ''}\"")
    except Exception as e:
        logger.error(f"监听总结发送失败: {e}", exc_info=True)


if __name__ == "__main__":
    setup_logging()
    logger.info("Starting XiaoAi Web Server on ws://localhost:8765 (ASR+VAD+LLM+TTS)")
    uvicorn.run(app, host="0.0.0.0", port=8765, ws_ping_interval=30, ws_ping_timeout=10)