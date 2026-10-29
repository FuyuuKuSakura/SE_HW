"""/items 与 /products 路由：市场列表、同款聚合、发布、编辑、上下架。"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from ..db import get_db
from ..errors import ApiError, ok
from ..schemas import ItemCreate, ItemPatch, StatusPatch
from ..search import score_item
from ..security import current_uid
from ..serializers import item_out, offer_brief, review_out

router = APIRouter(tags=["商品"])

CST = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def _get_item_row(conn, item_id: str):
    return conn.execute(
        """SELECT i.*, u.name AS seller_name
           FROM items i JOIN users u ON u.id = i.seller_id
           WHERE i.id = ?""",
        (item_id,),
    ).fetchone()


def _next_item_id(conn) -> str:
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(id, 2) AS INTEGER)) FROM items WHERE id LIKE 'i%'"
    ).fetchone()
    return f"i{(row[0] or 0) + 1}"


# --------------------------------------------------------------------- 列表
@router.get("", summary="买家市场列表（支持同款聚合与近似搜索）")
def list_items(
    q: str = "",
    match: str = Query("fuzzy", pattern="^(fuzzy|exact)$"),
    min_score: float = Query(0.34, alias="minScore", ge=0, le=1),
    category: str | None = None,
    mode: str | None = Query(None, pattern="^(sale|donate)$"),
    sort: str = Query("latest", pattern="^(latest|price_asc|price_desc|relevance)$"),
    group_by: str = Query("product", alias="groupBy", pattern="^(product|offer)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, alias="pageSize", ge=1, le=50),
    uid: str = Depends(current_uid),
):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT i.*, u.name AS seller_name
               FROM items i JOIN users u ON u.id = i.seller_id
               WHERE i.status = 'on_sale' AND i.seller_id <> ?""",
            (uid,),
        ).fetchall()
        items = [item_out(r) for r in rows]

    if category and category != "全部":
        items = [it for it in items if it["category"] == category]
    if mode:
        items = [it for it in items if it["mode"] == mode]

    keyword = q.strip()
    if keyword:
        kept = []
        for it in items:
            score, match_type = score_item(keyword, it)
            if match == "exact" and match_type != "exact":
                continue
            if match == "fuzzy" and score < min_score:
                continue
            kept.append({**it, "score": score, "matchType": match_type})
        items = kept
        # 有搜索词且没指定排序时，按相关度排；指定了价格排序则以价格为准
        if sort == "latest":
            sort = "relevance"

    if sort == "relevance" and not keyword:
        sort = "latest"

    if group_by == "offer":
        items = _sort_offers(items, sort)
        total = len(items)
        chunk = items[(page - 1) * page_size: page * page_size]
        return ok({"list": chunk, "page": page, "pageSize": page_size,
                   "total": total, "hasMore": page * page_size < total})

    groups = _group_products(items)
    groups = _sort_groups(groups, sort)
    total = len(groups)
    chunk = groups[(page - 1) * page_size: page * page_size]
    return ok({"list": chunk, "page": page, "pageSize": page_size,
               "total": total, "hasMore": page * page_size < total})


def _sort_offers(items: list[dict], sort: str) -> list[dict]:
    if sort == "price_asc":
        return sorted(items, key=lambda x: (x["price"], x["createdAt"]))
    if sort == "price_desc":
        return sorted(items, key=lambda x: (-x["price"], x["createdAt"]))
    if sort == "relevance":
        return sorted(items, key=lambda x: (-x.get("score", 0), x["createdAt"]))
    return sorted(items, key=lambda x: x["createdAt"], reverse=True)


def _group_products(items: list[dict]) -> list[dict]:
    """按 (productId, mode) 聚合。捐赠和出售分开，避免 0 元把出售价拉平。"""
    buckets: dict[tuple, list[dict]] = {}
    for it in items:
        buckets.setdefault((it["productId"], it["mode"]), []).append(it)

    groups = []
    for (pid, mode), offers in buckets.items():
        on_sale = [o for o in offers if o["status"] == "on_sale"]
        newest = max(o["createdAt"] for o in offers)
        groups.append({
            "productId": pid,
            "title": sorted(offers, key=lambda o: len(o["title"]))[0]["title"],
            "category": offers[0]["category"],
            "mode": mode,
            "img": offers[0]["img"],
            "minPrice": min((o["price"] for o in on_sale), default=None),
            "sellerCount": len({o["sellerId"] for o in on_sale}),
            "offerCount": len(offers),
            "score": max((o.get("score", 0) for o in offers), default=None),
            "matchType": next((o["matchType"] for o in offers if o.get("matchType")), None),
            "createdAt": newest,
            "offers": [offer_brief({**o, "seller_id": o["sellerId"], "seller_name": o["sellerName"],
                                    "created_at": o["createdAt"]}) for o in
                       sorted(offers, key=lambda o: (o["status"] != "on_sale", o["price"]))],
        })
    return groups


