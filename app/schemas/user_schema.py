from pydantic import BaseModel, EmailStr

class UserCreateSchema(BaseModel):
    name : str
    email : EmailStr

class UserResponseSchema(BaseModel):
    id:int
    name:str
    email:str

    class Config:
        from_attributes = True