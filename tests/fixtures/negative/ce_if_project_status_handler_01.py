"""IF-PROJECT-STATUS-01: project status routes (COUNTEREXAMPLE).

负样本：将三个 IF-PROJECT-STATUS-01 token 中两个移除，破坏 RED 归因。
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse


async def project_status(request: Request) -> JSONResponse:
    """负样本：去除 IF-token。"""
    raise NotImplementedError("missing contract anchor")


async def checkpoint_detail(request: Request) -> JSONResponse:
    """保留 IF-token。"""
    raise NotImplementedError("IF-PROJECT-STATUS-01")


async def checkpoint_action(request: Request) -> JSONResponse:
    """负样本：去除 IF-token。"""
    raise NotImplementedError("missing contract anchor")
