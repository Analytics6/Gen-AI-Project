from app.db import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password


def seed_user(username: str, password: str, full_name: str | None = None):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"User '{username}' already exists.")
            return

        user = User(username=username, password_hash=hash_password(password), full_name=full_name)
        db.add(user)
        db.commit()
        print(f"User '{username}' created.")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed a user in the Azure SQL users table.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", default=None)
    args = parser.parse_args()

    seed_user(args.username, args.password, args.full_name)
