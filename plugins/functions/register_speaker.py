import logging
import os
import sys

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.registry import register_function, ToolType
from plugins.registry import ActionResponse, Action

logger = logging.getLogger(__name__)

_current_audio_data = None


def set_current_audio(audio_data):
    global _current_audio_data
    _current_audio_data = audio_data


@register_function("register_speaker", ToolType.WAIT)
def register_speaker(name: str):
    """
    注册当前说话人的声纹，当用户说'记住我的声音'、'我叫张三，记住我'时调用
    Args:
        name: 说话人名称，如'张三'、'老板'
    """
    from bailing.speaker_diarization import FunASRSpeakerDiarizer
    from bailing.robot import Robot

    if _current_audio_data is None:
        return ActionResponse(Action.REQLLM, None, "没有可用的音频数据，请先说话再注册声纹")

    robot = Robot._instance
    if robot is None:
        return ActionResponse(Action.REQLLM, None, "系统未就绪")

    diarizer = robot.speaker_diarizer
    if not isinstance(diarizer, FunASRSpeakerDiarizer):
        return ActionResponse(Action.REQLLM, None, "说话人分离功能未启用，请在配置中开启 SpeakerDiarization")

    success = diarizer.register_speaker(name, _current_audio_data)
    if success:
        msg = f"已注册声纹：{name}，以后我就能认出你了"
        logger.info(msg)
        return ActionResponse(Action.REQLLM, msg, msg)
    else:
        return ActionResponse(Action.REQLLM, None, f"声纹注册失败，请再试一次")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("register_speaker 工具已就绪（需在 Robot 运行时使用）")
