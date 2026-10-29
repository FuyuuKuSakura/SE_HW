"""全链路接口自测。

不需要手动起服务：脚本自己在后台线程里跑一个 uvicorn，逐条打接口，
最后把数据库重建回种子状态（测试过程中会下单、改状态、发评论）。

    python test_api.py

报告同时打印到控制台并写入 api_test_report.txt。
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import uvicorn

import seed
from main import app

HOST, PORT = "127.0.0.1", 8123
BASE = f"http://{HOST}:{PORT}/api/v1"

LINES: list[str] = []
PASS = 0
FAIL = 0


def log(text: str = "") -> None:
    print(text)
    LINES.append(text)


def call(method: str, path: str, body=None, token: str | None = None):
    # 查询串里可能有中文（搜索同义词），必须先做百分号编码
    url = BASE + urllib.parse.quote(path, safe="/?=&")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def expect(label: str, cond: bool, detail="") -> None:
    global PASS, FAIL
    detail = "" if detail == "" else str(detail)
    if cond:
        PASS += 1
        log(f"  OK   {label}{('  → ' + detail) if detail else ''}")
    else:
        FAIL += 1
        log(f"  FAIL {label}  → {detail}")


def section(title: str) -> None:
    log("")
    log(f"■ {title}")


def main() -> None:
    log("专专后端 · 接口自测报告")
    log("=" * 72)

    # ---------------------------------------------------------------- 认证
    section("1. 认证")
    st, r = call("POST", "/auth/login", {"account": "naiwa", "password": "123456"})
    expect("POST /auth/login 奶蛙登录", st == 200 and r["code"] == 0, f"HTTP {st}")
    me_token = r["data"]["token"]
    expect("登录返回 user.name", r["data"]["user"]["name"] == "奶蛙", r["data"]["user"]["name"])

    st, r = call("POST", "/auth/login", {"account": "u2", "password": "x"})
    u2_token = r["data"]["token"]
    expect("POST /auth/login 陈默登录", st == 200 and r["data"]["user"]["id"] == "u2")

    st, r = call("POST", "/auth/login", {"account": "u3", "password": "x"})
    u3_token = r["data"]["token"]

    st, r = call("GET", "/auth/me", token=me_token)
    expect("GET /auth/me", st == 200 and r["data"]["credit"] == "信用极好", r["data"]["campus"])

    st, r = call("GET", "/auth/me")
    expect("无 token → 40100", st == 401 and r["code"] == 40100, f"HTTP {st} code {r['code']}")

    st, r = call("GET", "/auth/me", token="bad.token")
    expect("伪造 token → 40101", st == 401 and r["code"] == 40101, f"code {r['code']}")

    # ---------------------------------------------------------------- 市场
    section("2. 市场列表与近似搜索")
    st, r = call("GET", "/items?groupBy=product&pageSize=50", token=me_token)
    groups = r["data"]["list"]
    expect("GET /items 同款聚合", st == 200 and all("offers" in g for g in groups),
           f"{len(groups)} 个同款组 / 共 {r['data']['total']} 组")
    expect("列表不含自己的挂单", all(all(o["sellerId"] != "me" for o in g["offers"]) for g in groups))
    iphone = next((g for g in groups if g["productId"] == "p_iphone13"), None)
    # i1 是奶蛙自己的（且已被预订），市场里看不到，所以只有 u2/u6 两个卖家
    expect("iPhone 13 同款聚合 2 个卖家、最低 2199",
           iphone and iphone["sellerCount"] == 2 and iphone["minPrice"] == 2199,
           f"minPrice={iphone and iphone['minPrice']} sellerCount={iphone and iphone['sellerCount']}")

    st, r = call("GET", "/items?q=macbok&match=fuzzy&groupBy=offer", token=me_token)
    hit = [i["title"] for i in r["data"]["list"]]
    expect("拼写错误 macbok → MacBook（近似）", len(hit) > 0, f"{hit[:2]}")

    st, r = call("GET", "/items?q=macbok&match=exact&groupBy=offer", token=me_token)
    expect("match=exact 时 macbok 无结果", r["data"]["total"] == 0, f"total={r['data']['total']}")

    st, r = call("GET", "/items?q=单车&groupBy=offer", token=me_token)
    hit = [i["title"] for i in r["data"]["list"]]
    expect("同义词 单车 → 公路自行车", any("自行车" in t for t in hit), f"{hit[:2]}")

    st, r = call("GET", "/items?q=平果手机&groupBy=offer", token=me_token)
    expect("同义词 平果手机 → iPhone", any("iPhone" in i["title"] for i in r["data"]["list"]),
           f"{[i['title'] for i in r['data']['list']][:2]}")

    st, r = call("GET", "/items?category=图书&mode=donate&groupBy=offer", token=me_token)
    expect("分类+捐赠筛选", all(i["category"] == "图书" and i["mode"] == "donate"
                            for i in r["data"]["list"]), f"{len(r['data']['list'])} 条")

    st, r = call("GET", "/items?sort=price_asc&groupBy=offer&pageSize=50", token=me_token)
    prices = [i["price"] for i in r["data"]["list"]]
    expect("价格升序", prices == sorted(prices), f"{prices[:5]}…")

    st, r = call("GET", "/items?groupBy=offer&pageSize=5&page=2", token=me_token)
    expect("分页 hasMore", r["data"]["page"] == 2 and len(r["data"]["list"]) == 5,
           f"total={r['data']['total']} hasMore={r['data']['hasMore']}")

    # ---------------------------------------------------------------- 详情
    section("3. 挂单详情")
    st, r = call("GET", "/items/i2", token=me_token)
    d = r["data"]
    expect("GET /items/i2", st == 200 and d["id"] == "i2", d["title"])
    expect("含卖家信息卡", d["seller"]["name"] == "陈默" and d["seller"]["onSaleCount"] >= 0,
           f"{d['seller']['credit']} / 在售 {d['seller']['onSaleCount']}")
    expect("含同款其他卖家", len(d["sameProductOffers"]) == 2, f"{[o['sellerName'] for o in d['sameProductOffers']]}")
    expect("含评价数与评论数", "reviewCount" in d and "commentCount" in d,
           f"review={d['reviewCount']} comment={d['commentCount']}")

    st, r = call("GET", "/items/i999", token=me_token)
    expect("不存在的挂单 → 40400", st == 404 and r["code"] == 40400, f"code {r['code']}")

    # ---------------------------------------------------------------- 发布
    section("4. 发布 / 编辑 / 上下架")
    st, r = call("POST", "/items", {
        "title": "罗技 C270 摄像头", "price": 129, "originalPrice": 299, "mode": "sale",
        "category": "数码", "condition": "95新", "img": "i8",
        "desc": "线上答辩用的，画质清晰。", "location": "南苑 3 栋",
    }, token=me_token)
    new_id = r["data"]["id"]
    expect("POST /items 发布出售", st == 200 and r["data"]["status"] == "on_sale",
           f"{new_id} productId={r['data']['productId']}")
    expect("未传 productId 时自动建同款", r["data"]["productId"].startswith("p_"))

    st, r = call("PATCH", f"/items/{new_id}", {"price": 99, "desc": "降价出，急。"}, token=me_token)
    expect("PATCH /items/{id} 改价", st == 200 and r["data"]["price"] == 99, f"price={r['data']['price']}")

    st, r = call("PATCH", f"/items/{new_id}", {"price": 88}, token=u2_token)
    expect("改别人的挂单 → 40300", st == 403 and r["code"] == 40300, f"code {r['code']}")

    # 按 api.md 5.2：改为 donate 时价格必须为 0，所以只传 mode 会被拒绝
    st, r = call("PATCH", f"/items/{new_id}", {"mode": "donate"}, token=me_token)
    expect("只改 mode 不传价格 → 40002", st == 400 and r["code"] == 40002, r.get("message", ""))

    st, r = call("PATCH", f"/items/{new_id}", {"mode": "donate", "price": 0}, token=me_token)
    expect("mode=donate + price=0 通过", st == 200 and r["data"]["price"] == 0,
           f"price={r['data']['price']}")

    st, r = call("PATCH", f"/items/{new_id}", {"mode": "sale"}, token=me_token)
    expect("0 元改回出售 → 40002", st == 400 and r["code"] == 40002, r.get("message", ""))

    st, r = call("PATCH", f"/items/{new_id}", {"mode": "sale", "price": 88}, token=me_token)
    expect("改回出售并重新定价", st == 200 and r["data"]["mode"] == "sale" and r["data"]["price"] == 88,
           f"{r['data']['mode']}/{r['data']['price']}")

    st, r = call("POST", "/items", {"title": "0 元出售", "price": 0, "mode": "sale",
                                    "category": "其他", "condition": "9成新"}, token=me_token)
    expect("出售价 0 → 40002", st == 400 and r["code"] == 40002, r["message"])

    st, r = call("PATCH", f"/items/{new_id}/status", {"status": "off_shelf"}, token=me_token)
    expect("下架", st == 200 and r["data"]["status"] == "off_shelf", r["data"]["status"])
    st, r = call("PATCH", f"/items/{new_id}/status", {"status": "on_sale"}, token=me_token)
    expect("重新上架", st == 200 and r["data"]["status"] == "on_sale", r["data"]["status"])

    st, r = call("PATCH", "/items/i2/status", {"status": "off_shelf"}, token=u3_token)
    expect("下架别人的挂单 → 40300", st == 403 and r["code"] == 40300)

    st, r = call("GET", "/items/mine", token=me_token)
    expect("GET /items/mine", st == 200 and all(i["sellerId"] == "me" for i in r["data"]),
           f"{len(r['data'])} 件")

    # ---------------------------------------------------------------- 评论
    section("5. 评论与卖家回复")
    st, r = call("GET", "/items/i2/comments?page=1&pageSize=12", token=me_token)
    expect("GET 评论列表", st == 200 and len(r["data"]["list"]) == 1, f"total={r['data']['total']}")
    expect("一级评论内嵌卖家回复", r["data"]["list"][0]["replies"][0]["user"]["name"] == "陈默")

    st, r = call("POST", "/items/i2/comments", {"content": "还在吗？我今晚可以来取。"}, token=u3_token)
    new_comment = r["data"]["id"]
    expect("发一级评论", st == 200 and r["data"]["parentId"] is None, new_comment)

    st, r = call("POST", "/items/i2/comments", {"content": "", "parentId": new_comment}, token=u2_token)
    expect("空内容 → 40002", st == 400 and r["code"] == 40002, r["message"])

    st, r = call("POST", "/items/i2/comments", {"content": "在的，随时来。", "parentId": new_comment},
                 token=u3_token)
    expect("非卖家回复 → 40301", st == 403 and r["code"] == 40301, r["message"])

    st, r = call("POST", "/items/i2/comments", {"content": "在的，随时来。", "parentId": new_comment},
                 token=u2_token)
    expect("卖家回复成功", st == 200 and r["data"]["parentId"] == new_comment)
    reply_id = r["data"]["id"]

    st, r = call("POST", "/items/i2/comments", {"content": "再回一条。", "parentId": new_comment},
                 token=u2_token)
    expect("重复回复 → 40902", st == 409 and r["code"] == 40902, r["message"])

    st, r = call("POST", "/items/i2/comments", {"content": "回复的回复", "parentId": reply_id},
                 token=u2_token)
    expect("三级评论 → 40902", st == 409 and r["code"] == 40902, r["message"])

    st, r = call("DELETE", f"/comments/{new_comment}", token=u2_token)
    expect("删别人的评论 → 40301", st == 403 and r["code"] == 40301)

    st, r = call("DELETE", f"/comments/{new_comment}", token=u3_token)
    expect("删自己的评论（级联删回复）", st == 200 and r["data"]["deleted"] is True)

    # ---------------------------------------------------------------- 下单
    section("6. 下单与状态机（核心事务）")
    st, r = call("POST", "/orders", {"itemId": "i2", "tradeMethod": "自提", "message": "今晚方便"},
                 token=me_token)
    order_id = r["data"]["id"]
    expect("POST /orders 下单", st == 200 and r["data"]["status"] == "pending", order_id)
    expect("订单存商品快照", r["data"]["item"]["title"] == "iPhone 13 128G 星光色",
           r["data"]["item"]["title"])

    st, r = call("GET", "/items/i2", token=u3_token)
    expect("挂单被锁定为 reserved", r["data"]["status"] == "reserved", r["data"]["status"])

    st, r = call("POST", "/orders", {"itemId": "i2", "tradeMethod": "自提"}, token=u3_token)
    expect("抢已被预订的挂单 → 40901", st == 409 and r["code"] == 40901, r["message"])

    st, r = call("POST", "/orders", {"itemId": "i20", "tradeMethod": "自提"}, token=me_token)
    expect("买自己的东西 → 40300", st == 403 and r["code"] == 40300, r["message"])

    st, r = call("POST", "/orders", {"itemId": "i31", "tradeMethod": "快递"}, token=me_token)
    expect("捐赠选快递 → 40903", st == 409 and r["code"] == 40903, r["message"])

    st, r = call("GET", "/orders?role=buyer", token=me_token)
    expect("GET /orders?role=buyer", st == 200 and any(o["id"] == order_id for o in r["data"]),
           f"{len(r['data'])} 笔")

    st, r = call("GET", "/orders?role=seller", token=u2_token)
    expect("GET /orders?role=seller", st == 200 and any(o["id"] == order_id for o in r["data"]),
           f"{len(r['data'])} 笔")

    st, r = call("GET", f"/orders/{order_id}", token=u3_token)
    expect("非交易双方查订单 → 40300", st == 403 and r["code"] == 40300)

    st, r = call("POST", f"/orders/{order_id}/confirm", token=me_token)
    expect("买家确认 → 40300", st == 403 and r["code"] == 40300, r["message"])

    st, r = call("POST", f"/orders/{order_id}/confirm", token=u2_token)
    expect("卖家确认 pending→trading", st == 200 and r["data"]["status"] == "trading")

    st, r = call("POST", f"/orders/{order_id}/confirm", token=u2_token)
    expect("重复确认 → 40900", st == 409 and r["code"] == 40900, r["message"])

    st, r = call("POST", f"/orders/{order_id}/complete", token=me_token)
    expect("完成 trading→completed", st == 200 and r["data"]["status"] == "completed")

    st, r = call("GET", "/items/i2", token=u3_token)
    expect("挂单变为 sold", r["data"]["status"] == "sold", r["data"]["status"])

    # ---------------------------------------------------------------- 评价
    section("7. 评价")
    st, r = call("POST", f"/orders/{order_id}/review",
                 {"stars": 5, "tags": ["描述相符", "沟通顺畅"], "text": "手机成色很好，卖家很爽快。"},
                 token=me_token)
    expect("POST 评价", st == 200 and r["data"]["reviewed"] is True,
           f"{r['data']['review']['stars']} 星 {r['data']['review']['tags']}")

    st, r = call("POST", f"/orders/{order_id}/review", {"stars": 4, "tags": []}, token=me_token)
    expect("重复评价 → 40900", st == 409 and r["code"] == 40900, r["message"])

    st, r = call("POST", f"/orders/{order_id}/review", {"stars": 4}, token=u2_token)
    expect("卖家评价 → 40300", st == 403 and r["code"] == 40300)

    st, r = call("GET", "/items/i2/reviews", token=me_token)
    expect("GET 商品评价", st == 200 and r["data"]["total"] >= 1, f"total={r['data']['total']}")

    # ---------------------------------------------------------------- 取消
    section("8. 取消与放货")
    st, r = call("POST", "/orders", {"itemId": "i7", "tradeMethod": "自提"}, token=me_token)
    oid2 = r["data"]["id"]
    st, r = call("POST", f"/orders/{oid2}/cancel", token=me_token)
    expect("买家取消 pending→cancelled", st == 200 and r["data"]["status"] == "cancelled")
    st, r = call("GET", "/items/i7", token=me_token)
    expect("挂单回到 on_sale", r["data"]["status"] == "on_sale", r["data"]["status"])

    # ---------------------------------------------------------------- 卖家
    section("9. 卖家主页与统计")
    st, r = call("GET", "/sellers/me/profile", token=me_token)
    d = r["data"]
    expect("GET /sellers/me/profile", st == 200 and d["name"] == "奶蛙",
           f"在售{d['onSale']} 已售{d['soldCount']} 捐出{d['donatedCount']}")
    expect("好评率与平均星级", d["reviewCount"] >= 4 and 0 < d["avgStars"] <= 5,
           f"avgStars={d['avgStars']} positiveRate={d['positiveRate']} reviewCount={d['reviewCount']}")
    expect("评价标签计数", isinstance(d["tags"], list) and len(d["tags"]) > 0, d["tags"][:3])

    st, r = call("GET", "/sellers/u2/items", token=me_token)
    expect("GET /sellers/{id}/items", st == 200 and all(i["sellerId"] == "u2" for i in r["data"]["list"]),
           f"{r['data']['total']} 件在售")

    st, r = call("GET", "/sellers/me/sold", token=me_token)
    expect("GET /sellers/{id}/sold（含捐赠）", st == 200 and r["data"]["total"] >= 4,
           f"total={r['data']['total']}，含 donate={any(x['mode'] == 'donate' for x in r['data']['list'])}")

    st, r = call("GET", "/sellers/me/reviews", token=me_token)
    expect("GET /sellers/{id}/reviews", st == 200 and r["data"]["stats"]["reviewCount"] >= 4,
           f"stats={r['data']['stats']} tags={len(r['data']['tags'])}")

    st, r = call("GET", "/seller/stats", token=me_token)
    expect("GET /seller/stats 工作台", st == 200 and r["data"]["onSaleCount"] >= 1,
           f"在售{r['data']['onSaleCount']} 待处理{r['data']['pendingOrderCount']} "
           f"成交额{r['data']['completedAmount']} 捐出{r['data']['donatedCount']}")

    # ---------------------------------------------------------------- 元数据
    section("10. 元数据与前端快照")
    st, r = call("GET", "/categories", token=me_token)
    expect("GET /categories", st == 200 and len(r["data"]["categories"]) == 7,
           f"{r['data']['categories']}")

    st, r = call("GET", "/products/p_iphone13", token=me_token)
    expect("GET /products/{id} 同款全部卖家", st == 200 and len(r["data"]["offers"]) == 3,
           f"{[o['sellerName'] for o in r['data']['offers']]}")

    st, r = call("GET", "/bootstrap", token=me_token)
    d = r["data"]
    expect("GET /bootstrap 全量快照", st == 200 and all(
        k in d for k in ("user", "users", "items", "orders", "comments", "reviews", "categories")),
        f"items={len(d['items'])} orders={len(d['orders'])} comments={len(d['comments'])}")

    # ---------------------------------------------------------------- 汇总
    log("")
    log("=" * 72)
    log(f"用例合计 {PASS + FAIL} 条：通过 {PASS}，失败 {FAIL}")
    log("测试过程中产生的数据已回滚（数据库重建为种子状态）")


if __name__ == "__main__":
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="critical")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(120):
        if server.started:
            break
        time.sleep(0.1)
    time.sleep(0.3)

    try:
        main()
    except Exception:  # noqa: BLE001 - 自测脚本，出错也要把已有报告落盘
        import traceback
        log("")
        log("!! 自测中断，堆栈如下：")
        log(traceback.format_exc())
    finally:
        server.should_exit = True
        time.sleep(0.4)
        seed.build()  # 还原演示数据
        log("")
        log("数据库已重置为种子状态，可以打开 /docs 继续手动试。")

        with open("api_test_report.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(LINES) + "\n")
