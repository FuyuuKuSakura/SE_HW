"""统一响应包与业务异常。

响应约定（与 api.md 一致）：
  成功  {"code": 0, "message": "ok", "data": ...}
  失败  {"code": 40901, "message": "...", "data": null}

错误码表（见 api.md 第 7 节）：
  40002 参数校验失败
  40300 无权访问 / 不能对自己的挂单下单
  40301 无权操作该资源（回复、删除）
  40900 当前状态不允许该操作
  40901 挂单不可下单（非在售）
  40902 重复提交（重复回复 / 三级评论）
  40903 捐赠订单不支持快递
  40100 未登录
  40101 token 无效
  40400 资源不存在
"""
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, http_status: int, code: int, message: str, data: Any = None):
        self.http_status = http_status
        self.code = code
        self.message = message
        self.data = data


def ok(data: Any = None) -> dict:
    return {"code": 0, "message": "ok", "data": data}


def register_error_handlers(app) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "data": exc.data},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        msg = f"{loc}: {first.get('msg', '参数不合法')}" if loc else str(first.get("msg", "参数不合法"))
        return JSONResponse(
            status_code=400,
            content={"code": 40002, "message": msg, "data": None},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code * 100, "message": str(exc.detail), "data": None},
        )
