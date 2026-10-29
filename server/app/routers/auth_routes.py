"""/auth 路由。

演示环境按 api.md 的约定不校验密码，但账号要真的存在——
因为「买家和卖家是两个不同用户」是这个系统的核心，
用两个浏览器窗口分别登录 me 和 u2，才能演示真实的一买一卖。
"""
from fastapi import APIRouter, Depends

from ..db import get_db
from ..errors import ApiError, ok
from ..schemas import LoginIn
from ..security import DEFAULT_ACCOUNT, current_uid, make_token
from ..serializers import user_out

router = APIRouter(tags=["认证"])


@router.post("/login", summary="登录（演示环境不校验密码）")
def login(body: LoginIn):
    account = (body.account or "").strip()
    if account in ("", DEFAULT_ACCOUNT):
        account = "me"

    with get_db() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE id = ? OR name = ?", (account, account)
        ).fetchone()
        if not user:
            raise ApiError(404, 40400, f"账号 {account} 不存在，可用账号见 GET /api/v1/auth/accounts")

    return ok({"token": make_token(user["id"]), "user": user_out(user)})


@router.get("/me", summary="当前登录用户")
def me(uid: str = Depends(current_uid)):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not user:
        raise ApiError(404, 40400, "用户不存在")
    return ok(user_out(user))


@router.get("/accounts", summary="演示账号列表（方便开两个窗口分别登录）")
def accounts():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, campus FROM users ORDER BY id"
        ).fetchall()
    return ok([{"account": r["id"], "name": r["name"], "campus": r["campus"],
                "note": "密码随意，演示环境不校验"} for r in rows])
