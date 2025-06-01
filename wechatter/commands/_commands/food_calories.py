from typing import Dict, List, Union, Any, Coroutine
from urllib.parse import quote
import re

import requests
from bs4 import BeautifulSoup
from loguru import logger

from wechatter.commands.handlers import command
from wechatter.commands.mcp import mcp_server
from wechatter.exceptions import Bs4ParsingError
from wechatter.models.wechat import SendTo
from wechatter.sender import sender
from wechatter.utils import get_request


@command(
    command="food-calories",
    keys=["食物热量", "food-calories", "热量", "calories", "卡路里"],
    desc="获取食物热量信息（数据来源：喵咕美食）。",
)
async def food_calories_command_handler(to: Union[str, SendTo], message: str = "") -> None:
    try:
        result = get_food_calories_str(message)
    except Exception as e:
        error_message = f"获取食物热量失败，错误信息：{str(e)}"
        logger.error(error_message)
        sender.send_msg(to, error_message)
    else:
        sender.send_msg(to, result)


@food_calories_command_handler.mainfunc
def get_food_calories_str(message: str) -> str:
    if not message:
        return "查询失败，请输入食物名称"

    search_url = f"https://www.miaofoods.com/search/{quote(message)}.html"
    response = get_request(url=search_url)
    food_list = _parse_search_results(response)
    food_details = _get_food_details(food_list)
    return _generate_food_message(food_details)


def _get_food_details(food_list: List[Dict]) -> List[Dict]:
    """获取食物详情列表"""
    details = []
    for food in food_list[:5]:  # 取前5个结果
        try:
            detail_url = f"https://www.miaofoods.com{food['path']}"
            response = get_request(url=detail_url)
            detail = _parse_detail_page(response)
            details.append(detail)
        except Exception as e:
            logger.warning(f"获取食物详情失败：{str(e)}")
            continue

    if not details:
        logger.error("没有找到有效的营养信息")
        raise ValueError("没有找到有效的营养信息")
    return details


def _generate_food_message(food_details: List[Dict]) -> str:
    """生成格式化消息"""
    if not food_details:
        logger.error("食物详情列表为空")
        raise ValueError("食物详情列表为空")

    msg = "✨=====食物列表=====✨\n"
    for idx, item in enumerate(food_details, 1):
        msg += (
            f"{idx}. {item['name']}\n"
            f"   ✅ 分类：{item.get('category', 'N/A')}\n"
            f"   🔥 热量：{item.get('calories', 'N/A')}kcal\n"
            f"   🍚 碳水：{item.get('carbohydrate', 'N/A')}g\n"  # 注意保持key一致性
            f"   🥩 蛋白质：{item.get('protein', 'N/A')}g\n"
            f"   🧈 脂肪：{item.get('fat', 'N/A')}g\n"
            "────────────────────\n"
        )
    return msg


def _parse_search_results(response: requests.Response) -> List[Dict]:
    """解析搜索结果页面"""
    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find("script", string=lambda t: t and "window.__NUXT__" in t)

    if not script_tag:
        logger.error("未找到包含 window.__NUXT__ 的脚本标签")
        raise Bs4ParsingError("解析搜索结果失败")

    script_content = script_tag.string
    match = re.search(r"curSearchFoodList\s*:\s*\[(.*?)\](,|\})", script_content, re.DOTALL)

    if not match:
        logger.error("未找到 curSearchFoodList 数据")
        raise Bs4ParsingError("解析食物列表失败")

    food_list_str = match.group(1)
    food_tokens = re.findall(r'foodToken\s*:\s*"(.*?)"', food_list_str)

    return [{"path": f"/detail/{token}.html"} for token in food_tokens[:10]]


def _parse_detail_page(response: requests.Response) -> Dict:
    """解析详情页营养信息"""
    soup = BeautifulSoup(response.text, "html.parser")
    nutrition = {}

    # 解析基础信息
    info_div = soup.find("div", class_="food-detail-info")
    if info_div:
        for sub_div in info_div.find_all("div", class_="mtb-10"):
            text = sub_div.get_text(strip=True)
            if text.startswith("名称："):
                name_span = sub_div.find("span")
                if name_span:
                    nutrition["name"] = name_span.get_text(strip=True)
            elif text.startswith("分类："):
                category_span = sub_div.find("span")
                if category_span:
                    nutrition["category"] = category_span.get_text(strip=True)

    # 解析营养成分
    for div in soup.find_all("div", class_="food-detail-view"):
        spans = div.find_all("span")
        if len(spans) == 2:
            key = spans[0].get_text(strip=True)
            value = spans[1].get_text(strip=True)
            key_map = {
                "热量": "calories",
                "脂肪": "fat",
                "蛋白质": "protein",
                "碳水化合物": "carbohydrate"
            }
            if key in key_map:
                nutrition[key_map[key]] = value

    # 必要字段校验
    if "name" not in nutrition:
        logger.warning("未能解析到食物名称")
        raise ValueError("食物信息不完整")

    return nutrition

@mcp_server.tool(
    name="get_food_calories",
    description="获取食物热量信息（数据来源：喵咕美食）。",
)
async def get_food_calories(message: str) -> Coroutine[Any, Any, str] | str:
    """
    获取食物相关信息，包括食物的分类，热量，碳水，蛋白质，脂肪
    :param message: 食物名称
    :return: 食物相关信息
    """
    try:
        result = get_food_calories_str(message)
        return result
    except Exception as e:
        error_message = f"获取食物热量失败，错误信息：{str(e)}"
        logger.error(error_message)
        return error_message

