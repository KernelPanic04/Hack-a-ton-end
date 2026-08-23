from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import UserModel
from app.repository.base import BaseRepository

class UserRepository(BaseRepository[UserModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserModel, session)

    # Here we add personalized queries specific to this entity
    # Aquí agregas consultas personalizadas específicas de esta entidad
"""
    async def get_by_email(self, email: str) -> User | None:
        query = select(User).where(User.email == email)
        result = await self.session.execute(query)
        return result.scalars().first()
"""