import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models.entities import DeliveryAssignment, Payment, SubOrder, User


DISPATCH_TIMEOUT_SECONDS = 30
ACTIVE_STATUSES = ("PREPARING", "READY")
BUSY_SUBORDER_STATUSES = ("PREPARING", "READY", "DELIVERING")


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_available_drivers(db: Session):
    busy_drivers = (
        db.query(DeliveryAssignment.driver_id)
        .join(SubOrder, SubOrder.id == DeliveryAssignment.sub_order_id)
        .filter(
            DeliveryAssignment.status.in_(("OFFERED", "ACCEPTED")),
            SubOrder.status.in_(BUSY_SUBORDER_STATUSES),
        )
    )

    return (
        db.query(User)
        .filter(
            User.role == "DRIVER",
            User.status == "ACTIVE",
            User.is_online.is_(True),
            ~User.id.in_(busy_drivers),
        )
        .order_by(User.id)
        .all()
    )


def get_or_create_offer(sub_order_id, attempted_drivers, db_factory):
    with db_factory() as db:
        sub_order = (
            db.query(SubOrder)
            .filter(SubOrder.id == sub_order_id)
            .with_for_update()
            .first()
        )
        if sub_order is None:
            return None

        assignments = db.query(DeliveryAssignment).filter(
            DeliveryAssignment.sub_order_id == sub_order_id
        )

        accepted = assignments.filter(
            DeliveryAssignment.status.in_(("ACCEPTED", "COMPLETED"))
        ).first()
        if accepted is not None:
            sub_order.dispatch_status = "ASSIGNED"
            db.commit()
            return None

        if sub_order.status not in ACTIVE_STATUSES:
            return None

        existing_offer = assignments.filter(
            DeliveryAssignment.status == "OFFERED"
        ).order_by(DeliveryAssignment.assigned_at).first()
        if existing_offer is not None:
            return existing_offer.id, existing_offer.driver_id

        for candidate in get_available_drivers(db):
            if candidate.id in attempted_drivers:
                continue

            driver = (
                db.query(User)
                .filter(
                    User.id == candidate.id,
                    User.role == "DRIVER",
                    User.status == "ACTIVE",
                    User.is_online.is_(True),
                )
                .with_for_update()
                .first()
            )
            if driver is None:
                continue

            busy = (
                db.query(DeliveryAssignment.id)
                .join(SubOrder, SubOrder.id == DeliveryAssignment.sub_order_id)
                .filter(
                    DeliveryAssignment.driver_id == driver.id,
                    DeliveryAssignment.status.in_(("OFFERED", "ACCEPTED")),
                    SubOrder.status.in_(BUSY_SUBORDER_STATUSES),
                )
                .first()
            )
            if busy is not None:
                continue

            assignment = DeliveryAssignment(
                sub_order_id=sub_order.id,
                driver_id=driver.id,
                status="OFFERED",
                assigned_at=utc_now(),
            )
            sub_order.dispatch_status = "SEARCHING"
            db.add(assignment)
            db.flush()
            result = assignment.id, driver.id
            db.commit()
            return result

        sub_order.dispatch_status = "FAILED"
        db.commit()
        return None


def check_offer(assignment_id, db_factory):
    with db_factory() as db:
        assignment = db.get(DeliveryAssignment, assignment_id)
        if assignment is None:
            return "MISSING", 0

        if assignment.status != "OFFERED":
            return assignment.status, 0

        deadline = assignment.assigned_at + timedelta(seconds=DISPATCH_TIMEOUT_SECONDS)
        remaining = (deadline - utc_now()).total_seconds()

        if remaining > 0:
            return "OFFERED", remaining

        changed = db.query(DeliveryAssignment).filter(
            DeliveryAssignment.id == assignment_id,
            DeliveryAssignment.status == "OFFERED",
        ).update(
            {"status": "TIMEOUT"},
            synchronize_session=False,
        )
        db.commit()

        if changed:
            return "TIMEOUT", 0

        db.refresh(assignment)
        return assignment.status, 0


async def run_auto_dispatch_loop(sub_order_id: str, db_factory):
    attempted_drivers = set()

    while True:
        offer = await asyncio.to_thread(
            get_or_create_offer, sub_order_id, attempted_drivers, db_factory
        )
        if offer is None:
            return

        assignment_id, driver_id = offer
        attempted_drivers.add(driver_id)

        while True:
            status, remaining = await asyncio.to_thread(
                check_offer, assignment_id, db_factory
            )

            if status != "OFFERED":
                break

            await asyncio.sleep(min(1, remaining))

        if status in ("REJECTED", "TIMEOUT", "MISSING", "ACCEPTED", "COMPLETED"):
            # Đọc lại SubOrder để tìm ứng viên kế tiếp hoặc lưu ASSIGNED.
            continue

        # Ví dụ: đề nghị đã bị thu hồi khi đơn bị hủy.
        return


def trigger_refund_if_paid_online(db: Session, order_id: str):
    payment = (
        db.query(Payment)
        .filter(
            Payment.order_id == order_id,
            Payment.method == "ONLINE",
            Payment.status == "SUCCESS",
        )
        .with_for_update()
        .first()
    )

    if payment is None:
        return False

    payment.status = "REFUND_PROCESSING"
    return True