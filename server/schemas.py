# server/schemas.py
from pydantic import BaseModel, Field

class RegisterIn(BaseModel):
    nickname: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=4, max_length=64)

class RegisterOut(BaseModel):
    user_id: str
    token: str
    nickname: str

class LoginIn(BaseModel):
    nickname: str
    password: str

class LoginOut(BaseModel):
    user_id: str
    token: str
    nickname: str

class CreateRoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)

class RoomListOut(BaseModel):
    rooms: dict[str, int]

class RoomInfoOut(BaseModel):
    exists: bool
    name: str | None = None
    member_count: int | None = None
    members: list[str] | None = None
