"""请求体模型（Pydantic）。

api.md 用的是 camelCase（originalPrice / productId / tradeMethod），
Python 习惯 snake_case，所以这里统一用 alias 做映射，
接口字段完全按文档走，代码里仍然是可读的 snake_case。
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["sale", "donate"]
Condition = Literal["99新", "95新", "9成新", "8成新", "7成新"]
Category = Literal["数码", "家电", "家具", "图书", "服饰", "运动", "其他"]


class _Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class LoginIn(_Base):
    account: str
    password: str | None = None


class ItemCreate(_Base):
    title: str = Field(min_length=1, max_length=60)
    price: int | None = Field(default=None, ge=0)
    original_price: int | None = Field(default=None, alias="originalPrice", ge=0)
    mode: Mode = "sale"
    product_id: str | None = Field(default=None, alias="productId")
    category: Category
    condition: Condition
    img: str | None = None
    desc: str | None = Field(default=None, max_length=500)
    location: str | None = None


class ItemPatch(_Base):
    title: str | None = Field(default=None, min_length=1, max_length=60)
    price: int | None = Field(default=None, ge=0)
    original_price: int | None = Field(default=None, alias="originalPrice", ge=0)
    mode: Mode | None = None
    category: Category | None = None
    condition: Condition | None = None
    img: str | None = None
    desc: str | None = Field(default=None, max_length=500)
    location: str | None = None


class StatusPatch(_Base):
    status: Literal["on_sale", "off_shelf"]


class CommentCreate(_Base):
    content: str
    parent_id: str | None = Field(default=None, alias="parentId")


class OrderCreate(_Base):
    item_id: str = Field(alias="itemId")
    trade_method: Literal["自提", "快递"] = Field(default="自提", alias="tradeMethod")
    message: str | None = Field(default=None, max_length=200)


class ReviewCreate(_Base):
    stars: int = Field(ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    text: str | None = Field(default=None, max_length=500)
