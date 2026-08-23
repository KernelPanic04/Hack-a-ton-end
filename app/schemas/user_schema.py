from pydantic import BaseModel, EmailStr, Field

class UserCreateSchema(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class LoginSchema(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class UserResponseSchema(BaseModel):
    id:int
    name:str
    email:str

    class Config:
        from_attributes = True
