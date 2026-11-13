import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Mặc định dùng SQLite để chạy demo nhanh; hỗ trợ chuyển sang PostgreSQL qua biến môi trường
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./multi_restaurant.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else{}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()