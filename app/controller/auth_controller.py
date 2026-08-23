import os

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repository.user_repository import UserRepository
from app.repository.user_test_repository import UserTestRepository
from app.schemas.user_schema import LoginSchema, UserCreateSchema, UserResponseSchema
from app.service.user_service import UserService
from app.service.user_test_service import UserTestService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def get_auth_service(
    db: AsyncSession = Depends(get_db),
) -> UserService | UserTestService:
    mode = os.getenv("AUTH_USER_MODE", "users").lower()
    if mode == "users":
        return UserService(UserRepository(db))
    if mode == "test_users":
        return UserTestService(UserTestRepository(db))
    raise RuntimeError("AUTH_USER_MODE debe ser 'users' o 'test_users'")


@router.post("/register", response_model=UserResponseSchema, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreateSchema,
    service: UserService | UserTestService = Depends(get_auth_service),
):
    return await service.create_user(user_in)


@router.post("/login", response_model=UserResponseSchema)
async def login(
    credentials: LoginSchema,
    service: UserService | UserTestService = Depends(get_auth_service),
):
    return await service.authenticate(str(credentials.email), credentials.password)
