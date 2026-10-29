-- 专专 · 校园二手物品流转平台
-- SQLite schema v2，对应 api.md v2 契约
-- 执行方式：sqlite3 zzj.db < schema.sql   或由 app/db.py 自动执行

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- 用户
CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  avatar        TEXT,
  credit        TEXT NOT NULL DEFAULT '信用良好',
  campus        TEXT,
  joined_at     TEXT NOT NULL,
  bio           TEXT,
  password_hash TEXT
);

-- ---------------------------------------------------------------- 商品（同款归一）
-- 多卖家挂"同一件东西"时共享 product_id，市场页才能合并成一张卡
CREATE TABLE IF NOT EXISTS products (
  product_id TEXT PRIMARY KEY,
  title      TEXT NOT NULL,
  category   TEXT NOT NULL,
  mode       TEXT NOT NULL CHECK (mode IN ('sale', 'donate')),
  created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------- 挂单
CREATE TABLE IF NOT EXISTS items (
  id             TEXT PRIMARY KEY,
  product_id     TEXT NOT NULL REFERENCES products(product_id),
  seller_id      TEXT NOT NULL REFERENCES users(id),
  title          TEXT NOT NULL,
  price          INTEGER NOT NULL CHECK (price >= 0),
  original_price INTEGER CHECK (original_price IS NULL OR original_price >= 0),
  mode           TEXT NOT NULL CHECK (mode IN ('sale', 'donate')),
  category       TEXT NOT NULL,
  condition      TEXT NOT NULL CHECK (condition IN ('99新', '95新', '9成新', '8成新', '7成新')),
  img            TEXT,
  description    TEXT,            -- 对应接口里的 desc；desc 是 SQL 关键字，列名避开
  location       TEXT,
  status         TEXT NOT NULL DEFAULT 'on_sale'
                 CHECK (status IN ('on_sale', 'reserved', 'sold', 'off_shelf')),
  created_at     TEXT NOT NULL,
  -- 业务不变量：出售必定价 > 0，捐赠必 0 元
  CHECK ((mode = 'sale' AND price > 0) OR (mode = 'donate' AND price = 0))
);

-- ---------------------------------------------------------------- 订单
CREATE TABLE IF NOT EXISTS orders (
  id           TEXT PRIMARY KEY,               -- ZZ20261021001
  item_id      TEXT NOT NULL REFERENCES items(id),
  product_id   TEXT NOT NULL,
  mode         TEXT NOT NULL CHECK (mode IN ('sale', 'donate')),
  buyer_id     TEXT NOT NULL REFERENCES users(id),
  seller_id    TEXT NOT NULL REFERENCES users(id),
  price        INTEGER NOT NULL,               -- 成交价快照
  title_snap   TEXT NOT NULL,                  -- 商品标题快照
  img_snap     TEXT,                           -- 封面快照
  trade_method TEXT NOT NULL CHECK (trade_method IN ('自提', '快递')),
  message      TEXT,
  status       TEXT NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending', 'trading', 'completed', 'cancelled')),
  reviewed     INTEGER NOT NULL DEFAULT 0 CHECK (reviewed IN (0, 1)),
  created_at   TEXT NOT NULL,
  confirmed_at TEXT,
  completed_at TEXT,
  cancelled_at TEXT,
  CHECK (buyer_id <> seller_id),                                  -- 不能买自己的东西
  CHECK (mode = 'sale' OR (price = 0 AND trade_method = '自提'))    -- 捐赠只能 0 元自提
);

-- ---------------------------------------------------------------- 交易评价
CREATE TABLE IF NOT EXISTS reviews (
  id         TEXT PRIMARY KEY,
  order_id   TEXT NOT NULL UNIQUE REFERENCES orders(id),   -- UNIQUE 天然防重复评价
  item_id    TEXT NOT NULL REFERENCES items(id),
  buyer_id   TEXT NOT NULL REFERENCES users(id),
  seller_id  TEXT NOT NULL REFERENCES users(id),
  stars      INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
  content    TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_tags (
  review_id TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
  tag       TEXT NOT NULL,
  PRIMARY KEY (review_id, tag)
);

-- ---------------------------------------------------------------- 商品评论（两层）
CREATE TABLE IF NOT EXISTS comments (
  id         TEXT PRIMARY KEY,
  item_id    TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  user_id    TEXT NOT NULL REFERENCES users(id),
  parent_id  TEXT REFERENCES comments(id) ON DELETE CASCADE,
  content    TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 200),
  created_at TEXT NOT NULL
);

-- 每条一级评论最多一条卖家回复
CREATE UNIQUE INDEX IF NOT EXISTS uq_comment_single_reply
  ON comments(parent_id) WHERE parent_id IS NOT NULL;

-- 堵死第三层：父评论自身必须不是回复
CREATE TRIGGER IF NOT EXISTS trg_comment_depth
BEFORE INSERT ON comments
WHEN NEW.parent_id IS NOT NULL
BEGIN
  SELECT CASE
    WHEN (SELECT parent_id FROM comments WHERE id = NEW.parent_id) IS NOT NULL
    THEN RAISE(ABORT, '40902: 不允许三级评论')
  END;
END;

-- ---------------------------------------------------------------- 索引
CREATE INDEX IF NOT EXISTS idx_items_market   ON items(status, category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_product  ON items(product_id, mode, status);
CREATE INDEX IF NOT EXISTS idx_items_seller   ON items(seller_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_buyer   ON orders(buyer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_seller  ON orders(seller_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_item    ON orders(item_id);
CREATE INDEX IF NOT EXISTS idx_comments_item  ON comments(item_id, parent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reviews_seller ON reviews(seller_id, stars);

-- ---------------------------------------------------------------- 视图
-- 卖家统计：商品详情、卖家主页、工作台三个入口都查这个视图，
-- 保证好评率 / 成交额口径唯一（成交额不含捐赠，好评率=4–5 星占比）
DROP VIEW IF EXISTS v_seller_stats;
CREATE VIEW v_seller_stats AS
SELECT
  u.id AS seller_id,
  u.name,
  (SELECT COUNT(*) FROM items i
     WHERE i.seller_id = u.id AND i.status = 'on_sale') AS on_sale_count,
  (SELECT COUNT(*) FROM orders o
     WHERE o.seller_id = u.id AND o.status = 'completed' AND o.mode = 'sale') AS sold_count,
  (SELECT COUNT(*) FROM orders o
     WHERE o.seller_id = u.id AND o.status = 'completed' AND o.mode = 'donate') AS donated_count,
  (SELECT COALESCE(SUM(o.price), 0) FROM orders o
     WHERE o.seller_id = u.id AND o.status = 'completed' AND o.mode = 'sale') AS sold_amount,
  (SELECT COUNT(*) FROM reviews r WHERE r.seller_id = u.id) AS review_count,
  (SELECT ROUND(COALESCE(AVG(r.stars), 0), 2) FROM reviews r
     WHERE r.seller_id = u.id) AS avg_stars,
  (SELECT COALESCE(ROUND(100.0 * SUM(CASE WHEN r.stars >= 4 THEN 1 ELSE 0 END)
     / COUNT(*), 0), 0) FROM reviews r WHERE r.seller_id = u.id) AS positive_rate
FROM users u;
