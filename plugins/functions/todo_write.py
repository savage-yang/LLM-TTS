import json
import logging
import os
import sys

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.registry import register_function, ToolType
from plugins.registry import ActionResponse, Action

logger = logging.getLogger(__name__)

_todo_file = os.path.join(os.path.dirname(__file__), "..", "..", "tmp", "todos.json")


def _load() -> list[dict]:
    if not os.path.exists(_todo_file):
        return []
    try:
        with open(_todo_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(todos: list[dict]):
    os.makedirs(os.path.dirname(_todo_file), exist_ok=True)
    with open(_todo_file, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


def _fmt(todos: list[dict]) -> str:
    if not todos:
        return "没有待办事项"
    icons = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}
    lines = []
    for i, t in enumerate(todos, 1):
        icon = icons.get(t["status"], "[ ]")
        p = t.get("priority", "medium")
        lines.append(f"{i}. {icon} [{p}] {t['content']}")
    return "\n".join(lines)


@register_function("todo_write", ToolType.WAIT)
def todo_write(
    action: str,
    content: str = "",
    todo_id: str = "",
    tasks: str = "",
    priority: str = "medium",
):
    """
    任务规划与进度跟踪工具。当用户提出的需求需要多个步骤完成时，自动拆解为任务列表并跟踪进度。
    Args:
        action: 操作类型
          - "plan"   用 tasks 参数批量创建任务计划（tasks 是 JSON 数组字符串，每项含 content 和可选 priority）
          - "start"  开始某个任务（todo_id 必填），标记为进行中
          - "done"   完成某个任务（todo_id 必填）
          - "list"   查看当前所有任务及进度
          - "abort"  中止当前计划，清空所有未完成任务
          - "add"    追加单个任务（content 必填）
          - "delete" 删除某个任务（todo_id 必填）
        content: 单个任务内容，add 时必填
        todo_id: 任务序号（从1开始），start/done/delete 时必填
        tasks: 任务列表 JSON 字符串，plan 时必填，格式: '[{"content": "第一步", "priority": "high"}, {"content": "第二步", "priority": "medium"}]'
        priority: 优先级，可选 high / medium / low，仅 add 时有效
    """
    todos = _load()

    if action == "plan":
        if not tasks:
            return ActionResponse(Action.REQLLM, None, "请提供 tasks 参数")
        try:
            items = json.loads(tasks)
            if not isinstance(items, list):
                raise ValueError("tasks 必须是数组")
            plan = []
            for item in items:
                plan.append({
                    "content": item.get("content", ""),
                    "priority": item.get("priority", "medium"),
                    "status": "pending",
                })
            _save(plan)
            msg = f"已创建任务计划，共 {len(plan)} 步：\n{_fmt(plan)}"
            logger.info(msg)
            return ActionResponse(Action.REQLLM, msg, msg)
        except Exception as e:
            return ActionResponse(Action.REQLLM, None, f"tasks 解析失败: {e}")

    elif action == "start":
        if not todo_id:
            return ActionResponse(Action.REQLLM, None, "请提供 todo_id")
        try:
            idx = int(todo_id) - 1
            if idx < 0 or idx >= len(todos):
                return ActionResponse(Action.REQLLM, None, f"序号 {todo_id} 不存在")
            todos[idx]["status"] = "in_progress"
            _save(todos)
            msg = f"开始执行：{todos[idx]['content']}\n当前进度：\n{_fmt(todos)}"
            logger.info(msg)
            return ActionResponse(Action.REQLLM, msg, msg)
        except ValueError:
            return ActionResponse(Action.REQLLM, None, "todo_id 必须是数字")

    elif action == "done":
        if not todo_id:
            return ActionResponse(Action.REQLLM, None, "请提供 todo_id")
        try:
            idx = int(todo_id) - 1
            if idx < 0 or idx >= len(todos):
                return ActionResponse(Action.REQLLM, None, f"序号 {todo_id} 不存在")
            todos[idx]["status"] = "done"
            _save(todos)
            msg = f"已完成：{todos[idx]['content']}\n当前进度：\n{_fmt(todos)}"
            logger.info(msg)
            return ActionResponse(Action.REQLLM, msg, msg)
        except ValueError:
            return ActionResponse(Action.REQLLM, None, "todo_id 必须是数字")

    elif action == "list":
        formatted = _fmt(todos)
        logger.info(f"查看任务进度:\n{formatted}")
        return ActionResponse(Action.REQLLM, formatted, formatted)

    elif action == "add":
        if not content:
            return ActionResponse(Action.REQLLM, None, "请提供 content")
        todos.append({
            "content": content,
            "priority": priority,
            "status": "pending",
        })
        _save(todos)
        msg = f"已添加任务：{content}\n当前任务列表：\n{_fmt(todos)}"
        logger.info(msg)
        return ActionResponse(Action.REQLLM, msg, msg)

    elif action == "delete":
        if not todo_id:
            return ActionResponse(Action.REQLLM, None, "请提供 todo_id")
        try:
            idx = int(todo_id) - 1
            if idx < 0 or idx >= len(todos):
                return ActionResponse(Action.REQLLM, None, f"序号 {todo_id} 不存在")
            removed = todos.pop(idx)
            _save(todos)
            msg = f"已删除：{removed['content']}\n当前任务列表：\n{_fmt(todos)}"
            logger.info(msg)
            return ActionResponse(Action.REQLLM, msg, msg)
        except ValueError:
            return ActionResponse(Action.REQLLM, None, "todo_id 必须是数字")

    elif action == "abort":
        _save([])
        msg = "已中止当前计划，清空所有任务"
        logger.info(msg)
        return ActionResponse(Action.REQLLM, msg, msg)

    else:
        return ActionResponse(Action.REQLLM, None, f"不支持的操作: {action}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    rsp = todo_write("plan", tasks='[{"content":"分析项目结构","priority":"high"},{"content":"检查每个文件","priority":"high"},{"content":"总结问题列表","priority":"medium"}]')
    print(rsp.response)
    print("---")
    rsp = todo_write("start", todo_id="1")
    print(rsp.response)
    print("---")
    rsp = todo_write("done", todo_id="1")
    print(rsp.response)