import enum
from typing import TYPE_CHECKING, Optional, Any

from pydantic import BaseModel
from typing_extensions import Union, List, Dict

if TYPE_CHECKING:
    from wechatter.models.gpt.gpt_chat_info import GptChatInfo
    from wechatter.models.wechat import Message


class GptChatRole(enum.Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class GptChatMessage(BaseModel):
    id: Optional[int] = None
    message: "Message"
    gpt_chat_info: "GptChatInfo"
    gpt_response: str
    content_type: str = "text"  # 新增字段，用于标识内容类型
    content: Union[str, List[Dict[str, Any]]] = ""  # 新增字段，支持字符串或复杂对象

    def to_turn(self):
        return [
            {
                "role": GptChatRole.user.value,
                "content": self.message.content,
            },
            {
                "role": GptChatRole.assistant.value,
                "content": self.gpt_response,
            },
        ]