def _sort_groups(groups: list[dict], sort: str) -> list[dict]:
    if sort == "price_asc":
        return sorted(groups, key=lambda g: (g["minPrice"] if g["minPrice"] is not None else 10 ** 9))
    if sort == "price_desc":
        return sorted(groups, key=lambda g: -(g["minPrice"] or 0))
    if sort == "relevance":
        return sorted(groups, key=lambda g: (-(g["score"] or 0), g["createdAt"]))
    return sorted(groups, key=lambda g: g["createdAt"], reverse=True)


# --------------------------------------------------------------------- 我的商品
@router.get("/mine", summary="我发布的挂单（卖家工作台）")
def my_items(
    status: str | None = Query(None, pattern="^(on_sale|reserved|sold|off_shelf)$"),
    mode: str | None = Query(None, pattern="^(sale|donate)$"),
    uid: str = Depends(current_uid),
):
    sql = """SELECT i.*, u.name AS seller_name FROM items i JOIN users u ON u.id = i.seller_id
             WHERE i.seller_id = ?"""
    params: list = [uid]
    if status:
        sql += " AND i.status = ?"
        params.append(status)
    if mode:
        sql += " AND i.mode = ?"
        params.append(mode)
    sql += " ORDER BY i.created_at DESC"
    with get_db() as conn:
        return ok([item_out(r) for r in conn.execute(sql, params).fetchall()])


# --------------------------------------------------------------------- 详情
@router.get("/{item_id}", summary="挂单详情")
def get_item(item_id: str, uid: str = Depends(current_uid)):
    with get_db() as conn:
        row = _get_item_row(conn, item_id)
        if not row:
            raise ApiError(404, 40400, "挂单不存在")

        seller = conn.execute(
            """SELECT u.*, (SELECT COUNT(*) FROM items i
                            WHERE i.seller_id = u.id AND i.status = 'on_sale') AS on_sale_count
               FROM users u WHERE u.id = ?""",
            (row["seller_id"],),
        ).fetchone()
        review_count = conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE item_id = ?", (item_id,)
        ).fetchone()[0]
        comment_count = conn.execute(
            "SELECT COUNT(*) FROM comments WHERE item_id = ? AND parent_id IS NULL", (item_id,)
        ).fetchone()[0]
        latest = conn.execute(
            """SELECT status FROM orders WHERE item_id = ?
               AND status <> 'cancelled' ORDER BY created_at DESC LIMIT 1""",
            (item_id,),
        ).fetchone()
        same = conn.execute(
            """SELECT i.*, u.name AS seller_name FROM items i JOIN users u ON u.id = i.seller_id
               WHERE i.product_id = ? AND i.mode = ? AND i.id <> ?
               ORDER BY CASE i.status WHEN 'on_sale' THEN 0 WHEN 'reserved' THEN 1 ELSE 2 END,
                        i.price ASC""",
            (row["product_id"], row["mode"], item_id),
        ).fetchall()

    data = item_out(row)
    data["seller"] = {
        "id": seller["id"], "name": seller["name"], "credit": seller["credit"],
        "campus": seller["campus"], "onSaleCount": seller["on_sale_count"],
    }
    data["reviewCount"] = review_count
    data["commentCount"] = comment_count
    data["latestOrderStatus"] = latest["status"] if latest else None
    data["sameProductOffers"] = [offer_brief(r) for r in same]
    return ok(data)


