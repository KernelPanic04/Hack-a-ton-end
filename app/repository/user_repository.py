from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import UserModel
from app.repository.base import BaseRepository

class UserRepository(BaseRepository[UserModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserModel, session)

    async def get_by_email(self, email: str) -> UserModel | None:
        query = select(UserModel).where(UserModel.email == email.lower())
        result = await self.session.execute(query)
        return result.scalars().first()
