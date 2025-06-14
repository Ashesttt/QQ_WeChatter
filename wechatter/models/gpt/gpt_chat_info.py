from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Union

from pydantic import BaseModel

from wechatter.models.gpt.gpt_chat_message import GptChatMessage
from wechatter.models.wechat import Message

if TYPE_CHECKING:
    from wechatter.models.wechat import Person


class GptChatInfo(BaseModel):
    id: Optional[int] = None
    person: "Person"
    topic: str
    model: str
    created_time: datetime = datetime.now()
    talk_time: datetime = datetime.now()
    is_chatting: bool = True
    gpt_chat_messages: List[GptChatMessage] = []

    def get_conversation(self) -> List:
        conversation = []
        for message in self.gpt_chat_messages:
            conversation.extend(message.to_turn())
        return conversation

    def extend_conversation(self, conversation: List):
        conv = []
        for i in range(0, len(conversation) - 1, 2):
            user_content = conversation[i]["content"]
            conv.append(
                GptChatMessage(
                    message=Message(
                        type="text",
                        person=self.person,
                        content=user_content if isinstance(user_content, str) else str(user_content),
                    ),
                    gpt_chat_info=self,
                    gpt_response=conversation[i + 1]["content"],
                    content_type="multimodal" if isinstance(user_content, list) else "text",
                    content=user_content,
                )
            )
        self.gpt_chat_messages.extend(conv)
        return self
