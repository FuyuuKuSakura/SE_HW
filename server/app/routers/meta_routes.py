"""/categories、/products/{id}、/bootstrap 路由。

/bootstrap 是给前端「内存缓存」模式用的扩展接口：
一次拿到当前用户的完整数据快照，前端保留 DB 对象、只把 loadDB/save 换成它，
13 处读逻辑一行都不用改（见 README「前端接入」）。
"""
from fastapi import APIRouter, Depends

from ..db import get_db
from ..errors import ApiError, ok
from ..security import current_uid
from ..serializers import comment_out, item_out, offer_brief, order_out, review_out, user_out

router = APIRouter(tags=["元数据"])

CATEGORIES = ["数码", "家电", "家具", "图书", "服饰", "运动", "其他"]
CONDITIONS = ["99新", "95新", "9成新", "8成新", "7成新"]
MODES = [{"key": "sale", "label": "出售"}, {"key": "donate", "label": "捐赠"}]


def _meta() -> dict:
    return {"categories": CATEGORIES, "conditions": CONDITIONS, "modes": MODES}


@router.get("/categories", summary="分类 / 成色 / 流转方式枚举")
def categories():
    return ok(_meta())


@router.get("/products/{product_id}", summary="同款商品详情与全部卖家挂单")
def product_detail(product_id: str, uid: str = Depends(current_uid)):
    with get_db() as conn:
        product = conn.execute(
            "SELECT * FROM products WHERE product_id = ?", (product_id,)
        ).fetchone()
        if not product:
            raise ApiError(404, 40400, "同款商品不存在")
        rows = conn.execute(
            """SELECT i.*, u.name AS seller_name FROM items i JOIN users u ON u.id = i.seller_id
               WHERE i.product_id = ?
               ORDER BY CASE i.status WHEN 'on_sale' THEN 0 WHEN 'reserved' THEN 1 ELSE 2 END,
                        i.price ASC""",
            (product_id,),
        ).fetchall()

    offers = [offer_brief(r) for r in rows]
    on_sale = [r for r in rows if r["status"] == "on_sale"]
    return ok({
        "productId": product["product_id"],
        "title": product["title"],
        "category": product["category"],
        "mode": product["mode"],
        "offers": offers,
        "minPrice": min((r["price"] for r in on_sale), default=None),
        "sellerCount": len({r["seller_id"] for r in on_sale}),
    })


@router.get("/bootstrap", summary="当前用户的全量数据快照（前端内存缓存用）")
def bootstrap(uid: str = Depends(current_uid)):
    with get_db() as conn:
        me = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not me:
            raise ApiError(404, 40400, "用户不存在")

        users = [user_out(r) for r in conn.execute("SELECT * FROM users ORDER BY id")]
        items = [item_out(r) for r in conn.execute(
            """SELECT i.*, u.name AS seller_name FROM items i JOIN users u ON u.id = i.seller_id
               ORDER BY i.created_at DESC""")]
        orders = [order_out(r) for r in conn.execute(
            """SELECT o.*, b.name AS buyer_name, b.avatar AS buyer_avatar,
                      s.name AS seller_name, s.avatar AS seller_avatar,
                      r.id AS review_id, r.stars AS review_stars, r.content AS review_content,
                      r.created_at AS review_created_at
               FROM orders o
               JOIN users b ON b.id = o.buyer_id
               JOIN users s ON s.id = o.seller_id
               LEFT JOIN reviews r ON r.order_id = o.id
               WHERE o.buyer_id = ? OR o.seller_id = ?
               ORDER BY o.created_at DESC""", (uid, uid))]
        comments = [comment_out(r) for r in conn.execute(
            """SELECT c.*, u.name AS user_name, u.avatar AS user_avatar
               FROM comments c JOIN users u ON u.id = c.user_id
               ORDER BY c.created_at ASC""")]
        reviews = [review_out(r) for r in conn.execute(
            """SELECT r.*, u.name AS buyer_name, u.avatar AS buyer_avatar,
                      i.title AS item_title, i.img AS item_img
               FROM reviews r JOIN users u ON u.id = r.buyer_id
               JOIN items i ON i.id = r.item_id
               ORDER BY r.created_at DESC""")]
        tags = conn.execute(
            "SELECT review_id, tag FROM review_tags ORDER BY tag"
        ).fetchall()

    tag_map: dict[str, list[str]] = {}
    for t in tags:
        tag_map.setdefault(t["review_id"], []).append(t["tag"])
    for rv in reviews:
        rv["tags"] = tag_map.get(rv["id"], [])
    for o in orders:
        if o["review"]:
            o["review"]["tags"] = tag_map.get(o["review"]["id"], [])

    return ok({
        "user": user_out(me),
        "users": users,
        "items": items,
        "orders": orders,
        "comments": comments,
        "reviews": reviews,
        **_meta(),
    })
