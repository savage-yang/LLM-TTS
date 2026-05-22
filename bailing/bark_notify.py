import requests
import logging
import re
from typing import Dict
from urllib.parse import quote

logger = logging.getLogger(__name__)


class BarkNotifier:
    """Bark推送通知器，用于向iOS设备发送推送通知"""

    def __init__(self, device_key: str, base_url: str = "https://api.day.app"):
        """
        初始化 BarkNotifier

        Args:
            device_key: Bark设备的唯一标识密钥，为空则禁用推送
            base_url: Bark API的基础URL，默认为官方API地址
        """
        self.device_key = device_key
        self.base_url = base_url.rstrip("/")
        self._enabled = bool(device_key)

    def send(self, title: str, body: str = "", group: str = "小爱助手") -> bool:
        """
        发送Bark推送通知

        Args:
            title: 通知标题
            body: 通知正文内容，默认为空
            group: 通知分组名称，默认为"小爱助手"

        Returns:
            bool: 推送是否成功

        Note:
            支持最多3次重试，每次超时时间递增（15s/20s/25s）
            失败时会记录详细日志并等待1秒后重试
        """
        if not self._enabled:
            logger.debug("Bark未配置device_key，跳过推送")
            return False

        url = f"{self.base_url}/{self.device_key}/{quote(title)}"
        if body:
            url += f"/{quote(body)}"
        params = {}
        if group:
            params["group"] = group

        max_retries = 3
        for attempt in range(max_retries):
            try:
                timeout = 15 + attempt * 5
                resp = requests.get(url, params=params, timeout=timeout)
                if resp.status_code == 200:
                    logger.info(f"Bark推送成功: {title}")
                    return True
                else:
                    logger.error(f"Bark推送失败 [{resp.status_code}]: {resp.text}")
                    if attempt < max_retries - 1:
                        import time as _time
                        _time.sleep(1)
            except Exception as e:
                logger.error(f"Bark推送异常 (第{attempt+1}次): {e}")
                if attempt < max_retries - 1:
                    import time as _time
                    _time.sleep(1)
        return False

    def send_formatted(self, content: str) -> bool:
        """
        解析结构化内容并发送格式化的Bark通知

        支持解析包含以下字段的内容文本：
        - 标题: 通知标题
        - 时间/日期: 时间信息
        - 地点: 地点信息
        - 内容: 详细内容

        Args:
            content: 结构化文本内容，支持"标题"、"时间"、"日期"、"地点"、"内容"等字段

        Returns:
            bool: 推送是否成功，解析失败返回False

        Example:
            >>> notifier.send_formatted("标题:会议提醒\\n时间:14:00\\n地点:会议室A\\n内容:周会")
        """
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
        """
        解析结构化文本内容，提取关键字段信息

        支持的字段及其正则匹配规则：
        - title: 匹配"标题:"或"标题："后的内容
        - time: 匹配"时间:"或"日期:"或"时间："或"日期："后的内容
        - location: 匹配"地点:"或"地点："后的内容
        - detail: 匹配"内容:"或"内容："后的内容

        Args:
            content: 待解析的原始文本

        Returns:
            Dict[str, str]: 包含提取字段的字典，可能包含title、time、location、detail键
                           值为"暂无"、"无"或空字符串的字段将被过滤掉
        """
        info: Dict[str, str] = {}
        patterns = {
            "title": r"标题[：:](.+?)(?=\s*(?:时间|日期|地点|内容)|$)",
            "time": r"(?:时间|日期)[：:](.+?)(?=\s*(?:标题|地点|内容)|$)",
            "location": r"地点[：:](.+?)(?=\s*(?:标题|时间|日期|内容)|$)",
            "detail": r"内容[：:](.+?)(?=\s*(?:标题|时间|日期|地点)|$)",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                val = match.group(1).strip()
                if val and val not in ("暂无", "无", ""):
                    info[key] = val
        return info
