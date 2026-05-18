import asyncio
import json
import logging
import sys
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent))

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bailing.llm import OpenAILLM, LocalLLM
from bailing.prompt import sys_prompt, listening_summary_prompt

logger = logging.getLogger("web_server")

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
    llm = OpenAILLM(llm_config.get("LocalLLM", {})) if llm_config.get("LocalLLM", {}).get("url") else LocalLLM(llm_config.get("LocalLLM", {}))
else:
    llm = OpenAILLM(llm_config.get("OpenAILLM", {}))

SYSTEM_PROMPT = sys_prompt

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
            self.wake_word, "小艾", "小暧", "晓爱", "筱爱", "肖爱", "笑爱", "孝爱"
        }

        self.listening_raw: list = []

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
                    logger.info(f"检测到唤醒词「{matched}」，切换到对话模式")
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
                    should_summarize = self._check_trigger_summary()
                    return None, False, "listening" if not should_summarize else "summarizing"
            else:
                self._last_dialogue_time = time.time()
                return text_stripped, False, "dialogue"

    def _check_trigger_summary(self) -> bool:
        if self._summarizing:
            return False
        now = time.time()
        if now - self._last_summary_time >= self.summary_interval:
            self._summarizing = True
            return True
        if self.word_count >= self.summary_word_threshold:
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
            if time.time() - self._last_dialogue_time >= self.dialogue_idle_timeout:
                self.mode = "listening"
                logger.info(f"对话模式空闲超过{self.dialogue_idle_timeout}秒，自动切回监听模式")
                return True
            return False

    def switch_to_listening(self):
        with self._lock:
            self.mode = "listening"
            logger.info("切换到监听模式")

    def switch_to_dialogue(self):
        with self._lock:
            self.mode = "dialogue"
            self._last_dialogue_time = time.time()
            logger.info("切换到对话模式")

    def get_status(self) -> dict:
        with self._lock:
            return {
                "mode": self.mode,
                "word_count": self.word_count,
                "wake_word": self.wake_word,
            }


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


# ============================================================
# WebSocket 端点
# ============================================================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket client connected")

    session = SessionState()

    idle_task = asyncio.create_task(idle_checker(ws, session))

    try:
        await ws.send_json({
            "type": "status",
            "mode": "listening",
            "wake_word": session.wake_word,
            "word_count": 0,
        })

        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            msg_type = msg.get("type", "")

            if msg_type == "connect":
                status = session.get_status()
                await ws.send_json({"type": "connected", "status": "ok", **status})
                continue

            if msg_type == "switch_mode":
                target = msg.get("mode", "")
                if target == "listening":
                    session.switch_to_listening()
                    await ws.send_json({"type": "mode_change", "mode": "listening", "reason": "manual"})
                elif target == "dialogue":
                    session.switch_to_dialogue()
                    await ws.send_json({"type": "mode_change", "mode": "dialogue", "reason": "manual"})
                continue

            if msg_type == "message":
                user_content = msg.get("content", "").strip()
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

                user_msg = processed_text
                session.dialogue.append({"role": "user", "content": user_msg})

                await ws.send_json({
                    "type": "message",
                    "role": "user",
                    "content": user_msg,
                    "is_final": True,
                })

                full_response = ""
                try:
                    for chunk in llm.response(session.dialogue):
                        if chunk:
                            full_response += chunk
                            await ws.send_json({
                                "type": "message",
                                "role": "assistant",
                                "content": chunk,
                                "is_final": False,
                                "emotion": "speaking",
                            })
                            await asyncio.sleep(0.01)

                    full_response = full_response.strip()

                    if not full_response:
                        full_response = "抱歉，我没有理解你的意思，能再说一遍吗？"

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

                    session.dialogue.append({"role": "assistant", "content": cleaned})

                    if need_switch:
                        session.switch_to_listening()
                        await ws.send_json({
                            "type": "mode_change",
                            "mode": "listening",
                            "reason": "llm_switch",
                        })

                    if need_push:
                        logger.info(f"检测到推送标记，已过滤")

                except Exception as e:
                    logger.error(f"LLM error: {e}")
                    await ws.send_json({
                        "type": "message",
                        "role": "assistant",
                        "content": f"抱歉，我遇到了一个错误：{str(e)}",
                        "is_final": True,
                        "emotion": "idle",
                    })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        idle_task.cancel()
        try:
            await idle_task
        except asyncio.CancelledError:
            pass
        try:
            await ws.close()
        except Exception:
            pass


async def generate_summary_and_send(ws: WebSocket, raw_text: str, session: SessionState):
    await ws.send_json({
        "type": "summary_start",
        "word_count": session.word_count,
    })
    try:
        loop = asyncio.get_event_loop()

        def do_summary_sync():
            try:
                llm_response = llm.response([
                    {"role": "system", "content": listening_summary_prompt},
                    {"role": "user", "content": f"请总结以下内容：\n{raw_text}"}
                ])
                return "".join(llm_response)
            except Exception as e:
                logger.error(f"总结失败: {e}")
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
    except Exception as e:
        logger.error(f"总结生成失败: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
    logger.info("Starting XiaoAi Web Server on ws://localhost:8765")
    uvicorn.run(app, host="0.0.0.0", port=8765, ws_ping_interval=30, ws_ping_timeout=10)