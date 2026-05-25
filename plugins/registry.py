from enum import Enum
import logging

logger = logging.getLogger(__name__)

function_registry = {}

def register_function(name, action=None):
    def decorator(func):
        function_registry[name] = func
        if action:
            func.action = action
        logger.info(f"函数 '{name}' 注册成功")
        return func
    return decorator

listener_registry = {}

def register_listener(name: str):
    """注册监听模式处理器的装饰器，name 为特殊 token 名（不含尖括号）"""
    def decorator(func):
        listener_registry[name] = func
        logger.info(f"监听处理器 '{name}' 注册成功")
        return func
    return decorator

class ToolType(Enum):
    NONE = (1, "调用完工具后，啥也不用管")
    WAIT = (2, "调用工具，等待函数返回")
    SCHEDULER= (3, "定时任务，时间到了之后，直接回复")
    TIME_CONSUMING = (4, "耗时任务，需要一定时间，后台运行有结果后再回复")
    ADD_SYS_PROMPT = (5, "增加系统指定到对话历史中去")

    def __init__(self, code, message):
        self.code = code
        self.message = message


class Action(Enum):
    NOTFOUND = (0, "没有找到函数")
    NONE = (1,  "啥也不干")
    RESPONSE = (2, "直接回复")
    REQLLM = (3, "调用函数后再请求llm生成回复")
    ADDSYSTEM = (4, "添加系统prompt到对话中去")
    ADDSYSTEMSPEAK = (5, "添加系统prompt到对话中去&主动说话")

    def __init__(self, code, message):
        self.code = code
        self.message = message

class ActionResponse:
    def __init__(self, action : Action, result, response):
        self.action = action # 动作类型
        self.result = result # 动作产生的结果
        self.response = response # 直接回复的内容



