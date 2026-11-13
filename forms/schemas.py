from pydantic import BaseModel, Field
from typing import Optional

# 1. Bước mẫu kiểm tra dữ liệu khi Thêm món vào giỏ hàng (REQ-4 -> REQ-9, BR04)
class AddToCartForm(BaseModel):
    customer_id : str
    food_id : str
    quantity : int = Field(gt=0, description="Số lượng món phải lớn hơn 0 (BR04)")
    size_extra: float = Field(ge=0, default=0.0, description="Phụ thu kích cỡ (Size)")
    topping_extra: float = Field(ge=0, default=0.0, description="Phụ thu topping")
    options_note :Optional[str] = ""
    force_reset_cart: bool = False # True khi khách đồng ý xóa giỏ cũ ở Pop-up REQ-9
# 2. Biểu mẫu kiểm tra dữ liệu khi Đặt hàng / Checkout (DT-ORD-01, DT-ORD-02)
class CheckoutForm(BaseModel):
    customer_id: str
    delivery_address : str = Field(min_length=5, description="Địa chỉ giao hàng không được trống")
    payment_method: str = Field(pattern="^(COD|ONLINE)$", description="Chỉ chấp nhận COD hoặc ONLINE")

# 3. Biểu mẫu cập nhật trạng thái đơn hàng
class OrderStatusForm(BaseModel):
    status : str
    reason: Optional[str] = None