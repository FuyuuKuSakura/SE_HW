# 专专 · 校园二手流转平台 —— 后端

按仓库里的 `api.md` v2 契约实现的服务端：**FastAPI + SQLite**，28 个契约接口 + 2 个便利接口，
71 条自测用例全部通过。

前端仍然是那个单文件 `index.html`，不需要重写——接上后端只改 9 个写操作函数，见「前端接入」。

---

## 30 秒跑起来

**Windows 一键：**

```bat
双击 run.bat
```

**手动：**

```bash
cd server
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python seed.py                  # 建表 + 灌 41 件商品 / 13 笔订单 / 16 条评论
uvicorn main:app --reload --port 8000
```

然后打开 **http://127.0.0.1:8000/docs** —— Swagger 页面，每个接口都能直接点「Try it out」发请求，
不用 curl，也不用 Postman。这一页就是答辩时的演示工具。

> 数据库文件是 `server/zzj.db`，第一次启动若不存在会自动建表并灌种子数据。
> 想重置演示数据：`python seed.py`（会清空重建）。

---

## 演示账号（密码随意，演示环境不校验）

| 账号 | 昵称 | 校区 | 角色定位 |
|---|---|---|---|
| `naiwa` 或 `me` | 奶蛙 | 南苑 3 栋 | 主视角，既是买家也是卖家 |
| `u2` | 陈默 | 北苑 1 栋 | 数码卖家，交易记录最多 |
| `u3` | 周雨 | 东苑 5 栋 | 毕业清仓，只卖过东西 |
| `u4` | 林一舟 | 南苑 2 栋 | 健身骑行装备 |
| `u5` | 苏可 | 西苑 7 栋 | 宿舍搬空 |
| `u6` | 何嘉 | 北苑 4 栋 | 新用户 |

**答辩杀手锏——两个窗口演示：**

1. 浏览器 A 用 `naiwa` 登录，在 `i2`（陈默的 iPhone）下单一单；
2. 浏览器 B 用 `u2` 登录，刷新订单列表 → 看到「待确认」；
3. B 点确认 → A 那边刷新看到「交易中」；
4. A 点完成 → 商品变成「已售出」，A 可以给 5 星评价，B 的卖家主页平均星级立刻变化。

三十秒演完，一次性证明：数据真落库了、双方实时可见、状态机没写死在前端。

---

## 目录结构

```
server/
├── main.py               # FastAPI 入口：挂路由、CORS、启动时自动灌数据
├── schema.sql            # 7 张表 + 8 个索引 + 1 个视图 + 1 个触发器
├── seed.py               # 灌种子数据 + 一致性自检
├── test_api.py           # 71 条接口自测（自带服务，跑完自动还原数据）
├── run.bat               # Windows 一键启动
├── requirements.txt
├── app/
│   ├── db.py             # 连接管理（每请求一条连接 + PRAGMA foreign_keys）
│   ├── errors.py         # 统一响应包 {code,message,data} 与 7 个业务错误码
│   ├── security.py       # HMAC token 签发 / 校验
│   ├── schemas.py        # Pydantic 请求体（camelCase ↔ snake_case）
│   ├── serializers.py    # 数据库行 → 接口 JSON（集中改名，敏感字段不漏）
│   ├── search.py         # 近似搜索：完全包含 / 中文 bigram / 编辑距离 / 同义词
│   └── routers/
│       ├── auth_routes.py      items 相关      item_routes.py
│       ├── order_routes.py     comment_routes.py
│       └── seller_routes.py    meta_routes.py
└── zzj.db                # 运行时生成，已 gitignore
```

---

## 接口清单

统一前缀 `/api/v1`，统一响应 `{"code": 0, "message": "ok", "data": ...}`，
失败时 `code` 为业务错误码（见下表），HTTP 状态码同步设置。

### 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/login` | 登录，返回 `{token, user}` |
| GET | `/auth/me` | 当前用户 |
| GET | `/auth/accounts` | 🅴 演示账号列表（方便开两个窗口） |

### 商品

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/items` | 市场列表：同款聚合、近似搜索、分类/流转筛选、三种排序、分页 |
| GET | `/items/mine` | 我发布的挂单 |
| GET | `/items/{id}` | 详情：卖家卡、同款其他卖家、评价数、评论数、最近订单状态 |
| POST | `/items` | 发布；不传 `productId` 自动新建同款 |
| PATCH | `/items/{id}` | 编辑（仅归属人，`reserved`/`sold` 不可编辑） |
| PATCH | `/items/{id}/status` | 上架 / 下架 |
| GET | `/items/{id}/reviews` | 该挂单的交易评价 |
| GET | `/items/{id}/comments` | 一级评论分页，内嵌卖家回复 |
| POST | `/items/{id}/comments` | 发评论；带 `parentId` 即卖家回复 |
| DELETE | `/comments/{id}` | 删自己的评论（一级评论级联删回复） |

### 订单

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/orders` | 下单 / 申请领取捐赠（事务：锁货 + 建单） |
| GET | `/orders?role=buyer\|seller` | 我的订单 |
| GET | `/orders/{id}` | 详情（仅交易双方） |
| POST | `/orders/{id}/confirm` | `pending → trading`（卖家） |
| POST | `/orders/{id}/complete` | `trading → completed`，挂单变 `sold` |
| POST | `/orders/{id}/cancel` | `pending → cancelled`，挂单回 `on_sale`（买家） |
| POST | `/orders/{id}/review` | 买家评价，每单一次 |