# --------------------------------------------------------------------- 发布
@router.post("", summary="发布挂单")
def create_item(body: ItemCreate, uid: str = Depends(current_uid)):
    price = body.price or 0
    if body.mode == "donate":
        price = 0
    elif price <= 0:
        raise ApiError(400, 40002, "出售商品的 price 必须大于 0；捐赠请设置 mode=donate")

    with get_db() as conn:
        with conn:
            pid = body.product_id
            if pid:
                exists = conn.execute(
                    "SELECT 1 FROM products WHERE product_id = ?", (pid,)
                ).fetchone()
                if not exists:
                    raise ApiError(400, 40002, f"productId {pid} 不存在，不传该字段将自动新建同款")
            else:
                pid = "p_" + uuid.uuid4().hex[:8]
                conn.execute(
                    "INSERT INTO products(product_id, title, category, mode, created_at) VALUES (?,?,?,?,?)",
                    (pid, body.title, body.category, body.mode, _now()),
                )

            item_id = _next_item_id(conn)
            conn.execute(
                """INSERT INTO items(id, product_id, seller_id, title, price, original_price, mode,
                                     category, condition, img, description, location, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'on_sale',?)""",
                (item_id, pid, uid, body.title, price, body.original_price, body.mode,
                 body.category, body.condition, body.img, body.desc, body.location, _now()),
            )
            row = _get_item_row(conn, item_id)

    return ok(item_out(row))


# --------------------------------------------------------------------- 编辑
@router.patch("/{item_id}", summary="编辑挂单（仅商品归属人）")
def patch_item(item_id: str, body: ItemPatch, uid: str = Depends(current_uid)):
    with get_db() as conn:
        with conn:
            row = _get_item_row(conn, item_id)
            if not row:
                raise ApiError(404, 40400, "挂单不存在")
            if row["seller_id"] != uid:
                raise ApiError(403, 40300, "只能编辑自己发布的挂单")
            if row["status"] in ("reserved", "sold"):
                raise ApiError(409, 40900, f"当前状态 {row['status']} 不允许编辑")

            fields = body.model_dump(exclude_unset=True)
            if not fields:
                raise ApiError(400, 40002, "没有需要修改的字段")

            mode = fields.get("mode", row["mode"])
            price = fields.get("price", row["price"])
            if mode == "donate":
                if price and price > 0:
                    raise ApiError(400, 40002, "改为捐赠时价格必须为 0 或省略")
                fields["price"] = 0
            elif price <= 0:
                raise ApiError(400, 40002, "出售商品的价格必须大于 0")

            column_map = {"original_price": "original_price", "desc": "description"}
            sets, params = [], []
            for key, value in fields.items():
                sets.append(f"{column_map.get(key, key)} = ?")
                params.append(value)
            params.append(item_id)
            conn.execute(f"UPDATE items SET {', '.join(sets)} WHERE id = ?", params)

            updated = _get_item_row(conn, item_id)
    return ok(item_out(updated))


@router.patch("/{item_id}/status", summary="上架 / 下架")
def patch_status(item_id: str, body: StatusPatch, uid: str = Depends(current_uid)):
    with get_db() as conn:
        with conn:
            row = _get_item_row(conn, item_id)
            if not row:
                raise ApiError(404, 40400, "挂单不存在")
            if row["seller_id"] != uid:
                raise ApiError(403, 40300, "只能操作自己发布的挂单")
            if row["status"] in ("reserved", "sold"):
                raise ApiError(409, 40900, f"当前状态 {row['status']} 不允许上下架")
            conn.execute("UPDATE items SET status = ? WHERE id = ?", (body.status, item_id))
            updated = _get_item_row(conn, item_id)
    return ok(item_out(updated))


# --------------------------------------------------------------------- 交易评价
@router.get("/{item_id}/reviews", summary="该挂单的交易评价")
def item_reviews(
    item_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(12, alias="pageSize", ge=1, le=50),
    uid: str = Depends(current_uid),
):
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone():
            raise ApiError(404, 40400, "挂单不存在")
        total = conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE item_id = ?", (item_id,)
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT r.*, u.name AS buyer_name, u.avatar AS buyer_avatar
               FROM reviews r JOIN users u ON u.id = r.buyer_id
               WHERE r.item_id = ?
               ORDER BY r.created_at DESC LIMIT ? OFFSET ?""",
            (item_id, page_size, (page - 1) * page_size),
        ).fetchall()

        tag_map: dict[str, list[str]] = {}
        if rows:
            marks = ",".join("?" * len(rows))
            for t in conn.execute(
                f"SELECT review_id, tag FROM review_tags WHERE review_id IN ({marks}) ORDER BY tag",
                [r["id"] for r in rows],
            ).fetchall():
                tag_map.setdefault(t["review_id"], []).append(t["tag"])

    return ok({
        "list": [review_out(r, tag_map.get(r["id"], [])) for r in rows],
        "page": page, "pageSize": page_size, "total": total,
        "hasMore": page * page_size < total,
    })
