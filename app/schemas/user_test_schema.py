from pydantic import BaseModel, EmailStr

class UserTestCreateSchema(BaseModel):
    name : str
    email : EmailStr

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
