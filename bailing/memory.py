import json
import os
import glob
import logging
import re
from typing import Dict, List, Optional, Any
import openai
from bailing.utils import read_json_file, write_json_file
from bailing.prompt import memory_prompt_template

logger = logging.getLogger(__name__)


class Memory:
    """对话记忆管理类，负责总结和存储对话历史记忆"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化记忆管理器
        
        Args:
            config: 配置字典，包含 dialogue_history_path, memory_file, model_name, api_key, url
        """
        self.dialogue_history_path = config.get("dialogue_history_path")
        self.memory_file = config.get("memory_file")
        
        # 加载已有记忆
        if os.path.isfile(self.memory_file):
            self.memory = read_json_file(self.memory_file)
        else:
            self.memory = {"history_memory_file": [], "memory": ""}

        self.model_name = config.get("model_name")
        self.api_key = config.get("api_key")
        self.base_url = config.get("url")
        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

        # 检查对话文件（不立即生成记忆，避免启动耗时
        self.read_dialogues_in_order(self.dialogue_history_path)

        # 保存记忆文件（确保结构完整）
        write_json_file(self.memory_file, self.memory)

    def get_memory(self) -> str:
        """
        获取当前记忆摘要
        
        Returns:
            记忆摘要字符串
        """
        return self.memory["memory"]

    def rebuild_full_memory(self, directory: str) -> None:
        """
        重新生成完整记忆，处理所有未总结过的历史对话文件
        
        Args:
            directory: 对话历史文件目录
        """
        # 获取所有对话文件
        pattern = os.path.join(directory, 'dialogue-*.json')
        all_dialogue_files = glob.glob(pattern)
        
        # 按时间排序
        all_dialogue_files.sort(key=lambda x: self.extract_time_from_filename(os.path.basename(x)))
        
        # 找出还没被总结过的文件
        processed_files = set(self.memory["history_memory_file"])
        unprocessed_files = [
            file_path for file_path in all_dialogue_files if file_path not in processed_files]
        
        if not unprocessed_files:
            logger.info("没有未处理的对话文件，无需更新记忆")
            return
        
        logger.info(f"发现{len(unprocessed_files)}个未处理的对话文件，正在重新生成记忆...")
        
        # 合并所有未处理的对话内容
        all_new_dialogues = []
        for file_path in unprocessed_files:
            dialogues = self.read_dialogue_file(file_path)
            if dialogues:
                dialogue_str = self.dialogues_history(dialogues)
                all_new_dialogues.append(f"【会话 {os.path.basename(file_path)}】:\n{dialogue_str}")
        
        if not all_new_dialogues:
            logger.info("没有有效的对话内容，无需更新记忆")
            return
        
        # 构造提示词，重新生成完整记忆
        full_dialogue_content = "\n\n".join(all_new_dialogues)
        memory_prompt = memory_prompt_template.replace(
            "${dialogue_abstract}", self.memory["memory"]
        ).replace("${dialogue_history}", full_dialogue_content).strip()
        
        new_memory = None
        try:
            responses = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": memory_prompt}],
                stream=False
            )
            new_memory = responses.choices[0].message.content
        except Exception as e:
            logger.error(f"生成记忆失败: {e}")
            return
        
        if new_memory is not None:
            # 更新记忆和已处理文件列表
            self.memory["history_memory_file"].extend(unprocessed_files)
            self.memory["memory"] = new_memory
            # 保存到文件
            write_json_file(self.memory_file, self.memory)
            logger.info(f"记忆更新完成！已处理{len(unprocessed_files)}个会话，新记忆长度：{len(new_memory)}字")
            logger.debug(f"新记忆内容：{new_memory}")

    @staticmethod
    def extract_time_from_filename(filename: str) -> str:
        """
        从文件名中提取时间信息
        
        Args:
            filename: 对话文件名
        
        Returns:
            提取的时间字符串，失败返回默认时间
        """
        match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', filename)
        if match:
            return match.group(1)
        return "2024-10-03 13:03:35"

    @staticmethod
    def read_dialogue_file(file_path: str) -> List[Dict[str, Any]]:
        """
        读取 JSON 对话文件并返回对话列表
        
        Args:
            file_path: 对话文件路径
        
        Returns:
            对话列表，解析失败返回空列表
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                dialogues = json.load(file)
                return dialogues
        except json.JSONDecodeError as e:
            logger.error(f"解析 JSON 时出错: {e}")
            return []
        except Exception as e:
            logger.error(f"读取对话文件失败: {e}")
            return []

    @staticmethod
    def dialogues_history(dialogues: List[Dict[str, Any]]) -> str:
        """
        将对话列表格式化输出字符串
        
        Args:
            dialogues: 对话列表
        
        Returns:
            格式化后的字符串
        """
        dialogues_str = []
        for dialogue in dialogues:
            role = dialogue.get('role', '未知角色')
            content = dialogue.get('content', '')
            logger.debug(f"{role}: {content}")
            dialogues_str.append(f"{role}: {content}")
        return "\n".join(dialogues_str)

    def read_dialogues_in_order(self, directory: str) -> None:
        """
        读取指定目录下的对话文件，检查是否有新对话需要处理
        
        Args:
            directory: 对话历史文件目录
        """
        # 获取所有符合命名规则的文件路径
        pattern = os.path.join(directory, 'dialogue-*.json')
        files = glob.glob(pattern)

        # 按时间排序
        files.sort(key=lambda x: self.extract_time_from_filename(os.path.basename(x)))
        
        # 只保留最新的1个对话文件，忽略所有旧文件
        if files:
            files = [files[-1]]
            logger.info(f"检查最新对话文件: {files[0]}")

        # 检查是否有新对话文件
        has_new_dialogue = False
        processed_files = set(self.memory["history_memory_file"])
        for file_path in files:
            if file_path in processed_files:
                logger.info(f"{file_path} 对话历史已形成记忆")
                continue
            logger.info(f"发现新对话文件: {file_path}，将在对话结束后自动生成记忆")
            has_new_dialogue = True
        
        # 如果有新对话，标记但不立即处理（避免启动时耗时）
        if has_new_dialogue:
            logger.info("新对话将在下次对话结束时自动总结")
