from decimal import Decimal, ROUND_HALF_UP
from math import asin, ceil, cos, radians, sin, sqrt

BASE_FEE = 15_000
INCLUDED_KM = 2
EXTRA_KM_FEE = 3_000
PLATFORM_RATE = Decimal("0.10")
EARTH_RADIUS_KM = 6_371


def delivery_price(restaurant, latitude, longitude):
    """Trả về phí giao và khoảng cách tính bằng km."""
    if latitude is None and longitude is None:
        return BASE_FEE, None

    if latitude is None or longitude is None:
        raise ValueError("Vui lòng nhập đủ vĩ độ và kinh độ giao hàng.")

    if restaurant.latitude is None or restaurant.longitude is None:
        raise ValueError("Nhà hàng chưa có tọa độ.")

    origin_lat = radians(restaurant.latitude)
    origin_lon = radians(restaurant.longitude)
    target_lat = radians(latitude)
    target_lon = radians(longitude)

    arc = sin((target_lat - origin_lat) / 2) ** 2
    arc += cos(origin_lat) * cos(target_lat) * sin(
        (target_lon - origin_lon) / 2
    ) ** 2

    distance = 2 * EARTH_RADIUS_KM * asin(sqrt(min(1.0, arc)))
    extra_km = ceil(max(0, distance - INCLUDED_KM))
    fee = BASE_FEE + extra_km * EXTRA_KM_FEE

    return fee, round(distance, 3)


def voucher_is_valid(voucher, now):
    """Kiểm tra hiệu lực của mã tại thời điểm báo giá hoặc đặt đơn."""
    return (
        voucher is not None
        and voucher.amount > 0
        and voucher.used_at is None
        and voucher.starts_at <= now < voucher.ends_at
    )


def allocate_discount(subtotals, voucher_amount):
    """Phân bổ một mã theo thứ tự các giỏ được chọn."""
    remaining = max(0, voucher_amount)
    discounts = []

    for subtotal in subtotals:
        discount = min(max(0, subtotal), remaining)
        discounts.append(discount)
        remaining -= discount

    return discounts


def platform_fee(subtotal):
    """Tính phí nền tảng trên tiền món, làm tròn đến đồng."""
    fee = Decimal(str(subtotal)) * PLATFORM_RATE
    return int(fee.quantize(Decimal("1"), rounding=ROUND_HALF_UP))