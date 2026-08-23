from typing import List
from fastapi import HTTPException, status

from app.repository.user_test_repository import UserTestRepository
from app.schemas.user_test_schema import UserTestCreateSchema, UserTestResponseSchema  

class UserTestService:
    def __init__(self, repository: UserTestRepository):
        self.repository = repository

    async def get_user_by_id(self, user_id: int):
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Usuario no encontrado"
            )
        return user

    async def get_all_users(self, skip: int = 0, limit: int = 100) -> List:
        return await self.repository.get_all(skip=skip, limit=limit)

    async def create_user(self, user_in: UserTestCreateSchema):
        # Business Logic Example: Check duplicate email
        existing_user = await self.repository.get_by_email(user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo electrónico ya está registrado"
            )
        return await self.repository.create(user_in.model_dump())

    async def delete_user(self, user_id: int):
        success = await self.repository.delete(user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        return {"message": "Usuario eliminado exitosamente"}