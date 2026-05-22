import logging
import os
import sys
import yaml

# 确保项目根目录在 sys.path 中，支持直接 python xxx.py 运行
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.registry import register_function, ToolType
from plugins.registry import ActionResponse, Action

logger = logging.getLogger(__name__)

_config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "config.yaml")
_bark_cfg = {}
try:
    with open(_config_path, "r", encoding="utf-8") as f:
        _cfg = yaml.safe_load(f)
    _bark_cfg = _cfg.get("BarkNotify", {})
    if not _bark_cfg.get("device_key"):
        logger.warning("Bark device_key 未配置，bark_push 工具将无法使用")
except Exception as e:
    logger.warning(f"读取 Bark 配置失败: {e}")


@register_function("bark_push", ToolType.WAIT)
def bark_push_formatted(content: str):
    """
    解析结构化内容并推送通知到 iOS 设备，内容可包含标题、时间、地点等字段，当用户说'推送这条消息给我'、'发通知'时调用
    Args:
        content: 结构化文本，支持"标题"、"时间"、"地点"、"内容"等字段，例如"标题:会议提醒\n时间:14:00\n地点:会议室A"
    """
    from bailing.bark_notify import BarkNotifier

    if not _bark_cfg.get("device_key"):
        return ActionResponse(Action.REQLLM, None, "Bark 推送未配置，无法发送通知")

    notifier = BarkNotifier(
        device_key=_bark_cfg.get("device_key", ""),
        base_url=_bark_cfg.get("base_url", "https://api.day.app")
    )
    success = notifier.send_formatted(content)
    if success:
        return ActionResponse(Action.REQLLM, "已推送", "已推送通知到手机")
    else:
        return ActionResponse(Action.REQLLM, None, "Bark 推送失败，内容解析可能有问题")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if not _bark_cfg.get("device_key"):
        logger.error("Bark device_key 未配置，请在 config.yaml 中配置 BarkNotify.device_key")
    else:
        from bailing.bark_notify import BarkNotifier
        notifier = BarkNotifier(
            device_key=_bark_cfg["device_key"],
            base_url=_bark_cfg.get("base_url", "https://api.day.app")
        )
        test_content = "标题:测试推送\n时间:16:00\n地点:办公室\n内容:这是一条来自小爱的结构化推送测试"
        logger.info(f"准备推送: {test_content}")
        success = notifier.send_formatted(test_content)
        if success:
            logger.info("推送成功！请检查手机通知")
        else:
            logger.error("推送失败")