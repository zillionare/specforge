"""IF-PROJECT-STATUS-01: Project Status HTTP handlers公开骨架。"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response


async def project_status(request: Request) -> Response:
    """读取同一Project的状态和ATDD投影。"""
    raise NotImplementedError("IF-PROJECT-STATUS-01")


async def checkpoint_detail(request: Request) -> Response:
    """读取current或historical checkpoint详情与evidence。"""
    raise NotImplementedError("IF-PROJECT-STATUS-01")
