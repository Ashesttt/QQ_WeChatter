# wechatter/mcp/server.py
import json
import sys
import asyncio
import functools
from typing import Dict, Any, Callable, Optional
from loguru import logger
import logging

class MCPServer:
    def __init__(self):
        self.tools = []
        self._tool_functions = {}
        # 配置日志
        logger.remove()
        # 将日志输出到stderr，并确保不会干扰stdout的JSON通信
        logger.add(sys.stderr, level="ERROR", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
        
        # 禁用urllib3的调试日志
        logging.getLogger('urllib3').setLevel(logging.WARNING)

    def tool(self, name: Optional[str] = None, description: Optional[str] = None):
        """工具装饰器"""
        def decorator(func: Callable):
            tool_name = name or func.__name__
            tool_description = description or func.__doc__ or ""
            
            # 获取函数的参数信息
            import inspect
            sig = inspect.signature(func)
            parameters = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
                parameters[param_name] = {
                    "type": "string",  # 默认类型为字符串
                    "description": param.annotation if isinstance(param.annotation, str) else ""
                }
            
            # 创建工具定义
            tool_def = {
                "name": tool_name,
                "description": tool_description,
                "inputSchema": {
                    "type": "object",
                    "properties": parameters,
                    "required": required
                }
            }
            
            # 添加到工具列表
            self.tools.append(tool_def)
            self._tool_functions[tool_name] = func
            
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            
            return wrapper
        return decorator

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """处理请求"""
        try:
            request_type = request.get("type")
            if request_type == "list_tools":
                return {"tools": self.tools}
            elif request_type == "call_tool":
                tool_name = request.get("name")
                tool_args = request.get("args", {})
                return await self.call_tool(tool_name, tool_args)
            else:
                return {"error": f"Unknown request type: {request_type}"}
        except Exception as e:
            logger.error(f"处理请求错误: {str(e)}")
            return {"error": str(e)}

    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        try:
            if tool_name in self._tool_functions:
                func = self._tool_functions[tool_name]
                result = await func(**args)
                return {"content": result}
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"调用工具错误: {str(e)}")
            return {"error": str(e)}

    async def run(self):
        """运行服务器"""
        try:
            # 发送就绪信号
            sys.stdout.write(json.dumps({"status": "ready"}) + "\n")
            sys.stdout.flush()

            while True:
                # 读取请求
                request_str = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                if not request_str:
                    break

                try:
                    # 解析请求
                    request = json.loads(request_str)
                    # 处理请求
                    response = await self.handle_request(request)
                    # 发送响应
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析错误: {str(e)}")
                    sys.stdout.write(json.dumps({"error": "Invalid JSON request"}) + "\n")
                    sys.stdout.flush()
                except Exception as e:
                    logger.error(f"处理请求错误: {str(e)}")
                    sys.stdout.write(json.dumps({"error": str(e)}) + "\n")
                    sys.stdout.flush()
        except Exception as e:
            logger.error(f"服务器运行错误: {str(e)}")
            sys.exit(1)

def main():
    """主函数，用于直接运行服务器"""
    # 禁用urllib3的调试日志
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    # 导入共享的MCP服务器实例
    from wechatter.commands.mcp import mcp_server
    
    # 运行服务器
    asyncio.run(mcp_server.run())

if __name__ == "__main__":
    main()
