"""/items/{id}/comments 与 /comments/{id} 路由。

业务规则（api.md 5.3）：
- 内容 1–200 字，去空白后不能为空
- 任意登录用户可发一级评论
- 只有该挂单的卖家能回复，且每条一级评论只能回一次
- 不允许第三层（数据库触发器兜底）
"""
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from ..db import get_db
from ..errors import ApiError, ok
from ..schemas import CommentCreate
from ..security import current_uid
from ..serializers import comment_out

items_router = APIRouter(tags=["评论"])
comments_router = APIRouter(tags=["评论"])

CST = timezone(timedelta(hours=8))
SELECT = """SELECT c.*, u.name AS user_name, u.avatar AS user_avatar
            FROM comments c JOIN users u ON u.id = c.user_id"""


def _now() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


@items_router.get("/{item_id}/comments", summary="一级评论分页列表（内嵌一条卖家回复）")
def list_comments(
    item_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(12, alias="pageSize", ge=1, le=50),
    uid: str = Depends(current_uid),
):
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone():
            raise ApiError(404, 40400, "挂单不存在")

        total = conn.execute(
            "SELECT COUNT(*) FROM comments WHERE item_id = ? AND parent_id IS NULL", (item_id,)
        ).fetchone()[0]
        roots = conn.execute(
            SELECT + """ WHERE c.item_id = ? AND c.parent_id IS NULL
                        ORDER BY c.created_at DESC LIMIT ? OFFSET ?""",
            (item_id, page_size, (page - 1) * page_size),
        ).fetchall()

        out = []
        for r in roots:
            node = comment_out(r)
            replies = conn.execute(
                SELECT + " WHERE c.parent_id = ? ORDER BY c.created_at ASC", (r["id"],)
            ).fetchall()
            node["replies"] = [comment_out(x) for x in replies]
            out.append(node)

    return ok({"list": out, "page": page, "pageSize": page_size,
               "total": total, "hasMore": page * page_size < total})


@items_router.post("/{item_id}/comments", summary="发布评论或卖家回复")
def create_comment(item_id: str, body: CommentCreate, uid: str = Depends(current_uid)):
    content = (body.content or "").strip()
    if not 1 <= len(content) <= 200:
        raise ApiError(400, 40002, "评论内容需为 1–200 字")

    with get_db() as conn:
        with conn:
            item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if not item:
                raise ApiError(404, 40400, "挂单不存在")

            if body.parent_id:
                parent = conn.execute(
                    "SELECT * FROM comments WHERE id = ?", (body.parent_id,)
                ).fetchone()
                if not parent or parent["item_id"] != item_id:
                    raise ApiError(404, 40400, "被回复的评论不存在或不属于该挂单")
                if parent["parent_id"]:
                    raise ApiError(409, 40902, "评论最多两层，不能回复一条回复")
                if item["seller_id"] != uid:
                    raise ApiError(403, 40301, "只有该挂单的卖家可以回复评论")
                if conn.execute(
                    "SELECT 1 FROM comments WHERE parent_id = ?", (parent["id"],)
                ).fetchone():
                    raise ApiError(409, 40902, "该评论已有一条卖家回复，不能重复回复")

            comment_id = "c" + uuid.uuid4().hex[:8]
            try:
                conn.execute(
                    """INSERT INTO comments(id, item_id, user_id, parent_id, content, created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (comment_id, item_id, uid, body.parent_id, content, _now()),
                )
            except sqlite3.IntegrityError as exc:
                # 唯一索引 / 触发器兜底：并发下也可能撞到这两条约束
                raise ApiError(409, 40902, f"评论写入被拒绝：{exc}") from exc

            row = conn.execute(SELECT + " WHERE c.id = ?", (comment_id,)).fetchone()
            return ok(comment_out(row))


@comments_router.delete("/{comment_id}", summary="删除自己的评论或回复")
def delete_comment(comment_id: str, uid: str = Depends(current_uid)):
    with get_db() as conn:
        with conn:
            row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
            if not row:
                raise ApiError(404, 40400, "评论不存在")
            if row["user_id"] != uid:
                raise ApiError(403, 40301, "只能删除自己发布的评论")
            # 一级评论删除时，其卖家回复由外键 ON DELETE CASCADE 级联删除
            conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    return ok({"deleted": True})
