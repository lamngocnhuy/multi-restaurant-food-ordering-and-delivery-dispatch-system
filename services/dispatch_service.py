import asyncio
from sqlalchemy.orm import Session
from models.entities import User, SubOrder, DeliveryAssignment, Payment

# ====== Cấu hình ======
# Số giây chờ tài xế phản hồi. Demo để 5, khi nộp báo cáo để 30 (khớp DT-DRV-02)
DISPATCH_TIMEOUT_SECONDS = 30

# Trạng thái đơn còn cần tìm tài xế
ACTIVE_STATUSES = ["PREPARING", "READY"]

# Trạng thái đơn mà tài xế được coi là đang bận
BUSY_SUBORDER_STATUSES = ["PREPARING", "READY", "DELIVERING"]


# 1. Tìm danh sách tài xế Online, sẵn sàng và KHÔNG đang bận đơn khác
def get_available_drivers(db: Session):
    busy_ids = [
        row[0]
        for row in db.query(DeliveryAssignment.driver_id)
        .join(SubOrder, SubOrder.id == DeliveryAssignment.sub_order_id)
        .filter(
            DeliveryAssignment.status == "ACCEPTED",
            SubOrder.status.in_(BUSY_SUBORDER_STATUSES),
        )
        .all()
    ]

    query = db.query(User).filter(
        User.role == "DRIVER",
        User.status == "ACTIVE",
        User.is_online == True,
    )
    # Chỉ loại trừ khi có tài xế bận (tránh NOT IN với danh sách rỗng)
    if busy_ids:
        query = query.filter(~User.id.in_(busy_ids))

    return query.all() or []


# 2. Điều phối tài xế tự động, vòng lặp đếm ngược (ST-02)
async def run_auto_dispatch_loop(sub_order_id: str, db_factory):
    db: Session = db_factory()
    try:
        sub_order = db.query(SubOrder).filter(SubOrder.id == sub_order_id).first()
        if not sub_order or sub_order.status not in ACTIVE_STATUSES:
            return

        sub_order.dispatch_status = "SEARCHING"
        db.commit()

        drivers = get_available_drivers(db)
        if not drivers:
            # DT-DRV-03: không có tài xế -> báo thất bại để giao diện hiện cảnh báo
            sub_order.dispatch_status = "FAILED"
            db.commit()
            print(f"[DISPATCH] Không có tài xế khả dụng cho đơn {sub_order_id}")
            return

        for driver in drivers:
            # Làm mới trạng thái đơn: nếu bị hủy giữa chừng thì dừng ngay
            db.refresh(sub_order)
            if sub_order.status not in ACTIVE_STATUSES:
                print(f"[DISPATCH] Đơn {sub_order_id} không còn cần tài xế, dừng điều phối.")
                return

            # Đơn đã có tài xế nhận thì dừng
            existing_accepted = db.query(DeliveryAssignment).filter(
                DeliveryAssignment.sub_order_id == sub_order_id,
                DeliveryAssignment.status == "ACCEPTED",
            ).first()
            if existing_accepted:
                return

            # Tạo đề nghị giao hàng gửi tới tài xế
            assignment = DeliveryAssignment(
                sub_order_id=sub_order_id,
                driver_id=driver.id,
                status="OFFERED",
            )
            db.add(assignment)
            db.commit()
            db.refresh(assignment)
            print(f"[DISPATCH] Đã gửi đề nghị tới Tài xế {driver.full_name} (đợi phản hồi)...")

            # Chờ phản hồi, mỗi giây kiểm tra một lần
            for _ in range(DISPATCH_TIMEOUT_SECONDS):
                await asyncio.sleep(1)
                db.refresh(assignment)
                if assignment.status == "ACCEPTED":
                    sub_order.dispatch_status = "ASSIGNED"
                    db.commit()
                    print(f"[DISPATCH] Tài xế {driver.full_name} ĐÃ NHẬN ĐƠN!")
                    return
                if assignment.status in ("REJECTED", "CANCELLED"):
                    break  # Từ chối hoặc đơn bị hủy -> thoát vòng đếm

            # Hết giờ mà chưa phản hồi -> TIMEOUT, chuyển tài xế kế tiếp
            if assignment.status == "OFFERED":
                assignment.status = "TIMEOUT"
                db.commit()
                print(f"[DISPATCH] Tài xế {driver.full_name} quá hạn phản hồi -> chuyển tài xế kế tiếp.")

        # Đã hỏi hết tài xế mà không ai nhận -> báo thất bại (DT-DRV-04 dùng trạng thái này)
        db.refresh(sub_order)
        if sub_order.status in ACTIVE_STATUSES:
            sub_order.dispatch_status = "FAILED"
            db.commit()
            print(f"[DISPATCH] Hết tài xế cho đơn {sub_order_id}.")
    finally:
        db.close()


# 3. Tự động kích hoạt hoàn tiền nếu đơn thanh toán ONLINE bị hủy (ST-09)
def trigger_refund_if_paid_online(db: Session, order_id: str):
    payment = db.query(Payment).filter(Payment.order_id == order_id).first()
    # Chỉ hoàn khi đã thanh toán thành công; nếu đã REFUND_PROCESSING thì bỏ qua
    if payment and payment.method == "ONLINE" and payment.status == "SUCCESS":
        payment.status = "REFUND_PROCESSING"
        db.commit()
        return True
    return False