from fastapi import APIRouter, Depends, status

from app.controller.user_controller import get_user_service
from app.schemas.user_schema import LoginSchema, UserCreateSchema, UserResponseSchema
from app.service.user_service import UserService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponseSchema, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreateSchema,
    service: UserService = Depends(get_user_service),
):
    return await service.create_user(user_in)


@router.post("/login", response_model=UserResponseSchema)
async def login(
    credentials: LoginSchema,
    service: UserService = Depends(get_user_service),
):
    return await service.authenticate(str(credentials.email), credentials.password)
