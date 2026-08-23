from typing import List
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.security import password_hash
from app.repository.user_repository import UserRepository
from app.schemas.user_schema import UserCreateSchema, UserResponseSchema

class UserService:
    def __init__(self, repository: UserRepository):
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

    async def create_user(self, user_in: UserCreateSchema):
        data = user_in.model_dump()
        plain_password = data.pop("password")
        normalized_email = str(data["email"]).strip().lower()
        existing_user = await self.repository.get_by_email(normalized_email)
        if existing_user:
            # Las cuentas creadas por la versión antigua no tenían contraseña.
            # Permitir registrarlas una vez más sirve como migración segura para
            # el hackathon sin asignar una contraseña global conocida.
            if not existing_user.password_hash:
                return await self.repository.update(existing_user, {
                    "name": data["name"],
                    "email": normalized_email,
                    "password_hash": password_hash.hash(plain_password),
                })
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El correo electrónico ya está registrado"
            )
        data["email"] = normalized_email
        data["password_hash"] = password_hash.hash(plain_password)
        try:
            return await self.repository.create(data)
        except IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El correo electrónico ya está registrado",
            ) from error

    async def authenticate(self, email: str, password: str):
        user = await self.repository.get_by_email(email.strip().lower())
        if not user or not user.password_hash or not password_hash.verify(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Correo o contraseña incorrectos",
            )
        return user

    async def delete_user(self, user_id: int):
        success = await self.repository.delete(user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        return {"message": "Usuario eliminado exitosamente"}
