import requests
import logging
import re
from typing import Dict
from urllib.parse import quote

logger = logging.getLogger(__name__)


class BarkNotifier:
    def __init__(self, device_key: str, base_url: str = "https://api.day.app"):
        self.device_key = device_key
        self.base_url = base_url.rstrip("/")
        self._enabled = bool(device_key)

    def send(self, title: str, body: str = "", group: str = "小爱助手") -> bool:
        if not self._enabled:
            logger.debug("Bark未配置device_key，跳过推送")
            return False

        url = f"{self.base_url}/{self.device_key}/{quote(title)}"
        if body:
            url += f"/{quote(body)}"
        params = {}
        if group:
            params["group"] = group

        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                logger.info(f"Bark推送成功: {title}")
                return True
            else:
                logger.error(f"Bark推送失败 [{resp.status_code}]: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Bark推送异常: {e}")
            return False

    def send_formatted(self, content: str) -> bool:
        info = self._parse(content)
        if not info:
            return False
        title = info.get("title", "提醒")
        body_parts = []
        if info.get("time"):
            body_parts.append(f"时间: {info['time']}")
        if info.get("location"):
            body_parts.append(f"地点: {info['location']}")
        if info.get("detail"):
            body_parts.append(info["detail"])
        return self.send(title=title, body="\n".join(body_parts))

    @staticmethod
    def _parse(content: str) -> Dict[str, str]:
        info: Dict[str, str] = {}
        patterns = {
            "title": r"标题[：:]\s*(.+)",
            "time": r"时间[：:]\s*(.+)",
            "location": r"地点[：:]\s*(.+)",
            "detail": r"内容[：:]\s*(.+)",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                val = match.group(1).strip()
                if val and val not in ("暂无", "无", ""):
                    info[key] = val
        return info
