"""专专 · 校园二手流转平台 —— 后端入口。

启动：
    cd server
    .venv\\Scripts\\activate          (Windows)
    uvicorn main:app --reload --port 8000

接口文档： http://127.0.0.1:8000/docs
前端页面： http://127.0.0.1:8000/app   （把仓库里的 index.html 放回来即可）
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.db import BASE_DIR, is_empty
from app.errors import register_error_handlers
from app.routers import (
    auth_routes,
    comment_routes,
    item_routes,
    meta_routes,
    order_routes,
    seller_routes,
)

REPO_DIR = os.path.dirname(BASE_DIR)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 第一次启动时自动建表 + 灌种子数据，组员 clone 下来不需要额外操作
    if is_empty():
        import seed
        seed.build()
        print("[专专] 数据库为空，已自动建表并灌入种子数据（41 商品 / 13 订单）")
    yield


DESCRIPTION = """
校园二手物品流转平台后端，按 `api.md` v2 契约实现。

* 认证方式：`Authorization: Bearer <token>`，token 从 `POST /api/v1/auth/login` 获取
* 统一响应：`{"code": 0, "message": "ok", "data": ...}`
* 错误响应：`{"code": 40901, "message": "...", "data": null}`

演示账号：`naiwa`（奶蛙）、`u2`（陈默）、`u3`（周雨）、`u4`、`u5`、`u6`，密码随意。
开两个浏览器窗口分别登录买家和卖家，就能演示真实的一买一卖。
"""

app = FastAPI(
    title="专专 · 校园二手流转平台 API",
    version="2.0.0",
    description=DESCRIPTION,
    lifespan=lifespan,
)

# 前端如果用 file:// 打开，或者跑在 5500 端口的静态服务上，都必须放开跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

API = "/api/v1"
app.include_router(auth_routes.router, prefix=f"{API}/auth")
app.include_router(item_routes.router, prefix=f"{API}/items")
app.include_router(comment_routes.items_router, prefix=f"{API}/items")
app.include_router(comment_routes.comments_router, prefix=f"{API}/comments")
app.include_router(order_routes.router, prefix=f"{API}/orders")
app.include_router(seller_routes.router, prefix=API)
app.include_router(meta_routes.router, prefix=API)


@app.get("/", include_in_schema=False)
def index():
    return JSONResponse({
        "service": "专专 · 校园二手流转平台 API",
        "version": "2.0.0",
        "docs": "/docs",
        "frontend": "/app",
        "api_base": API,
    })


@app.get("/app", include_in_schema=False)
def frontend():
    """把仓库根目录的 index.html 挂上来，前后端同源，省掉跨域麻烦。"""
    path = os.path.join(REPO_DIR, "index.html")
    if not os.path.exists(path):
        return JSONResponse(
            {"code": 40400, "message": "没有找到 index.html，把它复制到 server 的上一级目录再试"},
            status_code=404,
        )
    return FileResponse(path, media_type="text/html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
