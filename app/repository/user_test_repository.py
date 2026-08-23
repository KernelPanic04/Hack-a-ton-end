from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.user_test import UserTestModel
from app.repository.base import BaseRepository

class UserTestRepository(BaseRepository[UserTestModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserTestModel, session)

    async def get_by_email(self, email: str) -> Optional[UserTestModel]:
        query = select(UserTestModel).where(UserTestModel.email == email)
        result = await self.session.execute(query)
        return result.scalars().first()
