import asyncio
import json
import os
from typing import List, Dict, Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from loguru import logger

class MCPChatClient:
    def __init__(self, model: str, api_key: str, base_url: str):
        """
        初始化MCP客户端
        
        Args:
            model: LLM模型名称
            api_key: API密钥
            base_url: API基础URL
        """
        self.session = None
        self.write = None
        self.read = None
        
        self.model = model
        self.llm = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        # import sys
        # # 使用当前Python解释器路径
        # python_executable = sys.executable
        
        self.server_params = StdioServerParameters(
            # command=python_executable,  # 使用当前Python解释器
            command="python",
            args=["-m", "wechatter.commands.mcp.server"],
            env=None
        )
        self.tools = []

    async def initialize(self):
        """初始化MCP客户端，连接服务器并获取工具列表"""
        self.read, self.write = await stdio_client(self.server_params).__aenter__()
        self.session = await ClientSession(self.read, self.write).__aenter__()
        await self.session.initialize()
        tools_response = await self.session.list_tools()
        logger.critical("原始的list_tools()", tools_response)
        self.tools = tools_response.tools
        logger.info(f"MCP客户端初始化完成，可用工具：{[tool.name for tool in self.tools]}")
        return self

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        与LLM进行对话，支持工具调用
        
        Args:
            messages: 对话历史
            
        Returns:
            str: LLM回复内容
        """
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in self.tools]

        # 请求LLM
        response = await self.llm.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=available_tools
        )
        message = response.choices[0].message
        logger.critical("原始的chat()", response)
        logger.critical("处理后的chat()", message)

        # 如果没有工具调用，直接返回内容
        if not message.tool_calls:
            logger.info(f"LLM没有调用工具，直接回复了：{message.content}")
            return message.content or ""

        # 先添加助手消息（包含工具调用）
        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [tc.model_dump() for tc in message.tool_calls]
        })
        
        # 处理工具调用
        tool_messages = []
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
        
            # 调用工具并获取结果
            result = await self.session.call_tool(tool_name, tool_args)
            logger.info(f"调用工具 {tool_name}，参数 {tool_args}，结果：{result.content}")
        
            # 添加工具调用结果到消息列表
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result.content)
            })
        
        # 将工具响应添加到消息列表
        messages.extend(tool_messages)

        final_response = await self.llm.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=available_tools
        )

        return final_response.choices[0].message.content or ""

    async def close(self):
        """关闭MCP客户端连接"""
        await self.session.__aexit__(None, None, None)
        await self.read.__aexit__(None, None, None)
