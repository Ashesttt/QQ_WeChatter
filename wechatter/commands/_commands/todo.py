import os
import re
from typing import List, Union

from loguru import logger

from wechatter.commands.handlers import command
from wechatter.models.wechat import SendTo
from wechatter.sender import sender
from wechatter.utils import get_abs_path, load_json, save_json


# TODO: 使用SQLite进行数据持久化
@command(
    command="todo",
    keys=["待办事项", "待办", "todo"],
    desc="获取待办事项。",
)
async def todo_command_handler(to: Union[str, SendTo], message: str = "") -> None:
    # 判断是查询还是添加
    if message == "":
        # 获取待办事项
        result = view_todos(to.p_id, to.p_name)
        sender.send_msg(to, result)
    else:
        # 添加待办事项
        try:
            add_todo_task(to.p_id, message)
            result = view_todos(to.p_id, to.p_name)
            sender.send_msg(to, result)
        except Exception as e:
            error_message = f"添加待办事项失败，错误信息：{str(e)}"
            logger.error(error_message)
            sender.send_msg(to, error_message)


@command(
    command="todo-remove",
    keys=["删除待办事项", "todo-remove", "rmtd"],
    desc="删除待办事项。",
)
def remove_todo_command_handler(to: Union[str, SendTo], message: str = "") -> None:
    indices = [
        int(idx.strip()) - 1
        for idx in re.split(r"[\s,]+", message)
        if idx.strip().isdigit()
    ]
    if not indices:
        sender.send_msg(to, "输入有效数字来删除待办事项")
        return

    try:
        remove_result = remove_todo_task(to.p_id, indices)
        sender.send_msg(to, remove_result)
    except Exception as e:
        error_message = f"删除待办事项失败，错误信息：{str(e)}"
        logger.error(error_message)
        sender.send_msg(to, error_message)
    else:
        result = view_todos(to.p_id, to.p_name)
        sender.send_msg(to, result)


def _load_todos(person_id: str) -> List[str]:
    """加载特定用户的待办事项"""
    file_path = get_abs_path(os.path.join("data", "todos", f"p{person_id}_todo.json"))
    if os.path.exists(file_path):
        return load_json(file_path)
    return []


def _save_todos(person_id: str, content: List[str]) -> None:
    """保存待办事项到特定用户的 JSON 文件中"""
    file_path = get_abs_path(os.path.join("data", "todos", f"p{person_id}_todo.json"))
    save_json(file_path, content)


def add_todo_task(person_id: str, task: str) -> None:
    """向待办事项列表中添加任务，并返回添加是否成功的状态"""
    todos = _load_todos(person_id)
    todos.append(task)  # 直接在原始列表上添加任务
    _save_todos(person_id, todos)


def remove_todo_task(person_id: str, task_indices: List[int]) -> str:
    """从待办事项列表中删除任务，并返回删除的任务"""
    todos = _load_todos(person_id)
    removed_tasks = []
    for task_index in sorted(task_indices, reverse=True):
        if 0 <= task_index < len(todos):
            removed_task = todos.pop(task_index)  # 删除对应索引的任务
            removed_tasks.append(removed_task)
        else:
            logger.error(f"待办事项索引 {task_index + 1} 不存在")
            raise IndexError(f"待办事项索引 {task_index + 1} 不存在")

    _save_todos(person_id, todos)

    successful_removals = "✅成功删除待办事项✅\n"
    successful_removals += "\n".join(
        f"{i + 1}. {task}" for i, task in enumerate(removed_tasks)
    )
    return successful_removals


def view_todos(person_id: str, person_name: str) -> str:
    """查看特定用户的所有待办事项"""
    todos = _load_todos(person_id)
    p_name = person_name
    if todos:
        formatted_todos = f"✨{p_name}的待办事项✨\n"
        formatted_todos += "\n".join(f"{i + 1}. {task}" for i, task in enumerate(todos))
    else:
        formatted_todos = "没有待办事项。"
    return formatted_todos
