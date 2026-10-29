"""认证：签发 / 校验 token。

演示环境按 api.md 的约定"不校验账号密码"，但 token 是真的：
后端从这个 token 里取当前用户，所以「不能买自己的东西」「只能编辑自己的挂单」
这些权限判断全部由服务端强制，不是前端藏个按钮。

生产环境要换成 bcrypt + JWT，只需要改本文件。
"""
import hashlib
import hmac
import os

from fastapi import Header

from .errors import ApiError

SECRET = os.environ.get("ZZ_SECRET", "zhuanzhuan-se-demo-2026").encode()
DEFAULT_ACCOUNT = "naiwa"


def make_token(user_id: str) -> str:
    sig = hmac.new(SECRET, user_id.encode(), hashlib.sha256).hexdigest()[:20]
    return f"{user_id}.{sig}"


def verify_token(token: str) -> str | None:
    if not token or "." not in token:
        return None
    user_id, _, sig = token.rpartition(".")
    expect = hmac.new(SECRET, user_id.encode(), hashlib.sha256).hexdigest()[:20]
    return user_id if hmac.compare_digest(sig, expect) else None


def current_uid(authorization: str | None = Header(default=None)) -> str:
    """FastAPI 依赖：从 Authorization: Bearer <token> 解析出当前用户 id。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, 40100, "未登录：缺少 Authorization: Bearer <token>")
    uid = verify_token(authorization.split(" ", 1)[1].strip())
    if not uid:
        raise ApiError(401, 40101, "token 无效")
    return uid
