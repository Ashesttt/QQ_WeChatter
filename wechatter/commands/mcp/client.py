import asyncio
import json
import os
from typing import List, Dict, Any, Optional
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from loguru import logger
import traceback
import subprocess

class MCPChatClient:
    def __init__(self, model: str, api_key: str, base_url: str):
        """
        初始化MCP客户端
        
        Args:
            model: LLM模型名称
            api_key: API密钥
            base_url: API基础URL
        """
        self.model = model
        self.llm = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        self.tools = []
        self._initialized = False
        self._lock = asyncio.Lock()
        self._process = None
        self._stdin = None
        self._stdout = None
        self._stderr = None

    async def _start_server(self):
        """启动MCP服务器进程"""
        try:
            if not self._process:
                logger.info("正在启动MCP服务器进程...")
                
                # # 获取服务器脚本的绝对路径
                # current_dir = Path(__file__).parent
                # server_script = current_dir / "server.py"
                # 
                # if not server_script.exists():
                #     raise FileNotFoundError(f"服务器脚本不存在: {server_script}")
                
                self._process = await asyncio.create_subprocess_exec(
                    sys.executable,  # 使用当前Python解释器
                    # str(server_script),  # 直接运行Python文件
                    "-m",
                    "wechatter.commands.mcp.server",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=os.environ.copy()  # 复制当前环境变量
                )
                self._stdin = self._process.stdin
                self._stdout = self._process.stdout
                self._stderr = self._process.stderr
                
                # 启动错误日志监控任务
                asyncio.create_task(self._monitor_stderr())
                
                # 等待服务器就绪
                while True:
                    line = await self._stdout.readline()
                    if not line:
                        raise RuntimeError("Server process terminated unexpectedly")
                    try:
                        response = json.loads(line.decode())
                        if response.get("status") == "ready":
                            break
                    except json.JSONDecodeError:
                        continue
                
                logger.info("MCP服务器进程已启动")
        except Exception as e:
            logger.error(f"启动服务器错误: {str(e)}\n{traceback.format_exc()}")
            raise

    async def _monitor_stderr(self):
        """监控服务器的错误输出"""
        try:
            while True:
                line = await self._stderr.readline()
                if not line:
                    break
                logger.error(f"MCP服务器错误: {line.decode().strip()}")
        except Exception as e:
            logger.error(f"监控错误输出时发生错误: {str(e)}")

    async def _stop_server(self):
        """停止MCP服务器进程"""
        try:
            if self._process:
                logger.info("正在停止MCP服务器进程...")
                if self._stdin:
                    self._stdin.close()
                    await self._stdin.wait_closed()
                if self._process.returncode is None:
                    self._process.terminate()
                    await self._process.wait()
                logger.info("MCP服务器进程已停止")
        except Exception as e:
            logger.error(f"停止服务器错误: {str(e)}")
        finally:
            self._process = None
            self._stdin = None
            self._stdout = None
            self._stderr = None

    async def _send_request(self, request: Dict) -> Dict:
        """发送请求到服务器并获取响应"""
        if not self._process or not self._stdin or not self._stdout:
            raise RuntimeError("Client not initialized")
        
        try:
            request_str = json.dumps(request) + "\n"
            logger.debug(f"发送请求: {request_str.strip()}")
            self._stdin.write(request_str.encode())
            await self._stdin.drain()
            
            # 读取响应
            response_str = await self._stdout.readline()
            if not response_str:
                raise RuntimeError("No response from server")
            
            response_str = response_str.decode().strip()
            logger.debug(f"收到响应: {response_str}")
            
            if not response_str:
                raise RuntimeError("Empty response from server")
            
            try:
                return json.loads(response_str)
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析错误: {str(e)}, 原始响应: {response_str}")
                raise
        except Exception as e:
            logger.error(f"发送请求错误: {str(e)}\n{traceback.format_exc()}")
            raise

    async def initialize(self):
        """初始化MCP客户端，连接服务器并获取工具列表"""
        try:
            async with self._lock:
                if not self._initialized:
                    logger.info("正在初始化MCP客户端...")
                    await self._start_server()
                    
                    # # 等待服务器启动
                    # logger.info("等待服务器启动...")
                    # await asyncio.sleep(2)  # 增加等待时间
                    
                    # 发送初始化请求
                    logger.info("正在获取工具列表...")
                    try:
                        tools_response = await self._send_request({
                            "type": "list_tools"
                        })
                        
                        if not tools_response or "tools" not in tools_response:
                            raise RuntimeError(f"Invalid response from server: {tools_response}")
                        
                        self.tools = tools_response["tools"]
                        logger.info(f"MCP客户端初始化完成，可用工具：{[tool['name'] for tool in self.tools]}")
                        self._initialized = True
                    except Exception as e:
                        logger.error(f"获取工具列表失败: {str(e)}")
                        raise
                return self
        except Exception as e:
            logger.error(f"初始化错误: {str(e)}\n{traceback.format_exc()}")
            await self._stop_server()
            raise

    async def process_llm_conversation_with_tools(self, messages: List[Dict[str, str]]) -> str:
        """
        与LLM进行对话，支持工具调用
        
        Args:
            messages: 对话历史
            
        Returns:
            str: LLM回复内容
        """
        try:
            async with self._lock:
                if not self._initialized:
                    await self.initialize()

                available_tools = [{
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["inputSchema"]
                    }
                } for tool in self.tools]

                # 请求LLM
                response = await self.llm.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=available_tools
                )
                message = response.choices[0].message
                logger.debug(f"LLM响应: {message}")

                if not message.tool_calls:
                    logger.info(f"LLM没有调用工具，直接回复了：{message.content}")
                    return message.content or ""

                # 处理工具调用
                messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [tc.model_dump() for tc in message.tool_calls]
                })
                
                tool_messages = []
                for tool_call in message.tool_calls:
                    try:
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)
                        result = await self._send_request({
                            "type": "call_tool",
                            "name": tool_name,
                            "args": tool_args
                        })
                        logger.info(f"调用工具 {tool_name}，参数 {tool_args}，结果：{result['content']}")
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(result["content"])
                        })
                    except Exception as e:
                        logger.error(f"工具调用错误 {tool_name}: {str(e)}")
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"工具调用失败: {str(e)}"
                        })
                
                messages.extend(tool_messages)

                final_response = await self.llm.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=available_tools
                )

                return final_response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"聊天错误: {str(e)}\n{traceback.format_exc()}")
            raise

    async def close(self):
        """关闭MCP客户端连接"""
        async with self._lock:
            await self._stop_server()
            self._initialized = False
