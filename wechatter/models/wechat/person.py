import enum
from typing import Optional

from pydantic import BaseModel


class Gender(enum.Enum):
    """
    性别类
    """

    male = "male"
    female = "female"
    unknown = "unknown"


class Person(BaseModel):
    """
    个人消息类
    """

    id: str
    name: str
    alias: str
    gender: Gender
    signature: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    # phone_list: List[str]
    is_star: bool
    is_friend: bool
    is_official_account: bool = False
    is_gaming: bool = False
    # TODO：数据库也添加上：（为了实现管理人员功能）（收到信息，取到guild_id或其他id，判断是否为管理人员）
    guild_id:  Optional[str] = None # qq频道私聊
    msg_id: Optional[str] = None
    member_openid: Optional[str] = None # qq群
    user_openid: Optional[str] = None # qq私聊

    def to_dict(self):
        result = self.__dict__.copy()
        result["gender"] = self.gender.value
        return result
