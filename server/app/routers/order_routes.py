"""/orders 路由：下单、状态流转、评价。

核心是三个事务：下单锁货、完成收尾、取消放货。
每个都是"两张表必须同时改"，任何一步失败都要整体回滚。
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from ..db import get_db
from ..errors import ApiError, ok
from ..schemas import OrderCreate, ReviewCreate
from ..security import current_uid
from ..serializers import order_out

router = APIRouter(tags=["订单"])

CST = timezone(timedelta(hours=8))

ORDER_SELECT = """
SELECT o.*,
       b.name AS buyer_name,  b.avatar AS buyer_avatar,
       s.name AS seller_name, s.avatar AS seller_avatar,
       r.id AS review_id, r.stars AS review_stars, r.content AS review_content,
       r.created_at AS review_created_at
FROM orders o
JOIN users b ON b.id = o.buyer_id
JOIN users s ON s.id = o.seller_id
LEFT JOIN reviews r ON r.order_id = o.id
"""


def _now() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def _next_order_id(conn) -> str:
    prefix = "ZZ" + datetime.now(CST).strftime("%Y%m%d")
    for _ in range(20):
        n = conn.execute("SELECT COUNT(*) FROM orders WHERE id LIKE ?", (prefix + "%",)).fetchone()[0]
        oid = f"{prefix}{n + 1:03d}"
        if not conn.execute("SELECT 1 FROM orders WHERE id = ?", (oid,)).fetchone():
            return oid
    return prefix + uuid.uuid4().hex[:4].upper()


def _tags_of(conn, review_id: str | None) -> list[str]:
    if not review_id:
        return []
    rows = conn.execute(
        "SELECT tag FROM review_tags WHERE review_id = ? ORDER BY tag", (review_id,)
    ).fetchall()
    return [r["tag"] for r in rows]


def _load(conn, order_id: str) -> dict:
    row = conn.execute(ORDER_SELECT + " WHERE o.id = ?", (order_id,)).fetchone()
    if not row:
        raise ApiError(404, 40400, "订单不存在")
    data = order_out(row)
    if data["review"]:
        data["review"]["tags"] = _tags_of(conn, row["review_id"])
    return data


# --------------------------------------------------------------------- 下单
@router.post("", summary="下单 / 申请领取捐赠")
def create_order(body: OrderCreate, uid: str = Depends(current_uid)):
    with get_db() as conn:
        with conn:  # 事务：锁货 + 建单必须同时成功
            item = conn.execute("SELECT * FROM items WHERE id = ?", (body.item_id,)).fetchone()
            if not item:
                raise ApiError(404, 40400, "挂单不存在")
            if item["seller_id"] == uid:
                raise ApiError(403, 40300, "不能对自己的挂单下单")
            if item["mode"] == "donate" and body.trade_method != "自提":
                raise ApiError(409, 40903, "捐赠商品只能选择自提")
            if item["status"] != "on_sale":
                raise ApiError(409, 40901, f"挂单当前状态为 {item['status']}，不可下单")

            # 关键：把状态判断放进 WHERE，靠影响行数裁决谁抢到，避免"先查再改"的竞态
            cur = conn.execute(
                "UPDATE items SET status = 'reserved' WHERE id = ? AND status = 'on_sale'",
                (body.item_id,),
            )
            if cur.rowcount == 0:
                raise ApiError(409, 40901, "手慢了，这件刚被别人预订")

            price = 0 if item["mode"] == "donate" else item["price"]
            order_id = _next_order_id(conn)
            conn.execute(
                """INSERT INTO orders(id, item_id, product_id, mode, buyer_id, seller_id, price,
                                      title_snap, img_snap, trade_method, message, status,
                                      reviewed, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',0,?)""",
                (order_id, item["id"], item["product_id"], item["mode"], uid, item["seller_id"],
                 price, item["title"], item["img"], body.trade_method, body.message or "", _now()),
            )
            return ok(_load(conn, order_id))


# --------------------------------------------------------------------- 列表 / 详情
@router.get("", summary="我的订单（按角色）")
def list_orders(
    role: str = Query(..., pattern="^(buyer|seller)$"),
    status: str | None = Query(None, pattern="^(pending|trading|completed|cancelled)$"),
    mode: str | None = Query(None, pattern="^(sale|donate)$"),
    uid: str = Depends(current_uid),
):
    sql = ORDER_SELECT + (" WHERE o.buyer_id = ?" if role == "buyer" else " WHERE o.seller_id = ?")
    params: list = [uid]
    if status:
        sql += " AND o.status = ?"
        params.append(status)
    if mode:
        sql += " AND o.mode = ?"
        params.append(mode)
    sql += " ORDER BY o.created_at DESC"

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        out = []
        for row in rows:
            data = order_out(row)
            if data["review"]:
                data["review"]["tags"] = _tags_of(conn, row["review_id"])
            out.append(data)
    return ok(out)


