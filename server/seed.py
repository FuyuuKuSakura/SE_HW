"""灌种子数据。

用法：
    python seed.py            # 重建（先清空再灌）
    python seed.py --check    # 只做一致性检查，不写库

一致性由程序保证，不靠手写：
  商品状态 ← 订单状态推导（pending/trading → reserved，completed → sold）
  订单卖家 ← 挂单卖家推导
所以不会出现"订单已完成但商品还在售"这种脏数据。
"""
import sys
from datetime import datetime, timedelta

from app.db import connect, init_schema
from app.seed_data import BASE_DATE, COMMENTS, ITEMS, ORDERS, PRODUCTS, USERS

BASE_DT = datetime.fromisoformat(BASE_DATE)


def ts(days_ago: float) -> str:
    return (BASE_DT - timedelta(days=days_ago)).isoformat(timespec="seconds")


def build() -> None:
    init_schema()
    conn = connect()
    try:
        with conn:
            # 清空（顺序受外键约束，子表先删）
            for table in ("review_tags", "reviews", "comments", "orders",
                          "items", "products", "users"):
                conn.execute(f"DELETE FROM {table}")

            for u in USERS:
                conn.execute(
                    """INSERT INTO users(id, name, avatar, credit, campus, joined_at, bio, password_hash)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (u["id"], u["name"], u["avatar"], u["credit"], u["campus"],
                     ts(u["joined_days_ago"]), u["bio"], None),
                )

            for pid, title, category, mode in PRODUCTS:
                conn.execute(
                    "INSERT INTO products(product_id, title, category, mode, created_at) VALUES (?,?,?,?,?)",
                    (pid, title, category, mode, ts(60)),
                )

            for it in ITEMS:
                conn.execute(
                    """INSERT INTO items(id, product_id, seller_id, title, price, original_price,
                                         mode, category, condition, img, description, location,
                                         status, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (it["id"], it["pid"], it["seller"], it["title"], it["price"], it["orig"],
                     it["mode"], it["cat"], it["cond"], it["img"], it["desc"], it["loc"],
                     it["status"], ts(it["days"])),
                )

            # 商品状态表：item_id → status（由订单推导）
            item_status = {}
            seller_of = {it["id"]: it["seller"] for it in ITEMS}
            mode_of = {it["id"]: it["mode"] for it in ITEMS}
            title_of = {it["id"]: it["title"] for it in ITEMS}
            img_of = {it["id"]: it["img"] for it in ITEMS}
            price_of = {it["id"]: it["price"] for it in ITEMS}
            pid_of = {it["id"]: it["pid"] for it in ITEMS}

            review_seq = 0
            for o in ORDERS:
                iid = o["item"]
                seller = seller_of[iid]
                buyer = o["buyer"]
                if buyer == seller:
                    raise SystemExit(f"订单 {o['id']} 买卖双方相同：{buyer}")

                # 同一挂单不能有两个进行中的订单
                if o["status"] in ("pending", "trading", "completed"):
                    if iid in item_status:
                        raise SystemExit(f"挂单 {iid} 出现两个有效订单：{item_status[iid]}")
                    item_status[iid] = "sold" if o["status"] == "completed" else "reserved"

                donate = mode_of[iid] == "donate"
                conn.execute(
                    """INSERT INTO orders(id, item_id, product_id, mode, buyer_id, seller_id,
                                         price, title_snap, img_snap, trade_method, message, status,
                                         reviewed, created_at, confirmed_at, completed_at, cancelled_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (o["id"], iid, pid_of[iid], mode_of[iid], buyer, seller,
                     0 if donate else price_of[iid], title_of[iid], img_of[iid],
                     o["trade"], o.get("msg", ""), o["status"],
                     1 if o.get("review") else 0,
                     ts(o["days"]),
                     ts(o["confirmed_days"]) if o.get("confirmed_days") else None,
                     ts(o["completed_days"]) if o.get("completed_days") else None,
                     ts(o["cancelled_days"]) if o.get("cancelled_days") else None),
                )

                if o.get("review"):
                    review_seq += 1
                    rid = f"r{review_seq:02d}"
                    conn.execute(
                        """INSERT INTO reviews(id, order_id, item_id, buyer_id, seller_id,
                                               stars, content, created_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (rid, o["id"], iid, buyer, seller, o["review"]["stars"],
                         o["review"]["text"], ts(o["completed_days"] - 0.3 if o.get("completed_days") else o["days"])),
                    )
                    for tag in o["review"]["tags"]:
                        conn.execute("INSERT INTO review_tags(review_id, tag) VALUES (?,?)", (rid, tag))

            for c in COMMENTS:
                conn.execute(
                    """INSERT INTO comments(id, item_id, user_id, parent_id, content, created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (c["id"], c["item"], c["user"], c["parent"], c["content"], ts(c["days"])),
                )

            # 应用推导出的商品状态
            for iid, status in item_status.items():
                conn.execute("UPDATE items SET status=? WHERE id=?", (status, iid))

        check(conn)
    finally:
        conn.close()


def check(conn=None) -> None:
    own = conn is None
    if own:
        conn = connect()
    try:
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("users", "products", "items", "orders", "reviews", "review_tags", "comments")
        }
        print("行数：", counts)

        bad = conn.execute(
            """SELECT o.id, o.status, i.status FROM orders o JOIN items i ON i.id = o.item_id
               WHERE (o.status IN ('pending','trading') AND i.status <> 'reserved')
                  OR (o.status = 'completed' AND i.status <> 'sold')"""
        ).fetchall()
        print("订单/商品状态不一致：", len(bad), [tuple(r) for r in bad])

        orphan = conn.execute(
            """SELECT COUNT(*) FROM items i WHERE i.status='on_sale'
               AND EXISTS (SELECT 1 FROM orders o WHERE o.item_id=i.id
                           AND o.status IN ('pending','trading','completed'))"""
        ).fetchone()[0]
        print("在售却有成交订单的商品：", orphan)

        stuck = conn.execute(
            """SELECT COUNT(*) FROM items i WHERE i.status IN ('reserved','sold')
               AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.item_id=i.id
                               AND o.status IN ('pending','trading','completed'))"""
        ).fetchone()[0]
        print("被锁定却没有有效订单的商品：", stuck)

        third = conn.execute(
            """SELECT COUNT(*) FROM comments c JOIN comments p ON p.id = c.parent_id
               WHERE p.parent_id IS NOT NULL"""
        ).fetchone()[0]
        print("三级评论：", third)

        bad_money = conn.execute(
            """SELECT COUNT(*) FROM orders o WHERE (o.mode='sale' AND o.price<=0)
               OR (o.mode='donate' AND (o.price<>0 OR o.trade_method<>'自提'))"""
        ).fetchone()[0]
        print("金额/流转方式违规订单：", bad_money)

        print("卖家统计视图：")
        for r in conn.execute(
            "SELECT seller_id, name, on_sale_count, sold_count, donated_count, sold_amount, "
            "review_count, avg_stars, positive_rate FROM v_seller_stats ORDER BY seller_id"
        ):
            print("  ", dict(r))
    finally:
        if own:
            conn.close()


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        build()
        print("种子数据已写入 zzj.db")
