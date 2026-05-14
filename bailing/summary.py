import os
import logging
import threading
from typing import List, Dict, Any
from datetime import datetime
from bailing.utils import write_json_file

logger = logging.getLogger(__name__)


class SummaryManager:
    """监听内容和总结管理类"""

    def __init__(self, config: Dict[str, Any]):
        listening_config = config.get("ListeningMode", {})
        self.summary_save_path = listening_config.get("summary_save_path", "./tmp/listening_summaries")
        self.raw_save_path = os.path.join(self.summary_save_path, "raw")

        os.makedirs(self.summary_save_path, exist_ok=True)
        os.makedirs(self.raw_save_path, exist_ok=True)

        self.listening_items: List[dict] = []
        self._items_lock = threading.Lock()

        self.current_raw_file = os.path.join(
            self.raw_save_path,
            f"listening-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
        )

        logger.info(f"SummaryManager initialized，保存路径: {self.summary_save_path}")

    def add_listening_item(self, text: str, start_time: float, end_time: float) -> None:
        item = {
            "text": text,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "start_time": start_time,
            "end_time": end_time
        }
        with self._items_lock:
            self.listening_items.append(item)

    def get_raw_text(self) -> str:
        with self._items_lock:
            if not self.listening_items:
                return ""
            raw_text = ""
            for item in self.listening_items:
                raw_text += f"[{item['timestamp']}] {item['text']}\n"
            return raw_text

    def add_summary(self, summary_text: str) -> None:
        with self._items_lock:
            word_count = sum(len(item["text"]) for item in self.listening_items)
            item_count = len(self.listening_items)

            self._save_summary(summary_text, word_count, item_count)
            self._save_raw_items()
            self.listening_items = []

    def _save_summary(self, summary_text: str, word_count: int, item_count: int) -> None:
        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            filepath = os.path.join(self.summary_save_path, f"summary-{date_str}.txt")

            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"总结时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"原始内容字数: {word_count} | 条数: {item_count}\n")
                f.write(f"{'='*50}\n")
                f.write(summary_text)
                f.write("\n")

            logger.info(f"总结已追加到：{filepath}")
        except Exception as e:
            logger.error(f"保存总结失败：{e}")

    def _save_raw_items(self) -> None:
        try:
            write_json_file(self.current_raw_file, self.listening_items)
            logger.info(f"原始监听内容已保存：{self.current_raw_file}")
        except Exception as e:
            logger.error(f"保存原始监听内容失败：{e}")

    def clear(self) -> None:
        with self._items_lock:
            self.listening_items = []