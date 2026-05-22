import logging
import os
import sys
import requests
from bs4 import BeautifulSoup

# 确保项目根目录在 sys.path 中，支持直接 python xxx.py 运行
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.registry import register_function, ToolType
from plugins.registry import ActionResponse, Action

logger = logging.getLogger(__name__)

@register_function('get_weather', ToolType.WAIT)
def get_weather(city: str):
    """
    "获取某个地点的天气，用户应先提供一个位置，\n比如用户说杭州天气，参数为：zhejiang/hangzhou，\n\n比如用户说北京天气怎么样，参数为：beijing/beijing",
    city : 城市，zhejiang/hangzhou
    """
    url = "https://tianqi.moji.com/weather/china/"+city
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
    }
    try:
        # 加10秒超时，避免卡住
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code!=200:
            return ActionResponse(Action.REQLLM, None, "天气查询失败，请稍后再试")
        soup = BeautifulSoup(response.text, "html.parser")
        weather = soup.find('meta', attrs={'name':'description'})["content"]
        weather = weather.replace("墨迹天气", "")
        return ActionResponse(Action.REQLLM, weather, weather)
    except Exception as e:
        logger.error(f"天气查询出错: {e}")
        return ActionResponse(Action.REQLLM, None, "天气查询服务暂时不可用，请稍后再试")

if __name__ == "__main__":
    rsp = get_weather("zhejiang/hangzhou")
    print(rsp.response, rsp.action, rsp.result)