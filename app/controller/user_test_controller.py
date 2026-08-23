from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repository.user_test_repository import UserTestRepository
from app.service.user_test_service import UserTestService
from app.schemas.user_test_schema import UserTestCreateSchema, UserTestResponseSchema, UserTestLoginSchema

router = APIRouter(prefix="/users_test", tags=["Users_test"])

# Dependency factory function
def get_user_service(db: AsyncSession = Depends(get_db)) -> UserTestService:
    repo = UserTestRepository(db)
    return UserTestService(repo)

@router.post("/login", response_model=UserTestResponseSchema)
async def login(
    credentials: UserTestLoginSchema,
    service: UserTestService = Depends(get_user_service)
):
    # Debe declararse antes de /{user_id}; de lo contrario Starlette intenta
    # interpretar "login" como el identificador dinámico y responde 422.
    return await service.authenticate(str(credentials.email), credentials.password)

@router.get("/{user_id}", response_model=UserTestResponseSchema)
async def get_user(
    user_id: int,
    service: UserTestService = Depends(get_user_service)
):
    return await service.get_user_by_id(user_id)

@router.get("/", response_model=list[UserTestResponseSchema])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    service: UserTestService = Depends(get_user_service)
):
    return await service.get_all_users(skip=skip, limit=limit)

@router.post("/", response_model=UserTestResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserTestCreateSchema,
    service: UserTestService = Depends(get_user_service)
):
    return await service.create_user(user_in)

@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    service: UserTestService = Depends(get_user_service)
):
    return await service.delete_user(user_id)
