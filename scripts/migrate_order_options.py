from sqlalchemy import inspect, text

from database.connection import Base, engine
from models.entities import OrderItem


def main():
    Base.metadata.create_all(bind=engine)
    table = OrderItem.__tablename__

    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns(table)}
        if "options_note" not in columns:
            connection.execute(text("ALTER TABLE order_items ADD COLUMN options_note TEXT"))

    print("OK: Database da co order_items.options_note.")


if __name__ == "__main__":
    main()
