from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Login(Input):
    email: str = Field(min_length=3,max_length=254)
    password: str = Field(min_length=1,max_length=128)
class Register(Login):
    name: str = Field(min_length=2,max_length=120)
    phone: str = Field(default='',max_length=30)
    @field_validator('email')
    @classmethod
    def email_valid(cls,v):
        if '@' not in v or '.' not in v.rsplit('@',1)[1]: raise ValueError('Enter a valid email address.')
        return v.lower()
    @field_validator('password')
    @classmethod
    def password_valid(cls,v):
        if len(v)<8: raise ValueError('Use at least 8 characters for your password.')
        return v
class CartAdd(Input):
    menu_item_id: str
    quantity: int = Field(default=1,ge=1,le=99,strict=True)
    options: dict = Field(default_factory=dict)
    note: str = Field(default='',max_length=300)
class CartEdit(Input):
    quantity: int | None = Field(default=None,ge=1,le=99,strict=True)
    options: dict | None = None
    note: str | None = Field(default=None,max_length=300)
class Quote(Input):
    address: str = Field(min_length=5,max_length=300)
    lat: float = Field(ge=-90,le=90)
    lng: float = Field(ge=-180,le=180)
    promo_code: str = Field(default='',max_length=30)
class Checkout(Quote):
    phone: str = Field(min_length=8,max_length=30)
    note: str = Field(default='',max_length=500)
    payment_method: Literal['cod','online']
    idempotency_key: str = Field(min_length=8,max_length=120)
class Reason(Input):
    reason: str = Field(default='',max_length=500)
class RestaurantStatus(Reason):
    status: Literal['accepted','rejected','preparing','ready']
class MenuCreate(Input):
    code: str = Field(min_length=1,max_length=40)
    name: str = Field(min_length=1,max_length=150)
    description: str = Field(default='',max_length=2000)
    category: str = Field(min_length=1,max_length=80)
    price: int = Field(gt=0,le=10000000,strict=True)
    image: str = Field(default='',max_length=2000)
    available: bool = True
    popular: bool = False
    options: dict = Field(default_factory=dict)
class MenuEdit(Input):
    code: str | None = Field(default=None,min_length=1,max_length=40)
    name: str | None = Field(default=None,min_length=1,max_length=150)
    description: str | None = Field(default=None,max_length=2000)
    category: str | None = Field(default=None,min_length=1,max_length=80)
    price: int | None = Field(default=None,gt=0,le=10000000,strict=True)
    image: str | None = Field(default=None,max_length=2000)
    available: bool | None = None
    popular: bool | None = None
    options: dict | None = None
class Online(Input):
    online: bool
class Location(Input):
    lat: float = Field(ge=-90,le=90)
    lng: float = Field(ge=-180,le=180)
class Pickup(Input):
    suborder_id: str
class Complete(Input):
    cod_received: bool = False
class ReviewInput(Input):
    target_type: Literal['restaurant','driver']
    target_id: str
    rating: int = Field(ge=1,le=5,strict=True)
    comment: str = Field(default='',max_length=1000)
class ConfigEdit(Input):
    max_group_distance_km: float | None = Field(default=None,gt=0,le=50)
    dispatch_radius_km: float | None = Field(default=None,gt=0,le=100)
    base_delivery_fee: int | None = Field(default=None,ge=0,le=100000,strict=True)
    per_km_fee: int | None = Field(default=None,ge=0,le=100000,strict=True)
    commission_rate: float | None = Field(default=None,ge=0,le=0.5)
class AccountEdit(Input):
    active: bool
class ProfileEdit(Input):
    accepting_orders: bool
class Resolve(Reason):
    action: Literal['cancel','retry_dispatch']
class Sandbox(Input):
    outcome: Literal['success','failure']
class Callback(Input):
    payment_id: str
    outcome: Literal['success','failure']
    external_reference: str = Field(min_length=1,max_length=120)
class Reconcile(Input):
    include_current: bool = False

class RestaurantProvision(Input):
    name: str = Field(min_length=2,max_length=150)
    description: str = Field(default='',max_length=2000)
    category: str = Field(min_length=1,max_length=80)
    address: str = Field(min_length=5,max_length=300)
    lat: float = Field(ge=-90,le=90)
    lng: float = Field(ge=-180,le=180)
    image: str = Field(default='',max_length=2000)
class AccountCreate(Register):
    role: Literal['customer','restaurant','driver','admin']
    restaurant: RestaurantProvision | None = None
