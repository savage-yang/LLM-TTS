#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小爱智能语音助手 - Web 服务端
全局单例 Robot，WebSocket 只做消息转发，与 main.py 行为一致
"""

import asyncio
import json
import logging
import os
import signal
import sys
import threading
import traceback
from pathlib import Path
from typing import Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from bailing.robot import create_robot
from bailing.recorder import WebSocketRecorder

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# 日志配置
# ============================================================
def setup_logging(config_path: str = "config/config.yaml") -> None:
    log_level = logging.INFO
    try:
        with open(os.path.join(BASE_DIR, config_path), 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            level_str = config.get('logging', {}).get('level', 'INFO').upper()
            level_map = {
                'DEBUG': logging.DEBUG, 'INFO': logging.INFO,
                'WARNING': logging.WARNING, 'ERROR': logging.ERROR,
            }
            log_level = level_map.get(level_str, logging.INFO)
    except Exception:
        pass

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    os.makedirs("tmp", exist_ok=True)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('tmp/web_server.log', encoding='utf-8'),
        ],
        force=True,
    )
    for name in [
        "torch", "transformers", "funasr", "silero_vad",
        "pyaudio", "pygame", "urllib3", "requests", "httpx",
        "httpcore", "websocket", "websockets", "dashscope",
        "pydub", "sounddevice", "uvicorn", "uvicorn.access",
        "uvicorn.error", "fastapi", "av",
    ]:
        logging.getLogger(name).setLevel(logging.WARNING)


logger = logging.getLogger("web_server")


# ============================================================
# FastAPI
# ============================================================
app = FastAPI(title="百聆语音助手 Web")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

assets_dir = os.path.join(BASE_DIR, "assets")
if os.path.isdir(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

_config_path = os.path.join(BASE_DIR, "config", "config.yaml")

# 全局单例 Robot
_robot: Optional = None
_robot_lock = threading.Lock()
_current_ws: Optional[WebSocket] = None
_current_ws_lock = threading.Lock()
_duplex_thread: Optional[threading.Thread] = None


def _get_or_create_robot(loop=None):
    """获取或创建全局单例 Robot，与 main.py 一致只创建一次"""
    global _robot, _duplex_thread
    with _robot_lock:
        if _robot is not None:
            return _robot

        logger.info("首次连接，创建全局 Robot 实例...")
        _robot = create_robot(_config_path, websocket=None, loop=loop)
        _robot.recorder = WebSocketRecorder({})

        from bailing.player import WebSocketStreamPlayer
        from bailing.utils import read_config
        config_dict = read_config(_config_path)
        tts_module = config_dict["selected_module"]["TTS"]
        tts_cfg = config_dict["TTS"].get(tts_module, {})
        ws_player = WebSocketStreamPlayer(tts_cfg)
        _robot.stream_player = ws_player
        _robot.player = ws_player
        if _robot.current_tts_stream:
            _robot.current_tts_stream.stream_player = ws_player
            _robot.current_tts_stream.callback.player = ws_player

        async def _event_callback(event: dict):
            with _current_ws_lock:
                ws = _current_ws
            if ws is None:
                return
            try:
                await ws.send_json(event)
            except Exception:
                pass

        _robot.event_callback = _event_callback
        _robot._event_loop = loop
        _robot.listening_manager.event_callback = _event_callback
        _robot.listening_manager._event_loop = loop

        def _dialogue_callback(msg: dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not content:
                return
            is_final = (role == "assistant")
            with _current_ws_lock:
                ws = _current_ws
            if ws is None:
                return
            try:
                asyncio.run_coroutine_threadsafe(
                    ws.send_json({
                        "type": "message",
                        "role": role,
                        "content": content,
                        "is_final": is_final,
                    }),
                    _robot._event_loop
                )
            except Exception:
                pass

        _robot.callback = _dialogue_callback

        _robot.start_recording_and_vad()
        logger.info("全局 Robot 已启动，等待语音指令...")

        def run_duplex():
            try:
                while not _robot.stop_event.is_set():
                    _robot._duplex()
            except Exception as e:
                if not _robot.stop_event.is_set():
                    logger.error(f"_duplex 异常: {e}")

        _duplex_thread = threading.Thread(target=run_duplex, daemon=True)
        _duplex_thread.start()

        return _robot


# ============================================================
# 总结文件解析
# ============================================================
def _parse_summary_files(summary_dir: str) -> list[dict]:
    summaries = []
    if not os.path.isdir(summary_dir):
        return summaries
    for fname in sorted(os.listdir(summary_dir)):
        if not (fname.startswith("summary-") and fname.endswith(".txt")):
            continue
        filepath = os.path.join(summary_dir, fname)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            blocks = content.split("=" * 50)
            for block in blocks:
                block = block.strip()
                if not block:
                    continue
                lines = block.split("\n")
                ts = ""
                text_lines = []
                for line in lines:
                    if line.startswith("总结时间: "):
                        ts = line.replace("总结时间: ", "").strip()
                    elif not line.startswith("原始内容字数"):
                        text_lines.append(line)
                text = "\n".join(text_lines).strip()
                if text:
                    summaries.append({"content": text, "timestamp": ts})
        except Exception as e:
            logger.warning(f"读取总结文件失败 {fname}: {e}")
    return summaries


# ============================================================
# REST API 端点
# ============================================================
@app.get("/api/listening-summaries")
def get_listening_summaries():
    try:
        with open(_config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        listening_cfg = config.get("ListeningMode", {})
        summary_interval = listening_cfg.get("summary_interval", 60)
        summary_dir = listening_cfg.get("summary_save_path", "./tmp/listening_summaries")
    except Exception:
        summary_interval = 60
        summary_dir = "./tmp/listening_summaries"

    summary_dir = os.path.join(BASE_DIR, summary_dir)
    summaries = _parse_summary_files(summary_dir)

    return {"summaries": summaries, "summary_interval": summary_interval}


@app.get("/api/prologue")
def get_prologue():
    prologue_path = os.path.join(BASE_DIR, "voice_cache", "prologue.wav")
    if os.path.exists(prologue_path):
        return FileResponse(prologue_path, media_type="audio/wav")
    return {"error": "not found"}


# ============================================================
# WebSocket 端点
# ============================================================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    loop = asyncio.get_event_loop()
    client_id = id(ws) % 10000
    logger.info(f"🔗 [#{client_id}] 客户端已连接")

    robot = _get_or_create_robot(loop)

    # 新连接时重置对话历史为仅保留 system prompt（与 main.py 每次启动行为一致）
    robot.dialogue.reset_for_new_session()

    # 绑定当前 WebSocket（事件回调会发到这里）
    with _current_ws_lock:
        global _current_ws
        prev_ws = _current_ws
        _current_ws = ws

    # 更新 event_loop 和播放器发送函数
    robot._event_loop = loop

    def _ws_send_json(data: dict):
        asyncio.run_coroutine_threadsafe(ws.send_json(data), loop)

    if hasattr(robot.stream_player, 'set_send_fn'):
        robot.stream_player.set_send_fn(_ws_send_json, loop)
    if robot.current_tts_stream and robot.current_tts_stream.callback.player:
        if hasattr(robot.current_tts_stream.callback.player, 'set_send_fn'):
            robot.current_tts_stream.callback.player.set_send_fn(_ws_send_json, loop)

    # 发送当前状态
    try:
        await ws.send_json({
            "type": "status",
            "mode": robot.listening_manager.mode,
            "word_count": robot.listening_manager.total_word_count,
            "wake_word": "小爱",
            "tts_enabled": True,
            "modules_loaded": True,
            "summary_interval": robot.listening_manager.summary_interval,
            "dialogue_idle_timeout": robot.listening_manager.dialogue_idle_timeout,
        })
    except Exception:
        pass

    try:
        while True:
            try:
                msg = await ws.receive()

                if msg["type"] == "websocket.receive":
                    if "bytes" in msg:
                        robot.recorder.put_audio(msg["bytes"])
                    elif "text" in msg:
                        data = json.loads(msg["text"])
                        msg_type = data.get("type", "")

                        if msg_type == "connect":
                            continue

                        if msg_type == "switch_mode":
                            target = data.get("mode", "")
                            if target == "listening":
                                robot.listening_manager.switch_to_listening()
                            elif target == "dialogue":
                                robot.listening_manager.switch_to_dialogue()
                            await ws.send_json({"type": "mode_change", "mode": target, "reason": "manual"})
                            continue

                        if msg_type == "message":
                            content = data.get("content", "").strip()
                            if content:
                                threading.Thread(target=robot._submit_chat, args=(content, False), daemon=True).start()

                        if msg_type == "interrupt":
                            robot.interrupt_playback()

                elif msg["type"] == "websocket.disconnect":
                    break

            except WebSocketDisconnect:
                break
            except RuntimeError:
                break
            except Exception as e:
                logger.error(f"[#{client_id}] 接收异常: {e}")
                break

    except Exception as e:
        logger.error(f"[#{client_id}] 异常: {e}\n{traceback.format_exc()}")
    finally:
        # 断开时不销毁 Robot，保持全局单例
        with _current_ws_lock:
            if _current_ws is ws:
                _current_ws = None
        logger.info(f"🔌 [#{client_id}] 连接关闭（Robot 保持运行）")


# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    setup_logging()
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    logger.info("Starting XiaoAi Web Server on ws://0.0.0.0:8765")
    uvicorn.run(
        "web_server:app",
        host="0.0.0.0",
        port=8765,
        log_level="info",
        reload=False,
        ws_ping_interval=30,
        ws_ping_timeout=10,
    )