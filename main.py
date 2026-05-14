#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
塔菲智能语音助手 - 主程序入口
@Author: 寒江雪
@Date: 2026-05-09
"""

# --------------------------

import os
import sys
import argparse
import logging
import yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bailing.robot import create_robot

# --------------------------
# 日志全局配置
# --------------------------
def setup_logging(config_path: str = "config/config.yaml") -> None:
    """全局日志初始化配置，统一日志格式和级别"""
    # 先读取配置文件获取日志级别
    log_level = logging.INFO
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            level_str = config.get('logging', {}).get('level', 'INFO').upper()
            level_map = {
                'DEBUG': logging.DEBUG,
                'INFO': logging.INFO,
                'WARNING': logging.WARNING,
                'ERROR': logging.ERROR
            }
            log_level = level_map.get(level_str, logging.INFO)
    except Exception as e:
        print(f"读取日志配置失败，使用默认INFO级别: {e}")

    # 日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 清除已有日志处理器，避免重复输出
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(),  # 控制台输出
            logging.FileHandler('tmp/bailing.log', encoding='utf-8')  # 文件输出
        ],
        force=True
    )

    # 屏蔽第三方库冗余日志，只保留WARNING及以上级别
    third_party_loggers = [
        "torch", "transformers", "funasr", "silero_vad",
        "pyaudio", "pygame", "urllib3", "requests", "httpx",
        "httpcore", "websocket", "websockets", "dashscope",
        "pydub", "sounddevice"
    ]
    for logger_name in third_party_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

def main() -> None:
    """主程序入口"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="塔菲智能语音助手")
    parser.add_argument(
        '--config-path', 
        type=str, 
        help="配置文件路径", 
        default="config/config.yaml"
    )
    args = parser.parse_args()

    # 确保必要目录存在
    os.makedirs("tmp", exist_ok=True)
    os.makedirs("voice_cache", exist_ok=True)

    # 初始化日志
    setup_logging(args.config_path)
    logger = logging.getLogger(__name__)
    logger.info("塔菲智能语音助手启动中...")

    # 检查配置文件是否存在
    if not os.path.exists(args.config_path):
        logger.error(f"配置文件不存在: {args.config_path}，请检查路径后重试")
        sys.exit(1)

    try:
        # 创建机器人实例并运行
        robot = create_robot(args.config_path)
        logger.info("初始化完成，等待用户语音指令...")
        robot.run()
    except KeyboardInterrupt:
        logger.info("收到用户中断信号，程序退出")
    except Exception as e:
        logger.critical(f"程序异常退出: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
 