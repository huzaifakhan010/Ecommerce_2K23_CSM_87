"""Pydantic request/response schemas. API validation is the first line of defence;
the database constraints (app/models.py) are the last."""
import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN, min_length=2, max_length=120)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
CategoryName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]
Money = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


def _normalize_code(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


# SKU codes are normalised to upper case so uniqueness is effectively case-insensitive.
SkuCode = Annotated[str, BeforeValidator(_normalize_code), StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9-]{2,63}$")]

ProductStatus = Literal["draft", "published", "archived"]
CustomizationType = Literal["print", "embroidery", "engraving"]

# --------------------------------------------------------------------------- validation rules
SPEC_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
OPTION_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,29}$")


def validate_specifications(value: dict) -> dict:
    """Written rule: a JSON object with <= 20 snake_case keys; each value is a string (<= 200 chars),
    a number, a boolean, or a list (<= 20) of those scalars. Nested objects are rejected."""
    if len(value) > 20:
        raise ValueError("specifications may contain at most 20 keys")
    for key, item in value.items():
        if not SPEC_KEY_RE.match(key):
            raise ValueError(f"invalid specification key '{key}' (use snake_case, max 40 chars)")
        scalars = item if isinstance(item, list) else [item]
        if isinstance(item, list) and len(item) > 20:
            raise ValueError(f"specification '{key}' has more than 20 list items")
        for scalar in scalars:
            if isinstance(scalar, (bool, int, float)):
                continue
            if isinstance(scalar, str) and len(scalar) <= 200:
                continue
            raise ValueError(f"specification '{key}' must hold strings, numbers, booleans or lists of them")
    return value


def validate_option_values(value: Optional[dict]) -> Optional[dict]:
    """1-3 options; keys are snake_case; values are non-empty strings (<= 50 chars)."""
    if value is None:
        return value
    if not 1 <= len(value) <= 3:
        raise ValueError("option_values must contain between 1 and 3 options")
    cleaned = {}
    for key, item in value.items():
        if not OPTION_KEY_RE.match(key):
            raise ValueError(f"invalid option name '{key}' (use lowercase snake_case)")
        item = item.strip()
        if not 1 <= len(item) <= 50:
            raise ValueError(f"option '{key}' must have a value of 1-50 characters")
        cleaned[key] = item
    return cleaned


def reject_nulls(model: BaseModel, nullable: tuple = ()) -> None:
    """Update schemas: a field that was sent may not be null (except the ones listed in `nullable`)."""
    for field in model.model_fields_set:
        if getattr(model, field) is None and field not in nullable:
            raise ValueError(f"{field} cannot be null")


# --------------------------------------------------------------------------- auth
class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: Email
    password: str = Field(min_length=8, max_length=72)
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: Email
    password: str = Field(min_length=1, max_length=72)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(OrmModel):
    id: int
    email: str
    full_name: str
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --------------------------------------------------------------------------- categories
class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: CategoryName
    slug: Slug
    parent_id: Optional[int] = None


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[CategoryName] = None
    slug: Optional[Slug] = None
    parent_id: Optional[int] = None  # null is allowed: it moves the category to the top level
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def _no_nulls(self):
        reject_nulls(self, nullable=("parent_id",))
        return self


class CategoryOut(OrmModel):
    id: int
    parent_id: Optional[int]
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryNode(CategoryOut):
    children: list["CategoryNode"] = []


# --------------------------------------------------------------------------- products
class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # status is not accepted: new products are always drafts
    category_id: int
    name: Name
    slug: Slug
    description: str = Field(default="", max_length=5000)
    customization_type: CustomizationType = "print"
    specifications: dict[str, Any] = Field(default_factory=dict)

    @field_validator("specifications")
    @classmethod
    def _check_specs(cls, value):
        return validate_specifications(value)


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: Optional[int] = None
    name: Optional[Name] = None
    slug: Optional[Slug] = None
    description: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[ProductStatus] = None
    customization_type: Optional[CustomizationType] = None
    specifications: Optional[dict[str, Any]] = None

    @field_validator("specifications")
    @classmethod
    def _check_specs(cls, value):
        return validate_specifications(value) if value is not None else value

    @model_validator(mode="after")
    def _no_nulls(self):
        reject_nulls(self)
        return self


# --------------------------------------------------------------------------- variants & SKUs
class VariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_values: dict[str, str]

    @field_validator("option_values")
    @classmethod
    def _check_options(cls, value):
        return validate_option_values(value)


class VariantOut(OrmModel):
    id: int
    product_id: int
    option_values: dict[str, str]
    created_at: datetime


class SkuCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: SkuCode
    price: Money
    stock_quantity: int = Field(default=0, ge=0)
    is_active: bool = True
    variant_id: Optional[int] = None
    option_values: Optional[dict[str, str]] = None

    @field_validator("option_values")
    @classmethod
    def _check_options(cls, value):
        return validate_option_values(value)

    @model_validator(mode="after")
    def _one_variant_reference(self):
        if self.variant_id is not None and self.option_values is not None:
            raise ValueError("send either variant_id or option_values, not both")
        return self


class SkuUpdate(BaseModel):
    """The SKU code is immutable (it is the identity other tables will reference)."""

    model_config = ConfigDict(extra="forbid")
    price: Optional[Money] = None
    stock_quantity: Optional[int] = Field(default=None, ge=0)
    stock_delta: Optional[int] = Field(default=None, ge=-1_000_000, le=1_000_000)
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def _consistent(self):
        reject_nulls(self)
        if not self.model_fields_set:
            raise ValueError("send at least one of price, stock_quantity, stock_delta, is_active")
        if self.stock_quantity is not None and self.stock_delta is not None:
            raise ValueError("send either stock_quantity or stock_delta, not both")
        return self


class SkuOut(OrmModel):
    id: int
    product_id: int
    variant_id: Optional[int]
    code: str
    price: Decimal
    stock_quantity: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def availability(self) -> str:
        if not self.is_active:
            return "inactive"
        return "in_stock" if self.stock_quantity > 0 else "out_of_stock"


class ProductOut(OrmModel):
    id: int
    category_id: int
    name: str
    slug: str
    description: str
    status: str
    customization_type: str
    specifications: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    variants: list[VariantOut]
    skus: list[SkuOut]


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    limit: int
    offset: int
