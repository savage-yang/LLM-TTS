import logging
import os
import sys
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

if __name__ != "__main__":
    from plugins.registry import register_function, ToolType
    from plugins.registry import ActionResponse, Action

    @register_function('web_search', action=ToolType.TIME_CONSUMING)
    def web_search(query: str):
        return _web_search(query)
else:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from plugins.registry import ActionResponse, Action


def _web_search(query: str):
    """
    搜索互联网信息

    Args:
        query: 搜索关键词

    Returns:
        ActionResponse: 搜索结果
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    try:
        url = f'https://www.sogou.com/web?query={quote(query)}'
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return ActionResponse(Action.REQLLM, "搜索失败", None)

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        for item in soup.select('.vrwrap, .rb'):
            link_tag = item.select_one('h3 a')
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True)
            if not title or len(title) < 4:
                continue
            href = link_tag.get('href', "")
            abstract_tag = item.select_one('.star-wiki, .str-text, .space-txt')
            abstract = abstract_tag.get_text(strip=True) if abstract_tag else ""
            results.append(f"{title}\n{abstract}\n{href}")

        if not results:
            for tag in soup.find_all(['p', 'h3']):
                text = tag.get_text(strip=True)
                if len(text) > 15:
                    results.append(text)

        content = "\n---\n".join(results[:5]) if results else "未找到相关结果"
        return ActionResponse(Action.REQLLM, content, None)

    except Exception as e:
        logger.error(f"搜索出错: {e}")
        return ActionResponse(Action.REQLLM, "搜索失败", None)


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    rsp = _web_search("全世界有多少个国家")
    print(f"Action: {rsp.action}")
    print(f"Result:\n{rsp.result}")
    print(f"Response: {rsp.response}")