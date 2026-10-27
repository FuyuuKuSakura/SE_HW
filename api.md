# 专专 · 二手物品流转管理系统 API 契约

版本：v2（第二轮前端迭代）
更新日期：2026-10-27

## 1. 说明

本文档描述系统接入真实后端时的 HTTP 接口契约，对应交付的纯前端 demo `index.html`。

当前 demo 仍然是**单文件、无后端、无数据库**：所有数据保存在浏览器 `localStorage` 中，键为 `zz_demo_v2`。页面内部用同步 `store` / 查询函数读写，函数语义与本文接口一一对应；接入后端时，把本地函数替换为 `fetch` 调用即可，页面层不需要重写。

- Demo 入口：`index.html`
- 预置账号：`naiwa` / `123456`（不校验，仅展示）
- 数据存储键：`zz_demo_v2`（旧键 `zz_demo_v1` 会自动迁移）
- 初始数据：41 件商品、13 笔订单、16 条评论、6 个卖家
- 默认版本：`0.0.1`；版本记录见 `CHANGELOG.md` 和站内 `#/changelog`

### 1.1 v2 变更摘要

| 变更 | 说明 |
| --- | --- |
| 同款多卖家 | Item 增加 `productId`，新增商品聚合、同款在售和“我也有一件” |
| 捐赠 | Item / Order 增加 `mode`（`sale` / `donate`），捐赠 0 元、仅自提 |
| 商品评论 | 新增 Comment 模型与评论增删查接口，支持一条卖家回复 |
| 近似搜索 | `GET /items` 增加 `match=fuzzy\|exact`、`minScore`、`score`、`matchType` |
| 卖家主页 | 新增卖家资料、在售、已售、评价风评聚合接口 |
| 数据迁移 | v1 商品补 `productId` / `mode`，订单补快照，新增评论集合 |

## 2. 通用约定

### 2.1 基础信息

| 项目 | 约定 |
| --- | --- |
| Base URL | `/api/v1` |
| 编码 | UTF-8 |
| 请求体 | `application/json` |
| 鉴权 | `Authorization: Bearer <token>` |
| 时间格式 | ISO 8601，带时区，例如 `2026-10-27T18:30:00+08:00` |
| 金额 | 整数，单位为元；捐赠商品固定为 `0` |
| ID | 字符串，服务端生成，客户端不要假设格式 |
| 分页 | 默认 `page=1`、`pageSize=12`，最大 50 |

### 2.2 响应包

所有接口统一返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

`code = 0` 表示成功；非 0 时 `data` 为 `null`，`message` 为可直接展示的错误信息。

### 2.3 分页

列表接口统一返回：

```json
{
  "list": [],
  "page": 1,
  "pageSize": 12,
  "total": 21,
  "hasMore": true
}
```

### 2.4 错误码

| code | HTTP | 含义 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 40001 | 400 | 参数缺失或格式错误 |
| 40002 | 400 | 评论内容为空、超过 200 字或包含非法内容 |
| 40100 | 401 | 未登录或 token 失效 |
| 40300 | 403 | 无权限（不是商品 / 订单 / 评论的归属人） |
| 40301 | 403 | 无权删除该评论，或无权以卖家身份回复 |
| 40400 | 404 | 资源不存在 |
| 40900 | 409 | 当前状态不允许该操作 |
| 40901 | 409 | 商品当前不可购买（已预订、已售出或已下架） |
| 40902 | 409 | 该评论已经有一条卖家回复 |
| 40903 | 409 | 捐赠商品仅支持同校自提 |
| 50000 | 500 | 服务端异常 |

状态冲突示例：商品已被别人下单、重复确认订单、重复评价、重复回复同一条评论。

## 3. 数据模型

### 3.1 User

