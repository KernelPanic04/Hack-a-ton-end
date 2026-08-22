from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["Users"])

# DTO (Schema) de Pydantic para el cuerpo del POST
class UserCreate(BaseModel):
    name: str
    email: str

@router.get("/")
def read_root():
    return {"Hello": "World"}

@router.get("/{user_id}")
def get_user(user_id: int):
    # Aquí la capa Service/Repo buscará al usuario
    return {"user_id": user_id}

@router.post("/")
def create_user(user: UserCreate):
    # Aquí la capa Service/Repo creará al usuario
    return {"user_name": user.name, "email": user.email}