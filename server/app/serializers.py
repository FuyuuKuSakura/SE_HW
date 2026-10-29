"""ORM 行 → 接口 JSON 的映射层。

集中在一处转换有三个好处：
1. 数据库列名（description / content）和接口字段（desc / text）可以不一样，
   不用在每个路由里重复改名；
2. 想加字段只改这里，前端契约不会散落各处；
3. 敏感字段（password_hash）天然不会漏出去。
"""
import sqlite3
from typing import Any

Row = sqlite3.Row


def _d(row: Row | dict | None) -> dict:
    if row is None:
        return {}
    return dict(row)


def _user_brief(row: Row | dict | None) -> dict:
    r = _d(row)
    return {
        "id": r.get("id") or r.get("user_id") or r.get("seller_id") or r.get("buyer_id"),
        "name": r.get("name") or r.get("user_name") or r.get("seller_name") or r.get("buyer_name"),
        "avatar": r.get("avatar") or r.get("user_avatar") or r.get("seller_avatar") or r.get("buyer_avatar"),
    }


def user_out(row: Row | dict) -> dict:
    r = _d(row)
    return {
        "id": r["id"],
        "name": r["name"],
        "avatar": r.get("avatar"),
        "credit": r.get("credit"),
        "campus": r.get("campus"),
        "joinedAt": r.get("joined_at"),
        "bio": r.get("bio"),
    }


def item_out(row: Row | dict) -> dict:
    r = _d(row)
    return {
        "id": r["id"],
        "productId": r["product_id"],
        "sellerId": r["seller_id"],
        "sellerName": r.get("seller_name"),
        "title": r["title"],
        "price": r["price"],
        "originalPrice": r.get("original_price"),
        "mode": r["mode"],
        "category": r["category"],
        "condition": r["condition"],
        "img": r.get("img"),
        "desc": r.get("description"),
        "location": r.get("location"),
        "status": r["status"],
        "createdAt": r["created_at"],
    }


def offer_brief(row: Row | dict) -> dict:
    """同款在售列表里的一条挂单（比 item_out 精简）。"""
    r = _d(row)
    return {
        "id": r["id"],
        "sellerId": r["seller_id"],
        "sellerName": r.get("seller_name"),
        "price": r["price"],
        "condition": r["condition"],
        "status": r["status"],
        "location": r.get("location"),
        "createdAt": r["created_at"],
    }


def review_out(row: Row | dict, tags: list[str] | None = None) -> dict:
    r = _d(row)
    out = {
        "id": r.get("id"),
        "orderId": r.get("order_id"),
        "stars": r.get("stars"),
        "tags": tags if tags is not None else r.get("tags", []),
        "text": r.get("content"),
        "createdAt": r.get("created_at"),
        "buyer": _user_brief({"buyer_id": r.get("buyer_id"), "buyer_name": r.get("buyer_name"),
                              "buyer_avatar": r.get("buyer_avatar")}),
    }
    if r.get("item_id"):
        out["item"] = {"id": r.get("item_id"), "title": r.get("item_title"), "img": r.get("item_img")}
    return out


def comment_out(row: Row | dict) -> dict:
    r = _d(row)
    return {
        "id": r["id"],
        "itemId": r["item_id"],
        "userId": r["user_id"],
        "user": _user_brief({"user_id": r["user_id"], "user_name": r.get("user_name"),
                             "user_avatar": r.get("user_avatar")}),
        "parentId": r.get("parent_id"),
        "content": r["content"],
        "createdAt": r["created_at"],
        "replies": [],
    }


def order_out(row: Row | dict) -> dict:
    r = _d(row)
    out: dict[str, Any] = {
        "id": r["id"],
        "itemId": r["item_id"],
        "productId": r["product_id"],
        "mode": r["mode"],
        "buyerId": r["buyer_id"],
        "sellerId": r["seller_id"],
        "buyer": _user_brief({"buyer_id": r["buyer_id"], "buyer_name": r.get("buyer_name"),
                              "buyer_avatar": r.get("buyer_avatar")}),
        "seller": _user_brief({"seller_id": r["seller_id"], "seller_name": r.get("seller_name"),
                               "seller_avatar": r.get("seller_avatar")}),
        "price": r["price"],
        "item": {"id": r["item_id"], "title": r["title_snap"], "img": r.get("img_snap")},
        "tradeMethod": r["trade_method"],
        "message": r.get("message"),
        "status": r["status"],
        "reviewed": bool(r["reviewed"]),
        "createdAt": r["created_at"],
        "confirmedAt": r.get("confirmed_at"),
        "completedAt": r.get("completed_at"),
        "cancelledAt": r.get("cancelled_at"),
        "review": None,
    }
    if r.get("review_id"):
        out["review"] = {
            "id": r["review_id"],
            "stars": r["review_stars"],
            "tags": [],
            "text": r.get("review_content"),
            "createdAt": r.get("review_created_at"),
        }
    return out
