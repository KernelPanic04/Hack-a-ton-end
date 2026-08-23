from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user_test import UserTestModel
from app.repository.base import BaseRepository

class UserTestRepository(BaseRepository[UserTestModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserTestModel, session)