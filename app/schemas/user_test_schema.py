from pydantic import BaseModel, EmailStr, Field

class UserTestCreateSchema(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class UserTestResponseSchema(BaseModel):
    id:int
    name:str
    email:str

    class Config:
        from_attributes = True


class UserTestLoginSchema(BaseModel):
    """Solo el correo: no hay contraseña. Si el correo existe en la tabla,
    se acepta el login."""
    email: EmailStr