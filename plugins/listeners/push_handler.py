import logging
import os
import sys

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.registry import register_listener

logger = logging.getLogger(__name__)


@register_listener("PUSH")
def handle_push(content: str):
    """
    处理 <|PUSH|> 标记：推送通知到手机
    """
    if not content.strip():
        return
    try:
        from bailing.robot import Robot
        robot = Robot._instance
        if robot and robot.bark_notifier:
            robot.bark_notifier.send_formatted(content.strip())
            logger.info(f"[监听处理器] 已推送: {content}")
        else:
            logger.warning("[监听处理器] Bark推送器不可用")
    except Exception as e:
        logger.debug(f"[监听处理器] 推送失败: {e}")