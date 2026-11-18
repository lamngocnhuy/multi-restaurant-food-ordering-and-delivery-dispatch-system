from sqlalchemy import inspect, text

from database.connection import engine


def main():
    with engine.begin() as connection:
        inspector = inspect(connection)

        if not inspector.has_table("sub_orders"):
            print("Chua co bang sub_orders. FastAPI se tao bang khi khoi dong.")
            return

        columns = {column["name"] for column in inspector.get_columns("sub_orders")}
        if "dispatch_status" in columns:
            print("Cot sub_orders.dispatch_status da ton tai.")
            return

        connection.execute(text(
            "ALTER TABLE sub_orders ADD COLUMN dispatch_status VARCHAR"
        ))

    print("Da them cot sub_orders.dispatch_status.")


if __name__ == "__main__":
    main()