import json
from pathlib import Path
from urllib.parse import urlencode

from sqlalchemy import inspect, text

from database.connection import Base, SessionLocal, engine
from models.entities import FoodItem, Restaurant, User


MENU_FILE = Path(__file__).with_name("menu.json")


def load_catalog():
    catalog = json.loads(MENU_FILE.read_text(encoding="utf-8-sig"))

    for restaurant in catalog:
        for item in restaurant["items"]:
            if item["category"] not in {"FOOD", "DRINK"}:
                raise ValueError(f'Phân loại không hợp lệ cho {item["name"]}')
            if type(item["price"]) is not int or item["price"] <= 0:
                raise ValueError(f'Giá không hợp lệ cho {item["name"]}')

    return catalog


def ensure_category_column():
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("food_items")
        }

        if "category" not in columns:
            connection.execute(text(
                "ALTER TABLE food_items "
                "ADD COLUMN category VARCHAR(16) NOT NULL DEFAULT 'FOOD'"
            ))


def main():
    catalog = load_catalog()
    ensure_category_column()
    added = 0

    with SessionLocal() as db:
        for entry in catalog:
            owner = db.query(User).filter_by(email=entry["email"]).one_or_none()

            if owner is None:
                owner = User(
                    email=entry["email"],
                    full_name=f'Chủ quán {entry["name"]}',
                    role="RESTAURANT",
                    status="ACTIVE",
                    password_hash="disabled-demo-account",
                )
                db.add(owner)
                db.flush()
            elif owner.role != "RESTAURANT":
                raise ValueError(f'Email đã thuộc vai trò khác: {entry["email"]}')

            restaurant = db.query(Restaurant).filter_by(
                owner_id=owner.id,
                name=entry["name"],
            ).one_or_none()

            if restaurant is None:
                restaurant = Restaurant(
                    owner_id=owner.id,
                    name=entry["name"],
                    address=entry["address"],
                    status="OPEN",
                )
                db.add(restaurant)
                db.flush()

            existing_names = {
                name for (name,) in db.query(FoodItem.name).filter_by(
                    restaurant_id=restaurant.id
                )
            }

            for item in entry["items"]:
                if item["name"] in existing_names:
                    continue

                placeholder = "https://placehold.co/600x400/png?" + urlencode({
                    "text": item["name"],
                })
                db.add(FoodItem(
                    restaurant_id=restaurant.id,
                    name=item["name"],
                    price=item["price"],
                    category=item["category"],
                    status="IN_STOCK",
                    image_url=item.get("image_url") or placeholder,
                ))
                existing_names.add(item["name"])
                added += 1

        db.commit()

    print(f"OK: Da them {added} mon tu {MENU_FILE.name}.")


if __name__ == "__main__":
    main()