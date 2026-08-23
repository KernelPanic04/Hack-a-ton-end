from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user_test import UserTestModel
from app.repository.base import BaseRepository

class UserTestRepository(BaseRepository[UserTestModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserTestModel, session)

    async def get_by_email(self, email: str) -> UserTestModel | None:
        query = select(UserTestModel).where(UserTestModel.email == email.lower())
        result = await self.session.execute(query)
        return result.scalars().first()
