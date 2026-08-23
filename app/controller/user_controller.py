from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repository.user_repository import UserRepository
from app.service.user_service import UserService
from app.schemas.user_schema import UserCreateSchema, UserResponseSchema

router = APIRouter(prefix="/users", tags=["Users"])

# Dependency factory function
def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    repo = UserRepository(db)
    return UserService(repo)

@router.get("/{user_id}", response_model=UserResponseSchema)
async def get_user(
    user_id: int, 
    service: UserService = Depends(get_user_service)
):
    return await service.get_user_by_id(user_id)

@router.get("/", response_model=list[UserResponseSchema])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    service: UserService = Depends(get_user_service)
):
    return await service.get_all_users(skip=skip, limit=limit)

@router.post("/", response_model=UserResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreateSchema, 
    service: UserService = Depends(get_user_service)
):
    return await service.create_user(user_in)

@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    service: UserService = Depends(get_user_service)
):
    return await service.delete_user(user_id)