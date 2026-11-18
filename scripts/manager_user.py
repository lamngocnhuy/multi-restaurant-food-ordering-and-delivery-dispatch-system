import argparse
from getpass import getpass

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from api.auth import hash_password
from database.connection import SessionLocal
from models.entities import User


def main():
    parser = argparse.ArgumentParser(
        description="Cấp tài khoản nội bộ cho Food Dispatch System."
    )
    parser.add_argument("email")
    parser.add_argument("role", choices=("RESTAURANT", "DRIVER", "ADMIN"))
    parser.add_argument("--name", help="Họ tên khi tạo tài khoản mới")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Đặt lại mật khẩu cho tài khoản cùng vai trò đã tồn tại",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    name = (args.name or "").strip()

    if email.count("@") != 1 or any(char.isspace() for char in email):
        parser.error("Email không hợp lệ.")

    local_part, domain = email.split("@")
    if not local_part or "." not in domain or domain.startswith(".") or domain.endswith("."):
        parser.error("Email không hợp lệ.")

    with SessionLocal() as db:
        user = db.query(User).filter(func.lower(User.email) == email).first()

        if user is not None:
            if user.role != args.role:
                parser.error(f"Email đã thuộc vai trò {user.role}.")
            if not args.reset_password:
                parser.error("Tài khoản đã tồn tại. Dùng --reset-password để đặt lại mật khẩu.")
        elif args.reset_password:
            parser.error("Không tìm thấy tài khoản cần đặt lại mật khẩu.")
        elif not name:
            parser.error("Tài khoản mới cần có --name.")

        password = getpass("Mật khẩu mới: ")
        if not 10 <= len(password) <= 128:
            parser.error("Mật khẩu phải dài từ 10 đến 128 ký tự.")
        if password != getpass("Nhập lại mật khẩu: "):
            parser.error("Hai mật khẩu không khớp.")

        password_hash = hash_password(password)

        if user is None:
            user = User(
                email=email,
                full_name=name,
                role=args.role,
                status="ACTIVE",
                is_online=args.role == "DRIVER",
                password_hash=password_hash,
            )
            db.add(user)
            message = f"Đã tạo tài khoản {args.role} cho {email}."
        else:
            user.password_hash = password_hash
            message = f"Đã đặt lại mật khẩu cho {email}. Trạng thái tài khoản: {user.status}."

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise SystemExit("Không thể lưu tài khoản. Kiểm tra email đã được sử dụng hay chưa.") from None

    print(message)


if __name__ == "__main__":
    main()