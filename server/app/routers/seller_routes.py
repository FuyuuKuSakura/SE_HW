"""/sellers/{id}/* 与 /seller/stats 路由：卖家主页与工作台统计。

所有统计口径都从这里出发查 v_seller_stats 视图，
保证「商品详情 / 卖家主页 / 工作台」三个入口算出来的好评率、成交额一致。
"""
from fastapi import APIRouter, Depends, Query

from ..db import get_db
from ..errors import ApiError, ok
from ..security import current_uid
from ..serializers import item_out, review_out, user_out

router = APIRouter(tags=["卖家"])


def _stats(conn, seller_id: str):
    return conn.execute(
        "SELECT * FROM v_seller_stats WHERE seller_id = ?", (seller_id,)
    ).fetchone()


def _tags(conn, seller_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT rt.tag AS name, COUNT(*) AS count
           FROM review_tags rt JOIN reviews r ON r.id = rt.review_id
           WHERE r.seller_id = ?
           GROUP BY rt.tag ORDER BY count DESC, rt.tag""",
        (seller_id,),
    ).fetchall()
    return [{"name": r["name"], "count": r["count"]} for r in rows]


def _tags_map(conn, review_ids: list[str]) -> dict[str, list[str]]:
    if not review_ids:
        return {}
    marks = ",".join("?" * len(review_ids))
    rows = conn.execute(
        f"SELECT review_id, tag FROM review_tags WHERE review_id IN ({marks}) ORDER BY tag",
        review_ids,
    ).fetchall()
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["review_id"], []).append(r["tag"])
    return out


@router.get("/sellers/{seller_id}/profile", summary="卖家主页资料与统计")
def seller_profile(seller_id: str, uid: str = Depends(current_uid)):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (seller_id,)).fetchone()
        if not user:
            raise ApiError(404, 40400, "用户不存在")
        stat = _stats(conn, seller_id)
        tags = _tags(conn, seller_id)

    data = user_out(user)
    data.update({
        "onSale": stat["on_sale_count"],
        "soldCount": stat["sold_count"],
        "donatedCount": stat["donated_count"],
        "soldAmount": stat["sold_amount"],
        "reviewCount": stat["review_count"],
        "avgStars": stat["avg_stars"],
        "positiveRate": stat["positive_rate"],
        "tags": tags,
    })
    return ok(data)


@router.get("/sellers/{seller_id}/items", summary="卖家在售商品")
def seller_items(
    seller_id: str,
    status: str = Query("on_sale", pattern="^(on_sale|reserved|sold|off_shelf|all)$"),
    mode: str | None = Query(None, pattern="^(sale|donate)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, alias="pageSize", ge=1, le=50),
    uid: str = Depends(current_uid),
):
    sql = """SELECT i.*, u.name AS seller_name FROM items i JOIN users u ON u.id = i.seller_id
             WHERE i.seller_id = ?"""
    params: list = [seller_id]
    if status != "all":
        sql += " AND i.status = ?"
        params.append(status)
    if mode:
        sql += " AND i.mode = ?"
        params.append(mode)

    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
        sql += " ORDER BY i.created_at DESC LIMIT ? OFFSET ?"
        rows = conn.execute(sql, params + [page_size, (page - 1) * page_size]).fetchall()

    return ok({"list": [item_out(r) for r in rows], "page": page, "pageSize": page_size,
               "total": total, "hasMore": page * page_size < total})


@router.get("/sellers/{seller_id}/sold", summary="卖家已完成的交易（含捐赠）")
def seller_sold(
    seller_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(12, alias="pageSize", ge=1, le=50),
    uid: str = Depends(current_uid),
):
    base = """FROM orders o JOIN users b ON b.id = o.buyer_id
              LEFT JOIN reviews r ON r.order_id = o.id
              WHERE o.seller_id = ? AND o.status = 'completed'"""
    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) {base}", (seller_id,)).fetchone()[0]
        rows = conn.execute(
            f"""SELECT o.*, b.name AS buyer_name, b.avatar AS buyer_avatar,
                       r.id AS review_id, r.stars AS review_stars
                {base} ORDER BY o.completed_at DESC LIMIT ? OFFSET ?""",
            (seller_id, page_size, (page - 1) * page_size),
        ).fetchall()
        tag_map = _tags_map(conn, [r["review_id"] for r in rows if r["review_id"]])

    listed = []
    for r in rows:
        listed.append({
            "orderId": r["id"],
            "itemId": r["item_id"],
            "itemTitle": r["title_snap"],
            "itemImg": r["img_snap"],
            "mode": r["mode"],
            "price": r["price"],
            "completedAt": r["completed_at"],
            "buyer": {"id": r["buyer_id"], "name": r["buyer_name"], "avatar": r["buyer_avatar"]},
            "review": ({"stars": r["review_stars"], "tags": tag_map.get(r["review_id"], [])}
                       if r["review_id"] else None),
        })
    return ok({"list": listed, "page": page, "pageSize": page_size,
               "total": total, "hasMore": page * page_size < total})


@router.get("/sellers/{seller_id}/reviews", summary="卖家收到的交易评价（含标签计数）")
def seller_reviews(
    seller_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(12, alias="pageSize", ge=1, le=50),
    uid: str = Depends(current_uid),
):
    with get_db() as conn:
        stat = _stats(conn, seller_id)
        if not stat:
            raise ApiError(404, 40400, "用户不存在")
        total = conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE seller_id = ?", (seller_id,)
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT r.*, u.name AS buyer_name, u.avatar AS buyer_avatar,
                      i.title AS item_title, i.img AS item_img
               FROM reviews r
               JOIN users u ON u.id = r.buyer_id
               JOIN items i ON i.id = r.item_id
               WHERE r.seller_id = ?
               ORDER BY r.created_at DESC LIMIT ? OFFSET ?""",
            (seller_id, page_size, (page - 1) * page_size),
        ).fetchall()
        tag_map = _tags_map(conn, [r["id"] for r in rows])
        tags = _tags(conn, seller_id)

    return ok({
        "stats": {
            "reviewCount": stat["review_count"],
            "avgStars": stat["avg_stars"],
            "positiveRate": stat["positive_rate"],
        },
        "tags": tags,
        "list": [review_out(r, tag_map.get(r["id"], [])) for r in rows],
        "page": page, "pageSize": page_size, "total": total,
        "hasMore": page * page_size < total,
    })


@router.get("/seller/stats", summary="当前用户的工作台数据卡")
def my_seller_stats(uid: str = Depends(current_uid)):
    with get_db() as conn:
        stat = _stats(conn, uid)
        pending = conn.execute(
            """SELECT COUNT(*) FROM orders WHERE seller_id = ? AND status = 'pending'""",
            (uid,),
        ).fetchone()[0]
    return ok({
        "onSaleCount": stat["on_sale_count"] if stat else 0,
        "pendingOrderCount": pending,
        "completedAmount": stat["sold_amount"] if stat else 0,
        "donatedCount": stat["donated_count"] if stat else 0,
        "soldCount": stat["sold_count"] if stat else 0,
        "reviewCount": stat["review_count"] if stat else 0,
        "avgStars": stat["avg_stars"] if stat else 0,
        "positiveRate": stat["positive_rate"] if stat else 0,
    })
