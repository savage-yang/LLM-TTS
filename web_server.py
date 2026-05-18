import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bailing.llm import OpenAILLM, LocalLLM
from bailing.prompt import sys_prompt

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
    llm = LocalLLM(llm_config.get("LocalLLM", {}))
else:
    llm = OpenAILLM(llm_config.get("OpenAILLM", {}))

SYSTEM_PROMPT = sys_prompt


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket client connected")

    dialogue = [{"role": "system", "content": SYSTEM_PROMPT}]

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "connect":
                await ws.send_json({"type": "connected", "status": "ok"})
                continue

            if msg.get("type") == "message":
                user_content = msg.get("content", "").strip()
                if not user_content:
                    continue

                dialogue.append({"role": "user", "content": user_content})

                full_response = ""
                try:
                    for chunk in llm.response(dialogue):
                        if chunk:
                            full_response += chunk
                            await ws.send_json({
                                "type": "message",
                                "content": chunk,
                                "is_final": False,
                                "emotion": "speaking",
                            })
                            await asyncio.sleep(0.01)

                    await ws.send_json({
                        "type": "message",
                        "content": full_response if full_response else "抱歉，我没有理解你的意思，能再说一遍吗？",
                        "is_final": True,
                        "emotion": "happy" if full_response else "idle",
                    })
                    dialogue.append({"role": "assistant", "content": full_response})

                except Exception as e:
                    logger.error(f"LLM error: {e}")
                    await ws.send_json({
                        "type": "message",
                        "content": f"抱歉，我遇到了一个错误：{str(e)}",
                        "is_final": True,
                        "emotion": "idle",
                    })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        try:
            await ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
    logger.info("Starting XiaoAi Web Server on ws://localhost:8765")
    uvicorn.run(app, host="0.0.0.0", port=8765, ws_ping_interval=30, ws_ping_timeout=10)