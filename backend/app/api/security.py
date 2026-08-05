"""认证接口: 登录 / 当前用户."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.security.auth import CurrentUser, CurrentUserDep, authenticate, create_token

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: CurrentUser


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    user = authenticate(payload.username, payload.password)
    return LoginResponse(access_token=create_token(user), user=user)


@router.get("/me", response_model=CurrentUser)
async def me(user: CurrentUserDep) -> CurrentUser:
    return user