### 卖家与元数据

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/sellers/{id}/profile` | 主页资料 + 在售/已售/捐出/成交额/好评率/标签 |
| GET | `/sellers/{id}/items` | 卖家在售商品 |
| GET | `/sellers/{id}/sold` | 已完成交易（含捐赠） |
| GET | `/sellers/{id}/reviews` | 收到的评价 + 标签计数 + 统计 |
| GET | `/seller/stats` | 工作台四张数据卡 |
| GET | `/products/{productId}` | 同款详情与全部卖家挂单 |
| GET | `/categories` | 分类 / 成色 / 流转方式枚举 |
| GET | `/bootstrap` | 🅴 当前用户全量快照（前端内存缓存用） |

🅴 = 契约外的扩展接口，不影响 `api.md` 的其余部分。

### 错误码

| code | HTTP | 含义 |
|---|---|---|
| 40002 | 400 | 参数校验失败（价格非法、评论长度、字段缺失…） |
| 40100 | 401 | 未登录，缺少 token |
| 40101 | 401 | token 无效 |
| 40300 | 403 | 无权访问 / 对自己的挂单下单 / 买家确认订单 |
| 40301 | 403 | 无权操作该资源（非卖家回复、删别人评论） |
| 40400 | 404 | 资源不存在 |
| 40900 | 409 | 当前状态不允许该操作（重复确认、重复评价、已售商品编辑） |
| 40901 | 409 | 挂单不可下单（已被预订 / 已售出） |
| 40902 | 409 | 重复提交（重复回复、三级评论） |
| 40903 | 409 | 捐赠商品不能选快递 |

---

## 数据库设计：7 张表

```
users ──┬──< items >── products
        │      │
        │      ├──< orders >── users(buyer)
        │      │       │
        │      │       └──< reviews ──< review_tags
        │      │
        │      └──< comments (自引用，两层)
```

四个值得在答辩时讲的设计点：

**1. 商品状态不冗余存储，由订单驱动。** `pending/trading → reserved`，`completed → sold`，
`cancelled → 回到 on_sale`。种子脚本里商品状态是**从订单推导**出来的，不是手写的，
所以不可能出现「订单已完成、商品还挂在货架上」这种脏数据。

**2. 业务不变量写进 CHECK 约束，不靠代码自觉。**

```sql
CHECK ((mode = 'sale' AND price > 0) OR (mode = 'donate' AND price = 0))
CHECK (buyer_id <> seller_id)
CHECK (mode = 'sale' OR (price = 0 AND trade_method = '自提'))
```
就算有人绕过接口直接写库，脏数据也插不进去。

**3. 订单存商品快照（`title_snap` / `img_snap` / `price`）。** 商品可以被改价、被下架，
但历史订单必须固化成交当时的信息——否则买家翻旧订单会看到「我 399 买的椅子现在标价 199」。

**4. 统计口径收敛到一个视图。** `v_seller_stats` 把在售数、已售数、捐出数、成交额、
评价数、平均星级、好评率一次算完。商品详情、卖家主页、工作台三个入口都查它，
不可能算岔。好评率 = 4–5 星占比，成交额不含捐赠——口径全部来自 `api.md`。

另外：`review_tags` 拆表才能做「按次数倒序」的标签云；`reviews.order_id` 加 `UNIQUE`
天然防重复评价；`comments` 用一个 `BEFORE INSERT` 触发器堵死第三层评论（外键拦不住这个）。

---

## 三个必须用事务的地方

| 操作 | 两张表 |
|---|---|
| `POST /orders` 下单 | 插订单 + 挂单 `reserved` |
| `POST /orders/{id}/complete` | 订单 `completed` + 挂单 `sold` |
| `POST /orders/{id}/cancel` | 订单 `cancelled` + 挂单回 `on_sale` |

**防超卖没有用「先查状态再更新」**，因为那是典型的 TOCTOU 竞态——两个请求同时查到
`on_sale`，都以为能买。这里把判断塞进 WHERE，靠影响行数裁决：

```python
with conn:                                    # BEGIN / COMMIT / 出错 ROLLBACK
    cur = conn.execute(
        "UPDATE items SET status='reserved' WHERE id=? AND status='on_sale'", (item_id,))
    if cur.rowcount == 0:                     # 没抢到
        raise ApiError(409, 40901, "手慢了，这件刚被别人预订")
    conn.execute("INSERT INTO orders ...")    # 插单失败 → 上面那条 UPDATE 自动回滚
