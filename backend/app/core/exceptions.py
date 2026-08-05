"""统一业务异常与全局异常处理."""
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class BizError(Exception):
    """业务异常, 携带 HTTP 状态码与错误码."""

    def __init__(self, message: str, code: str = "BIZ_ERROR", http_code: int = status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.code = code
        self.http_code = http_code
        super().__init__(message)


class NotFoundError(BizError):
    def __init__(self, message: str):
        super().__init__(message, code="NOT_FOUND", http_code=status.HTTP_404_NOT_FOUND)


class AuthError(BizError):
    def __init__(self, message: str = "认证失败"):
        super().__init__(message, code="UNAUTHORIZED", http_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(BizError):
    def __init__(self, message: str = "无权限执行此操作"):
        super().__init__(message, code="FORBIDDEN", http_code=status.HTTP_403_FORBIDDEN)


def _error_body(exc: BizError) -> dict[str, Any]:
    return {"code": exc.code, "message": exc.message, "detail": None}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def biz_error_handler(request: Request, exc: BizError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_code, content=_error_body(exc))

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(BizError("服务器内部错误", code="INTERNAL_ERROR")),
        )
