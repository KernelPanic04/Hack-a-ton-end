from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repository.user_repository import UserRepository

router = APIRouter(prefix="/users", tags=["Users"])

class UserCreate(BaseModel):
    name: str
    email: str

@router.get("/{user_id}")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"id": user.id, "name": user.name, "email": user.email}

@router.post("/")
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    new_user = await repo.create(user.model_dump())
    return {"id": new_user.id, "name": new_user.name, "email": new_user.email}