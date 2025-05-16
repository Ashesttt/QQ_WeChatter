from .github import router as github_router
from .wechat import router as wechat_router
from .upload import router as upload_router

__all__ = ["github_router", "wechat_router", "upload_router"]
