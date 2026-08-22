from fastapi import FastAPI

HackatonApp = FastAPI()

@HackatonApp.get("/")
def read_root():
    return {"Hello": "World"}

@HackatonApp.get("/getUser/{user_id}")
def getUserService(user_id: int):
    return {"user_id": user_id}

@HackatonApp.put("/addUser/{user_name}")
def putUserService(user_name):
    return {"user_name": user_name}