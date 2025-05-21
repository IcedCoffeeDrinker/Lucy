from fastapi import FastAPI
import sqlalchemy
import sqlite3
import databases
import os

from ulid import ULID # from 'python-ulid' module
import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'users.db')}"

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

users = sqlalchemy.Table(
    "users", metadata,
    sqlalchemy.Column("user_id",    sqlalchemy.String, unique=True),
    sqlalchemy.Column("name",  sqlalchemy.String),
    sqlalchemy.Column("phone_number", sqlalchemy.String, unique=True),
)

# Engine for sync tasks (like migrations)
engine = sqlalchemy.create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
metadata.create_all(engine)

app = FastAPI()

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.post("/database_api/create_user")
async def create_user(payload: dict):
    name = payload.get("name")
    phone_number = payload.get("phone_number")
    user_id = str(ULID.from_datetime(datetime.datetime.now()))
    query = users.insert().values(user_id=user_id, name=name, phone_number=phone_number)
    try:
        await database.execute(query)
    except sqlite3.IntegrityError:
        query = users.select().where(users.c.phone_number == phone_number)
        existing_user = await database.fetch_one(query)
        return existing_user
    return await get_user(user_id) # Check if user was created

@app.get("/database_api/get_user/{user_id}")
async def get_user(user_id: str):
    query = users.select().where(users.c.user_id == user_id)
    user = await database.fetch_one(query)
    return user

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0

if __name__ == "__main__":
    import socket
    if not is_port_in_use(5001):
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=5001, reload=True)