from app.chroma_store import store
from app.security import hash_password


def seed_user(username: str, password: str, full_name: str | None = None, update_if_exists: bool = False):
    existing = store.get_user_by_username(username)
    if existing and not update_if_exists:
        print(f"User '{username}' already exists.")
        return

    if existing and update_if_exists:
        store.update_user_password(username=username, password_hash=hash_password(password))
        print(f"User '{username}' password updated.")
        return

    store.create_user(username=username, password_hash=hash_password(password), full_name=full_name)
    print(f"User '{username}' created.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed a user in ChromaDB users collection.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", default=None)
    parser.add_argument("--update-if-exists", action="store_true")
    args = parser.parse_args()

    seed_user(args.username, args.password, args.full_name, args.update_if_exists)
