from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from properties.config import DATABASE_URL

class Base(DeclarativeBase):
    pass

kwargs = {'pool_pre_ping': True}
if DATABASE_URL.startswith('sqlite'):
    kwargs['connect_args'] = {'check_same_thread': False}
engine = create_engine(DATABASE_URL, **kwargs)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)

def get_db():
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