@router.get("/{order_id}", summary="订单详情")
def get_order(order_id: str, uid: str = Depends(current_uid)):
    with get_db() as conn:
        row = conn.execute(ORDER_SELECT + " WHERE o.id = ?", (order_id,)).fetchone()
        if not row:
            raise ApiError(404, 40400, "订单不存在")
        if uid not in (row["buyer_id"], row["seller_id"]):
            raise ApiError(403, 40300, "只有交易双方可以查看该订单")
        return ok(_load(conn, order_id))


# --------------------------------------------------------------------- 状态流转
@router.post("/{order_id}/confirm", summary="卖家确认交易 pending → trading")
def confirm_order(order_id: str, uid: str = Depends(current_uid)):
    with get_db() as conn:
        with conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if not row:
                raise ApiError(404, 40400, "订单不存在")
            if row["seller_id"] != uid:
                raise ApiError(403, 40300, "只有卖家可以确认交易")
            if row["status"] != "pending":
                raise ApiError(409, 40900, f"订单当前状态为 {row['status']}，只有待确认的订单可以确认")

            cur = conn.execute(
                "UPDATE orders SET status='trading', confirmed_at=? WHERE id=? AND status='pending'",
                (_now(), order_id),
            )
            if cur.rowcount == 0:
                raise ApiError(409, 40900, "订单状态已被改变，请刷新后重试")
            return ok(_load(conn, order_id))


@router.post("/{order_id}/complete", summary="完成交易 trading → completed，挂单变 sold")
def complete_order(order_id: str, uid: str = Depends(current_uid)):
    with get_db() as conn:
        with conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if not row:
                raise ApiError(404, 40400, "订单不存在")
            if uid not in (row["buyer_id"], row["seller_id"]):
                raise ApiError(403, 40300, "只有交易双方可以完成订单")
            if row["status"] != "trading":
                raise ApiError(409, 40900, f"订单当前状态为 {row['status']}，只有交易中的订单可以完成")

            cur = conn.execute(
                "UPDATE orders SET status='completed', completed_at=? WHERE id=? AND status='trading'",
                (_now(), order_id),
            )
            if cur.rowcount == 0:
                raise ApiError(409, 40900, "订单状态已被改变，请刷新后重试")
            conn.execute("UPDATE items SET status='sold' WHERE id=?", (row["item_id"],))
            return ok(_load(conn, order_id))


@router.post("/{order_id}/cancel", summary="取消订单 pending → cancelled，挂单回到 on_sale")
def cancel_order(order_id: str, uid: str = Depends(current_uid)):
    with get_db() as conn:
        with conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if not row:
                raise ApiError(404, 40400, "订单不存在")
            if row["buyer_id"] != uid:
                raise ApiError(403, 40300, "只有买家可以取消订单")
            if row["status"] != "pending":
                raise ApiError(409, 40900, f"订单当前状态为 {row['status']}，只有待确认的订单可以取消")

            cur = conn.execute(
                "UPDATE orders SET status='cancelled', cancelled_at=? WHERE id=? AND status='pending'",
                (_now(), order_id),
            )
            if cur.rowcount == 0:
                raise ApiError(409, 40900, "订单状态已被改变，请刷新后重试")
            conn.execute(
                "UPDATE items SET status='on_sale' WHERE id=? AND status='reserved'",
                (row["item_id"],),
            )
            return ok(_load(conn, order_id))


# --------------------------------------------------------------------- 评价
@router.post("/{order_id}/review", summary="买家评价（每单一次）")
def review_order(order_id: str, body: ReviewCreate, uid: str = Depends(current_uid)):
    with get_db() as conn:
        with conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if not row:
                raise ApiError(404, 40400, "订单不存在")
            if row["buyer_id"] != uid:
                raise ApiError(403, 40300, "只有买家可以评价")
            if row["status"] != "completed":
                raise ApiError(409, 40900, "交易完成后才能评价")
            if row["reviewed"]:
                raise ApiError(409, 40900, "该订单已评价过，不能重复评价")

            review_id = "r" + uuid.uuid4().hex[:8]
            conn.execute(
                """INSERT INTO reviews(id, order_id, item_id, buyer_id, seller_id, stars, content, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (review_id, order_id, row["item_id"], uid, row["seller_id"],
                 body.stars, body.text or "", _now()),
            )
            for tag in dict.fromkeys(body.tags):
                conn.execute("INSERT INTO review_tags(review_id, tag) VALUES (?,?)", (review_id, tag))
            conn.execute("UPDATE orders SET reviewed = 1 WHERE id = ?", (order_id,))
            return ok(_load(conn, order_id))