```json
{
  "id": "u2",
  "name": "陈默",
  "avatar": "avatar_u2.png",
  "credit": "信用极好",
  "campus": "北苑 1 栋",
  "joinedAt": "2023-09-01T09:00:00+08:00",
  "bio": "数码爱好者，出物必把成色和配件写清楚。"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 用户 ID |
| name | string | 昵称 |
| avatar | string | 头像 URL；demo 内嵌 base64，生产环境换成 CDN URL |
| credit | string | 信用等级文案 |
| campus | string | 常用交易地点 |
| joinedAt | string | 加入时间 |
| bio | string | 个人简介，可为空 |

### 3.2 ProductGroup

同款聚合结果，用于首页卡片。后端可以由 `productId` 聚合得到，也可以单独建商品表。

```json
{
  "productId": "p_iphone13",
  "title": "iPhone 13 128G 午夜色",
  "category": "数码",
  "mode": "sale",
  "img": "i1",
  "minPrice": 2199,
  "sellerCount": 3,
  "offerCount": 3,
  "score": 0.92,
  "matchType": "fuzzy",
  "offers": [
    {
      "id": "i38",
      "sellerId": "u6",
      "sellerName": "何嘉",
      "price": 2199,
      "condition": "8成新",
      "status": "on_sale",
      "location": "北苑 4 栋"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| productId | string | 同款商品 ID |
| title | string | 展示标题，取代表挂单标题 |
| category | string | 分类 |
| mode | enum | `sale` / `donate`；聚合键为 `productId + mode` |
| img | string | 代表图片 |
| minPrice | int | 当前在售最低价；捐赠为 0 |
| sellerCount | int | 当前在售的不同卖家数 |
| offerCount | int | 当前在售挂单数 |
| score | number | 仅搜索时返回，0–1 |
| matchType | enum | `exact` / `fuzzy`，仅搜索时返回 |
| offers | array | 在售挂单摘要，可按需裁剪 |

### 3.3 Item（卖家挂单）

`Item` 表示**一个卖家的一条挂单**，不是“商品库”。同一 `productId` 下可以有多条 Item，分别属于不同卖家。

```json
{
  "id": "i38",
  "productId": "p_iphone13",
  "title": "iPhone 13 128G 午夜色",
  "price": 2199,
  "originalPrice": 5999,
  "mode": "sale",
  "category": "数码",
  "condition": "8成新",
  "img": "i1",
  "sellerId": "u6",
  "sellerName": "何嘉",
  "status": "on_sale",
  "desc": "同款午夜色，边框有使用痕迹，屏幕一直贴膜。电池健康 85%，可小刀。",
  "location": "北苑 4 栋",
  "createdAt": "2026-10-27T02:00:00+08:00",
  "updatedAt": "2026-10-27T02:00:00+08:00"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 挂单 ID |
| productId | string | 同款商品 ID；相同 `productId` 的挂单聚合成一张首页卡片 |
| title | string | 标题，1–40 字 |
| price | int | 售价；`mode = donate` 时必须为 0 |
| originalPrice | int/null | 原价；捐赠为 0 或 null |
| mode | enum | `sale`（出售）/ `donate`（捐赠） |
| category | enum | 分类，见 4.1 |
| condition | enum | 成色，见 4.2 |
| img | string | 图片标识或 URL |
| sellerId / sellerName | string | 卖家 |
| status | enum | 商品状态，见 4.3 |
| desc | string | 描述 |
| location | string | 交易地点 |
| createdAt / updatedAt | string | 时间 |

### 3.4 Order

```json
{
  "id": "ZZ20261027001",
  "itemId": "i38",
  "productId": "p_iphone13",
  "mode": "sale",
  "item": {
    "id": "i38",
    "title": "iPhone 13 128G 午夜色",
    "img": "i1",
    "price": 2199,
    "condition": "8成新"
  },
  "buyerId": "me",
  "buyerName": "奶蛙",
  "sellerId": "u6",
  "sellerName": "何嘉",
  "price": 2199,
  "status": "pending",
  "tradeMethod": "自提",
  "message": "今晚方便看机吗？",
  "createdAt": "2026-10-27T18:45:00+08:00",
  "confirmedAt": null,
  "completedAt": null,
  "cancelledAt": null,
  "reviewed": false,
  "review": null
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 订单号 |
| itemId | string | 具体挂单 ID；同款商品只锁定被下单的那条挂单 |
| productId | string | 下单时的同款 ID 快照 |
| mode | enum | 下单时的流转方式快照 |
| item | object | 商品快照，避免卖家改价影响历史订单 |
| buyerId / buyerName | string | 买家 |
| sellerId / sellerName | string | 卖家 |
| price | int | 成交价快照；捐赠为 0 |
| status | enum | 订单状态，见 4.4 |
| tradeMethod | enum | `自提` / `快递`；捐赠订单固定 `自提` |
| message | string | 买家留言，可为空 |
| createdAt | string | 下单时间 |
| confirmedAt / completedAt / cancelledAt | string/null | 状态时间 |
| reviewed | bool | 是否已评价 |
| review | object/null | 评价内容，见 3.5 |

### 3.5 Review

```json
{
  "stars": 5,
  "tags": ["描述相符", "沟通顺畅"],
  "text": "机子和描述一致，卖家还帮忙贴了膜。",
  "createdAt": "2026-10-27T20:00:00+08:00"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| stars | int | 1–5 |
| tags | string[] | 最多 4 个，来自预设标签 |
| text | string | 评价正文，可为空，服务端可补默认文案 |
| createdAt | string | 评价时间 |

评价是**订单维度**的：只有已完成订单的买家可以评价，且每单只能评价一次。

### 3.6 Comment

```json
{
  "id": "c1001",
  "itemId": "i7",
  "userId": "u3",
  "user": {
    "id": "u3",
    "name": "周雨",
    "avatar": "avatar_u3.png"
  },
  "parentId": null,
  "content": "这台电池循环多少次呀？",
  "createdAt": "2026-10-27T15:00:00+08:00",
  "replies": [
    {
      "id": "c1002",
      "itemId": "i7",
      "userId": "u2",
      "user": {
        "id": "u2",
        "name": "陈默",
        "avatar": "avatar_u2.png"
      },
      "parentId": "c1001",
      "content": "120 次，健康 91%。可以来北苑当面验机。",
      "createdAt": "2026-10-27T15:10:00+08:00"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 评论 ID |
| itemId | string | 挂单 ID；评论按挂单维度隔离 |
| userId / user | string/object | 评论人 |
| parentId | string/null | 一级评论为 null；卖家回复指向一级评论 ID |
| content | string | 正文，1–200 字 |
| createdAt | string | 发布时间 |
| replies | array | 仅一级评论返回；最多一条卖家回复 |

规则：

1. 评论和交易评价是两套数据：评论不要求交易，评价必须绑定已完成订单。
2. 每条一级评论最多一条卖家回复。
3. 只有该挂单的卖家可以回复；回复以 `parentId` 指向一级评论。
4. 删除一级评论时，其卖家回复一并删除（或软删除）。
5. 当前只做一级评论 + 一条卖家回复，不做点赞、举报、多级嵌套。

### 3.7 SellerProfile

```json
{
  "user": {
    "id": "u2",
    "name": "陈默",
    "avatar": "avatar_u2.png",
    "credit": "信用极好",
    "campus": "北苑 1 栋",
    "joinedAt": "2023-09-01T09:00:00+08:00",
    "bio": "数码爱好者，出物必把成色和配件写清楚。"
  },
  "stats": {
    "onSale": 4,
    "soldCount": 3,
    "donatedCount": 1,
    "soldAmount": 1698,
    "reviewCount": 4,
    "avgStars": 4.75,
    "positiveRate": 100
  },
  "tags": [
    { "name": "沟通顺畅", "count": 3 },
    { "name": "描述相符", "count": 2 }
  ]
}
```

| 字段 | 说明 |
| --- | --- |
| onSale | 当前在售挂单数 |
| soldCount | 已完成出售订单数（不含捐赠） |
| donatedCount | 已完成捐赠订单数 |
| soldAmount | 已完成出售订单金额合计（不含捐赠） |
| reviewCount | 收到的评价数 |
| avgStars | 平均星级，保留 2 位小数 |
| positiveRate | 好评率（4–5 星占比，0–100） |
| tags | 评价标签计数，按次数倒序 |

## 4. 枚举

### 4.1 分类

`数码`、`家电`、`家具`、`图书`、`服饰`、`运动`、`其他`

### 4.2 成色

`99新`、`95新`、`9成新`、`8成新`、`7成新`

### 4.3 商品状态

| 值 | 含义 | 可执行操作 |
| --- | --- | --- |
| on_sale | 在售 | 买家下单、卖家下架 |
| reserved | 已预订 | 等待交易完成；不可编辑状态 |
| sold | 已售出 | 交易完成，只读 |
| off_shelf | 已下架 | 卖家重新上架 |

### 4.4 订单状态

| 值 | 含义 |
| --- | --- |
| pending | 待卖家确认 |
| trading | 交易中（卖家已确认） |
| completed | 已完成 |
| cancelled | 已取消 |

### 4.5 流转方式

| 值 | 含义 | 规则 |
| --- | --- | --- |
| sale | 出售 | `price > 0`，支持自提 / 快递 |
| donate | 捐赠 | `price = 0`，订单只能自提 |

## 5. 接口清单

### 5.1 认证

#### POST /auth/login

演示环境不校验账号密码；真实后端应校验并签发 token。

请求：

```json
{ "account": "naiwa", "password": "123456" }
```

响应 `data`：

```json
{
  "token": "jwt_or_session_token",
  "user": {
    "id": "me",
    "name": "奶蛙",
    "avatar": "naiwa.png",
    "credit": "信用极好",
    "campus": "南苑 3 栋",
    "joinedAt": "2024-09-01T09:00:00+08:00",
    "bio": "喜欢折腾数码，也爱把闲置送给需要的人。"
  }
}
```

#### GET /auth/me

返回当前登录用户，结构同上 `user`。

### 5.2 商品与同款

#### GET /items

买家市场列表。默认只返回 `status = on_sale` 且不属于当前用户的挂单。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| q | string | 否 | 关键词 |
| match | enum | 否 | `fuzzy`（默认）/ `exact` |
| minScore | number | 否 | 近似搜索最低分，默认 0.34 |
| category | string | 否 | 分类；不传或 `全部` 表示全部 |
| mode | enum | 否 | `sale` / `donate`；不传表示全部 |
| sort | enum | 否 | `latest`（默认）/ `price_asc` / `price_desc` / `relevance` |
| groupBy | enum | 否 | `product`（默认，同款聚合）/ `offer`（平铺挂单） |
| page | int | 否 | 默认 1 |
| pageSize | int | 否 | 默认 12，最大 50 |

说明：

- `groupBy=product` 时按 `(productId, mode)` 聚合，`list` 为 ProductGroup；`sellerCount`、`minPrice` 只统计在售挂单。
- `groupBy=offer` 时 `list` 为 Item。
- 搜索时每个结果额外返回 `score`（0–1）和 `matchType`（`exact` / `fuzzy`）。
- `match=fuzzy` 时，完全匹配优先；没有完全匹配但达到 `minScore` 的结果按相似度排序。
- 当 `q` 非空且 `sort=latest` 时，服务端可以按 `relevance` 排序；前端在 `sort` 为价格时以价格优先。

响应示例（groupBy=product）：

```json
{
  "list": [
    {
      "productId": "p_iphone13",
      "title": "iPhone 13 128G 午夜色",
      "category": "数码",
      "mode": "sale",
      "img": "i1",
      "minPrice": 2199,
      "sellerCount": 3,
      "offerCount": 3,
      "score": 0.92,
      "matchType": "fuzzy",
      "offers": [
        {
          "id": "i38",
          "sellerId": "u6",
          "sellerName": "何嘉",
          "price": 2199,
          "condition": "8成新",
          "status": "on_sale",
          "location": "北苑 4 栋"
        }
      ]
    }
  ],
  "page": 1,
  "pageSize": 12,
  "total": 1,
  "hasMore": false
}
```

#### GET /items/{id}

返回单个挂单详情，额外包含：

```json
{
  "seller": {
    "id": "u2",
    "name": "陈默",
    "credit": "信用极好",
    "campus": "北苑 1 栋",
    "onSaleCount": 4
  },
  "reviewCount": 2,
  "commentCount": 3,
  "latestOrderStatus": "reserved",
  "sameProductOffers": [
    {
      "id": "i23",
      "sellerId": "u3",
      "sellerName": "周雨",
      "price": 2299,
      "condition": "9成新",
      "status": "on_sale",
      "location": "东苑 5 栋",
      "createdAt": "2026-10-27T09:00:00+08:00"
    }
  ]
}
```

- `sameProductOffers` 返回同 `productId`、同 `mode` 的其他挂单，按状态和在售价排序。
- `reviewCount` 是交易评价数；`commentCount` 是一级评论数。

#### GET /products/{productId}

返回同款商品详情与全部卖家挂单：

```json
{
  "productId": "p_iphone13",
  "title": "iPhone 13 128G",
  "category": "数码",
  "mode": "sale",
  "offers": [
    {
      "id": "i22",
      "sellerId": "u2",
      "sellerName": "陈默",
      "price": 2399,
      "condition": "95新",
      "status": "on_sale",
      "location": "北苑 1 栋"
    },
    {
      "id": "i23",
      "sellerId": "u3",
      "sellerName": "周雨",
      "price": 2299,
      "condition": "9成新",
      "status": "on_sale",
      "location": "东苑 5 栋"
    },
    {
      "id": "i38",
      "sellerId": "u6",
      "sellerName": "何嘉",
      "price": 2199,
      "condition": "8成新",
      "status": "on_sale",
      "location": "北苑 4 栋"
    }
  ],
  "minPrice": 2199,
  "sellerCount": 3
}
```

#### POST /items

发布挂单。

请求：

```json
{
  "title": "iPhone 13 128G 星光色",
  "price": 2599,
  "originalPrice": 5999,
  "mode": "sale",
  "productId": "p_iphone13",
  "category": "数码",
  "condition": "95新",
  "img": "i1",
  "desc": "自用一年，电池健康 89%。",
  "location": "南苑 3 栋"
}
```

规则：

- `sellerId` 强制为当前用户，`status = on_sale`。
- `mode = sale` 时 `price > 0`；`mode = donate` 时 `price` 必须为 0 或省略。
- `productId` 可选：传入表示加入已有同款；不传则服务端生成新的 `productId`。
- 同一 `productId` 下允许存在不同 `mode` 的挂单，但市场列表按 `(productId, mode)` 分组展示，避免捐赠 0 元价格覆盖出售价。
- 响应 `data`：新 Item。

#### PATCH /items/{id}

编辑挂单，仅商品归属人可调用。可编辑字段：

`title`、`price`、`originalPrice`、`mode`、`category`、`condition`、`img`、`desc`、`location`。

规则：

- 不允许通过该接口修改 `productId`、`sellerId`、`status`。
- 改为 `donate` 时价格必须为 0；改为 `sale` 时价格必须大于 0。
- 商品为 `reserved` / `sold` 时不允许编辑。

#### PATCH /items/{id}/status

上架 / 下架。

```json
{ "status": "off_shelf" }
```

允许值：`on_sale`、`off_shelf`。当商品为 `reserved` 或 `sold` 时返回 `40900`。

#### GET /items/mine

卖家工作台的“我的商品”。

查询参数：`status`（可选，按商品状态过滤）、`mode`（可选）。

响应 `data`：Item 数组。

#### GET /items/{id}/reviews

该挂单的交易评价列表。

响应 `data`：

```json
{
  "list": [
    {
      "stars": 5,
      "tags": ["描述相符", "沟通顺畅"],
      "text": "椅子很稳，卖家还帮忙搬下楼，感谢！",
      "createdAt": "2026-10-17T09:45:00+08:00",
      "buyer": { "id": "u3", "name": "周雨", "avatar": "avatar_u3.png" }
    }
  ],
  "total": 1
}
```

### 5.3 商品评论

#### GET /items/{id}/comments

一级评论分页列表，每条一级评论内嵌最多一条卖家回复。

查询参数：`page`、`pageSize`。

响应 `data`：

```json
{
  "list": [
    {
      "id": "c1",
      "itemId": "i7",
      "userId": "u3",
      "user": { "id": "u3", "name": "周雨", "avatar": "avatar_u3.png" },
      "parentId": null,
      "content": "这台电池循环多少次呀？",
      "createdAt": "2026-10-27T15:00:00+08:00",
      "replies": [
        {
          "id": "c2",
          "itemId": "i7",
          "userId": "u2",
          "user": { "id": "u2", "name": "陈默", "avatar": "avatar_u2.png" },
          "parentId": "c1",
          "content": "120 次，健康 91%。可以来北苑当面验机。",
          "createdAt": "2026-10-27T15:10:00+08:00"
        }
      ]
    }
  ],
  "page": 1,
  "pageSize": 12,
  "total": 1,
  "hasMore": false
}
```

按一级评论 `createdAt` 倒序；回复按 `createdAt` 正序。

#### POST /items/{id}/comments

发布评论或卖家回复。

发布一级评论：

```json
{
  "content": "这台电池循环多少次呀？"
}
```

卖家回复：

```json
{
  "content": "120 次，健康 91%。可以来北苑当面验机。",
  "parentId": "c1"
}
```

规则：

1. 内容 1–200 字，去掉首尾空白后不能为空，否则 `40002`。
2. `parentId` 为空：创建一级评论；任意登录用户都可以发。
3. `parentId` 非空：必须是同一 `itemId` 下的一级评论，且当前用户必须是该挂单卖家，否则 `40301`。
4. 每条一级评论最多一条卖家回复，重复回复返回 `40902`。
5. 评论和回复都不允许嵌套第三层。
6. 建议服务端做敏感词过滤、频率限制和审计。

响应 `data`：新 Comment（一级评论带空 `replies`）。

#### DELETE /comments/{id}

删除自己的评论或回复。

- 一级评论：只能删除自己发布的；删除时级联删除其卖家回复。
- 卖家回复：只能由发布它的卖家删除。
- 无权限返回 `40301`。

响应 `data`：`{ "deleted": true }`。

### 5.4 订单

#### POST /orders

买家下单 / 申请领取捐赠。

出售商品：

```json
{
  "itemId": "i9",
  "tradeMethod": "自提",
  "message": "今晚可以在图书馆门口交易吗？"
}
```

捐赠商品：

```json
{
  "itemId": "i27",
  "tradeMethod": "自提",
  "message": "我今晚可以来取，谢谢！"
}
```

服务端校验：

1. 挂单存在且 `status = on_sale`，否则 `40901`。
2. 挂单不能属于当前用户，否则 `40300`。
3. `mode = donate` 时 `tradeMethod` 必须为 `自提`，否则 `40903`。
4. 下单成功后订单 `status = pending`，挂单 `status = reserved`，两者在同一事务内完成。
5. 订单保存 `itemId`、`productId`、`mode`、商品快照和价格快照；同款其他卖家的挂单不受影响。
6. 捐赠订单 `price = 0`。

响应 `data`：新 Order。

#### GET /orders

当前用户的订单列表。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| role | string | 是 | `buyer` / `seller` |
| status | string | 否 | `pending` / `trading` / `completed` / `cancelled` |
| mode | string | 否 | `sale` / `donate` |

响应 `data`：Order 数组，按 `createdAt` 倒序。

#### GET /orders/{id}

订单详情。仅买家或卖家本人可访问，否则 `40300`。

#### POST /orders/{id}/confirm

卖家确认交易。

- 权限：卖家本人
- 前置状态：`pending`
- 结果：`status = trading`，写入 `confirmedAt`
- 非 `pending` 返回 `40900`

响应 `data`：更新后的 Order。

#### POST /orders/{id}/complete

完成交易。

- 权限：买家或卖家本人（demo 允许双方；生产环境建议仅买家确认收货）
- 前置状态：`trading`
- 结果：订单 `status = completed`、`completedAt`；挂单 `status = sold`
- 非 `trading` 返回 `40900`

#### POST /orders/{id}/cancel

取消订单。

- 权限：买家本人
- 前置状态：`pending`
- 结果：订单 `status = cancelled`、`cancelledAt`；挂单从 `reserved` 回到 `on_sale`
- 非 `pending` 返回 `40900`

#### POST /orders/{id}/review

买家评价。

- 权限：买家本人
- 前置状态：`completed` 且 `reviewed = false`
- 请求：

```json
{
  "stars": 5,
  "tags": ["描述相符", "成色很好"],
  "text": "书和描述一致，包装也很仔细。"
}
```

- 结果：写入 `review`、`reviewed = true`
- 重复评价返回 `40900`
- 捐赠订单同样可以评价

### 5.5 卖家主页

#### GET /sellers/{id}/profile

卖家主页头部资料与统计。

响应 `data`：SellerProfile，见 3.7。

补充规则：

- `soldCount` 只统计 `mode = sale` 的已完成订单；捐赠单独计入 `donatedCount`。
- `soldAmount` 不含捐赠。
- `avgStars` 保留 2 位小数；没有评价时返回 0。
- `positiveRate` 为 4–5 星评价占比，四舍五入到整数。
- 公开页面建议对买家昵称做脱敏（如“周*”），demo 直接展示昵称。

#### GET /sellers/{id}/items

卖家在售商品。

查询参数：`status`（默认 `on_sale`）、`mode`、`page`、`pageSize`。

响应 `data`：Item 数组或分页结构。

#### GET /sellers/{id}/sold

卖家已完成的交易记录，包含捐赠。

查询参数：`page`、`pageSize`。

响应 `data`：

```json
{
  "list": [
    {
      "orderId": "ZZ20261012007",
      "itemId": "i32",
      "itemTitle": "Kindle Paperwhite 4 8G",
      "itemImg": "i2",
      "mode": "sale",
      "price": 499,
      "completedAt": "2026-10-24T10:00:00+08:00",
      "buyer": { "id": "me", "name": "奶蛙" },
      "review": { "stars": 5, "tags": ["描述相符"] }
    }
  ],
  "page": 1,
  "pageSize": 12,
  "total": 1,
  "hasMore": false
}
```

#### GET /sellers/{id}/reviews

卖家收到的交易评价，用于“评价与风评”Tab。

查询参数：`page`、`pageSize`。

响应 `data`：

```json
{
  "stats": {
    "reviewCount": 4,
    "avgStars": 4.75,
    "positiveRate": 100
  },
  "tags": [
    { "name": "沟通顺畅", "count": 3 },
    { "name": "描述相符", "count": 2 }
  ],
  "list": [
    {
      "stars": 5,
      "tags": ["描述相符", "沟通顺畅"],
      "text": "椅子很稳，卖家还帮忙搬下楼，感谢！",
      "createdAt": "2026-10-17T09:45:00+08:00",
      "buyer": { "id": "u3", "name": "周雨", "avatar": "avatar_u3.png" },
      "item": { "id": "i4", "title": "布艺单人休闲椅", "img": "i4" },
      "orderId": "ZZ20261016005"
    }
  ],
  "page": 1,
  "pageSize": 12,
  "total": 4,
  "hasMore": false
}
```

### 5.6 卖家统计

#### GET /seller/stats

卖家工作台顶部数据卡。

响应 `data`：

```json
{
  "onSaleCount": 3,
  "pendingOrderCount": 1,
  "completedAmount": 1698,
  "donatedCount": 1
}
```

| 字段 | 说明 |
| --- | --- |
| onSaleCount | 当前用户在售挂单数 |
| pendingOrderCount | 当前用户作为卖家的待确认订单数 |
| completedAmount | 当前用户作为卖家的已完成出售订单金额合计（不含捐赠） |
| donatedCount | 当前用户作为卖家的已完成捐赠订单数 |

### 5.7 元数据

#### GET /categories

返回分类、成色和流转方式枚举。

```json
{
  "categories": ["数码", "家电", "家具", "图书", "服饰", "运动", "其他"],
  "conditions": ["99新", "95新", "9成新", "8成新", "7成新"],
  "modes": [
    { "key": "sale", "label": "出售" },
    { "key": "donate", "label": "捐赠" }
  ]
}
```

## 6. 近似搜索规范

### 6.1 目标

校园二手场景里，用户经常输入不完整、有错别字或同义表达，例如：

- `macbok` → `MacBook Air`
- `平果手机` → `iPhone`
- `单车` → `公路自行车`
- `降噪耳机` → `AirPods Pro` / `Sony WH-1000XM4`

demo 在浏览器内完成轻量打分；生产环境建议使用 PostgreSQL `pg_trgm` 或 Elasticsearch。

### 6.2 前端评分逻辑（demo）

1. 归一化：转小写，去掉空格、标点和分隔符。
2. 精确匹配：字段包含完整查询串时，直接取该字段权重。
3. 中文相似度：对查询串和字段做 bigram，计算 Dice 系数。
4. 短查询补充：查询长度 2–5 时，计算字符重合率，缓解中文错别字。
5. 英文 token：按空格和分隔符切 token，对长度 ≥3 的 token 计算 Levenshtein 相似度，阈值 0.6。
6. 同义词扩展：内置同义词表，命中后把扩展词也作为匹配项。
7. 字段权重：

| 字段 | 权重 |
| --- | --- |
| 标题 | 1.00 |
| 描述 | 0.62 |
| 分类 | 0.55 |
| 成色 | 0.35 |
| 卖家昵称 | 0.25 |
| 交易地点 | 0.20 |

8. 最终分数取各字段最高分并截断到 0–1；默认阈值 `0.34`。
9. `matchType`：任一字段包含完整查询串为 `exact`，否则为 `fuzzy`。
10. 排序：有查询且用户选择“最新发布”时按分数倒序；用户选择价格排序时价格优先。

### 6.3 后端实现建议

- PostgreSQL：启用 `pg_trgm`，对 `title`、`desc`、`category` 建 GIN 索引，使用 `similarity()` 和 `%` 运算符。
- Elasticsearch：使用 `multi_match` + `fuzziness: AUTO` + `edge_ngram`，并对标题加权。
- 同义词表放配置中心，支持运营维护。
- 结果返回 `score` 和 `matchType`，便于前端展示“近似匹配”标记。
- 对空查询、纯符号查询直接返回普通列表，避免打分开销。

## 7. 状态机

### 7.1 商品（单条挂单）

```
               买家下单                卖家确认               完成交易
  on_sale ───────────────▶ reserved ───────────────▶ reserved ───────────────▶ sold
     │                        │
     │ 卖家下架                │ 买家取消
     ▼                        ▼
 off_shelf ◀──── 上架 ──── on_sale
```

规则：

- 只有 `on_sale` 可以被下单；
- 下单即锁定为 `reserved`，防止同一挂单超卖；
- 订单取消，挂单回 `on_sale`；
- 订单完成，挂单变 `sold`；
- `reserved` / `sold` 不允许上下架或编辑状态；
- 同款其他卖家的挂单不受影响，商品聚合页继续展示其他在售挂单。

### 7.2 订单

```
  pending ──卖家确认──▶ trading ──完成交易──▶ completed
     │
     └──买家取消──▶ cancelled
```

每次状态变更都必须校验前置状态，非法流转返回 `40900`。

### 7.3 捐赠

捐赠复用订单状态机，不新增状态：

- 发布时 `mode = donate`、`price = 0`；
- 下单时 `tradeMethod` 固定为 `自提`；
- 订单、评价、取消、完成规则与出售一致；
- 统计时 `soldAmount` 不含捐赠，单独统计 `donatedCount`。

## 8. Demo 与接口的映射

| Demo 函数 / 位置 | 对应接口 | 说明 |
| --- | --- | --- |
| `enterDemo()` | `POST /auth/login` | 直接进入，不请求网络 |
| `searchOffers()` / `filteredGroups()` | `GET /items?groupBy=product` | 本地过滤、同款聚合、模糊打分 |
| `scoreItem()` | `GET /items?match=fuzzy` | 本地 bigram / 编辑距离 / 同义词 |
| `getItem(id)` | `GET /items/{id}` | 从 `DB.items` 查找 |
| `sameProductOffers(item)` | `GET /items/{id}` 的 `sameProductOffers` | 同款其他卖家 |
| `startSameItem()` / `submitPublish()` | `POST /items` / `PATCH /items/{id}` | 带 `productId` 发布或编辑 |
| `toggleItemStatus(id)` | `PATCH /items/{id}/status` | 上架 / 下架 |
| `commentsForItem(id)` | `GET /items/{id}/comments` | 一级评论 + 卖家回复 |
| `submitComment(itemId)` | `POST /items/{id}/comments` | 一级评论 |
| `submitReply(commentId)` | `POST /items/{id}/comments` + `parentId` | 卖家回复 |
| `deleteComment(id)` | `DELETE /comments/{id}` | 删除自己的评论 |
| `placeOrder(itemId)` | `POST /orders` | 下单 / 申请领取，挂单变 `reserved` |
| `roleOrders()` | `GET /orders?role=` | 按当前角色过滤 |
| `confirmOrder(id)` | `POST /orders/{id}/confirm` | `pending → trading` |
| `completeOrder(id)` | `POST /orders/{id}/complete` | `trading → completed`，挂单变 `sold` |
| `cancelOrder(id)` | `POST /orders/{id}/cancel` | `pending → cancelled`，挂单回 `on_sale` |
| `submitReview()` | `POST /orders/{id}/review` | 写入评价并置 `reviewed` |
| `reviewsForItem(id)` | `GET /items/{id}/reviews` | 从订单聚合评价 |
| `sellerStats(id)` | `GET /sellers/{id}/profile` + `/reviews` | 在售、已售、捐出、好评率、标签 |
| `renderSellerProfile(id)` | `GET /sellers/{id}/profile` / `/items` / `/sold` / `/reviews` | 卖家主页三个 Tab |
| `renderSellerHome()` 中的统计 | `GET /seller/stats` | 在售、待处理、成交额、已捐出 |
| `renderChangelog()` | 无 | 站内静态版本记录，与 `CHANGELOG.md` 同步 |

## 9. 请求示例

### 9.1 同款聚合 + 近似搜索

```http
GET /api/v1/items?q=macbok&match=fuzzy&groupBy=product&page=1&pageSize=12
Authorization: Bearer <token>
```

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "list": [
      {
        "productId": "p_macbook_air",
        "title": "MacBook Air M1 8+256",
        "category": "数码",
        "mode": "sale",
        "img": "i7",
        "minPrice": 3499,
        "sellerCount": 2,
        "offerCount": 2,
        "score": 0.78,
        "matchType": "fuzzy",
        "offers": [
          {
            "id": "i24",
            "sellerId": "u4",
            "sellerName": "许知远",
            "price": 3499,
            "condition": "9成新",
            "status": "on_sale",
            "location": "西苑 2 栋"
          }
        ]
      }
    ],
    "page": 1,
    "pageSize": 12,
    "total": 1,
    "hasMore": false
  }
}
```

### 9.2 发布捐赠

```http
POST /api/v1/items
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "title": "考研英语真题 2010-2025",
  "price": 0,
  "originalPrice": 0,
  "mode": "donate",
  "category": "图书",
  "condition": "8成新",
  "img": "i18",
  "desc": "真题和答案解析都全，部分页面有铅笔笔记。毕业清宿舍，免费送给需要的同学。",
  "location": "东苑 5 栋"
}
```

### 9.3 卖家回复评论

```http
POST /api/v1/items/i7/comments
Authorization: Bearer <seller_token>
Content-Type: application/json
```

```json
{
  "content": "120 次，健康 91%。可以来北苑当面验机。",
  "parentId": "c1"
}
```

### 9.4 捐赠下单

```http
POST /api/v1/orders
Authorization: Bearer <buyer_token>
Content-Type: application/json
```

```json
{
  "itemId": "i27",
  "tradeMethod": "自提",
  "message": "我今晚可以来取，谢谢！"
}
```

### 9.5 状态冲突

```json
{
  "code": 40901,
  "message": "这件商品已经被其他买家预订",
  "data": null
}
```

## 10. 后端实现建议

1. **下单事务**：创建订单与把挂单改为 `reserved` 必须在同一事务中完成；建议对挂单行加锁或使用条件更新 `WHERE status = 'on_sale'`，避免并发超卖。
2. **同款隔离**：订单只锁定 `itemId` 对应的挂单，不要把整个 `productId` 下的其他卖家挂单一起锁定。
3. **状态校验**：所有状态变更接口先校验前置状态，再写入，不要只依赖前端按钮。
4. **权限校验**：编辑商品、确认订单、取消订单、评价、卖家回复、删除评论都必须校验当前用户与资源的归属关系。
5. **评论规则**：一级评论任意登录用户可发；卖家回复仅限该挂单卖家；每条一级评论最多一条回复；删除一级评论级联删除回复。
6. **内容安全**：评论和商品描述必须转义或做富文本白名单；建议敏感词过滤、频率限制、举报和审计。
7. **订单快照**：订单保存商品标题、图片、价格、`productId`、`mode` 快照，卖家后续改价或改同款不影响历史订单。
8. **金额**：当前约定为整数元；捐赠固定 0。如果后续支持小数，统一改为整数分。
9. **搜索**：近似搜索建议使用 `pg_trgm` 或 Elasticsearch；同义词表配置化；对搜索结果返回 `score` / `matchType`。
10. **卖家统计**：`soldCount`、`soldAmount` 排除捐赠，`donatedCount` 单独统计；统计结果可缓存，订单状态变化时失效。
11. **隐私**：公开卖家主页的交易记录和评价中，建议对买家昵称脱敏，不返回联系方式。
12. **幂等**：确认、完成、取消、评价、卖家回复在重复调用时应返回明确的冲突码，而不是重复写入。

## 11. v1 → v2 迁移说明

| 对象 | 迁移动作 |
| --- | --- |
| Item | 新增 `productId`，默认 `"p" + id`；新增 `mode`，默认 `"sale"` |
| Item | 同款商品按业务规则补相同的 `productId`；捐赠商品补 `mode = "donate"`、`price = 0` |
| Order | 新增 `productId`、`mode`、`itemTitle`、`itemImg` 快照，从关联挂单回填 |
| Comment | 新建评论表 / 集合，历史数据无评论时为空 |
| 搜索 | 为标题、描述、分类补充全文 / trigram 索引 |
| 统计 | 新增 `donatedCount`；`completedAmount` 排除捐赠 |
| 前端 | `localStorage` 从 `zz_demo_v1` 迁移到 `zz_demo_v2`，保留用户创建的商品和订单，并合并新演示数据 |