```

自测里用两个不同账号先后抢同一挂单验证过：第二个拿到 `40901`。

---

## 前端接入：只改 9 个函数

前端 `index.html` 有 13 处读 `DB.items` / `DB.orders`、9 处写 `save()`。
**读逻辑一行都不用改**——保留 `DB` 作为内存缓存，只在启动和写入后从 `/bootstrap` 重拉：

```javascript
const API = 'http://127.0.0.1:8000/api/v1';
let TOKEN = '';

async function api(path, method = 'GET', body) {
  const res = await fetch(API + path, {
    method,
    headers: { 'Content-Type': 'application/json', ...(TOKEN ? { Authorization: 'Bearer ' + TOKEN } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json();
  if (json.code !== 0) throw new Error(json.message);
  return json.data;
}

async function refresh() {
  const snap = await api('/bootstrap');
  DB = { items: snap.items, orders: snap.orders, user: snap.user, comments: snap.comments };
  render();
}
```

然后 9 个写函数各自换成对应的接口调用（函数名保持不动，页面事件绑定不用改）：

| 原函数 | 改成 |
|---|---|
| `placeOrder(itemId)` | `await api('/orders','POST',{itemId,tradeMethod,message}); await refresh();` |
| `confirmOrder(id)` | `await api('/orders/'+id+'/confirm','POST'); await refresh();` |
| `completeOrder(id)` | `await api('/orders/'+id+'/complete','POST'); await refresh();` |
| `cancelOrder(id)` | `await api('/orders/'+id+'/cancel','POST'); await refresh();` |
| `submitReview()` | `await api('/orders/'+id+'/review','POST',{stars,tags,text}); await refresh();` |
| `submitPublish(editId)` | 新建 `POST /items`，编辑 `PATCH /items/{id}` |
| `toggleItemStatus(id)` | `await api('/items/'+id+'/status','PATCH',{status}); await refresh();` |

前端页面可以直接从后端访问（前后端同源，省掉跨域）：把 `index.html` 放在 `server/` 的
上一级目录，然后打开 **http://127.0.0.1:8000/app**。

**字段对照**（`/bootstrap` 返回的字段和前端 `DB` 对象基本一一对应，改名的地方只有一处）：

| 前端字段 | 接口字段 | 说明 |
|---|---|---|
| `item.desc` | `desc` | 数据库列叫 `description`，序列化层已改名 |
| `item.originalPrice` | `originalPrice` | |
| `item.createdAt` | `createdAt` | ISO8601 带 `+08:00`，前端 `new Date()` 直接能吃 |
| `order.review` | `review` | `{stars, tags[], text, createdAt}`，没评价时为 `null` |
| `order.reviewed` | `reviewed` | 布尔值 |
| `USERS[id]` | `snap.users` | 接口返回数组，用 `Object.fromEntries(users.map(u=>[u.id,u]))` 转成字典 |

前端原本把 `USERS` 写死在文件里，接后端后建议同样从 `/bootstrap` 的 `users` 构建，
否则卖家主页进去会拿不到陌生卖家的资料。

---

## 自测

```bash
cd server
python test_api.py
```

脚本自己在后台线程起一个 uvicorn（8123 端口），按 10 个模块打 71 条用例，
覆盖登录鉴权、近似搜索、同款聚合、发布编辑、评论两层约束、下单事务、状态机、
重复评价、取消放货、卖家统计、前端快照。跑完自动把数据库还原成种子状态。

结果同时打印到控制台并写入 `api_test_report.txt`。

最近一次：**74 条用例，通过 74，失败 0**（含 3 条边界断言）。

---

## 常见问题

**端口 8000 被占用** → `uvicorn main:app --port 8010`，同时改前端的 `API` 常量。

**`database is locked`** → 已开 WAL + 15 秒 timeout，正常不会出现。若频繁出现，
检查是不是有另一个进程（比如 DB Browser）独占了 `zzj.db`。

**改了 `schema.sql` 却没生效** → 表已存在时 `CREATE TABLE IF NOT EXISTS` 不会改结构。
删掉 `zzj.db` 再 `python seed.py`。

**前端 `file://` 打开报跨域** → 后端已开 `allow_origins=["*"]`，但仍然建议用
`http://127.0.0.1:8000/app` 访问，减少一层变量。

**想换成 MySQL** → SQL 基本都是标准语法，改动集中在 `app/db.py` 的连接管理和
`schema.sql` 的 `INTEGER PRIMARY KEY` / `TEXT` 类型映射，路由层不用动。

---

## 与原型相比新增的能力

原型是纯前端 + 浏览器本地存储：换台电脑数据就没了，两个人也看不到对方的操作。
接上后端之后新增的是**真实的多用户语义**：

- 数据落库，跨设备、跨浏览器一致；
- 权限由服务端强制：不能买自己的东西、只有卖家能确认、只有买家能取消和评价；
- 并发安全：两个买家同一秒下单，只有一个成功；
- 聚合可信：好评率、成交额、标签云由 SQL 算，不靠前端遍历内存；
- 可审计：订单保存商品快照，商品后续被改被删都不影响历史。
