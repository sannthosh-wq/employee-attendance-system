from fastapi import FastAPI
from database import engine, Base
import auth, attendance, admin

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(auth.router,prefix="/admin")
app.include_router(attendance.router)
app.include_router(admin.router)

@app.get("/")
def home():
    return {"message": "Attendance System API Running"}