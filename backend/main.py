from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base

import auth
import attendance
import admin
import leave
import employee

Base.metadata.create_all(bind=engine)

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(attendance.router)
app.include_router(admin.router)
app.include_router(leave.router)
app.include_router(employee.router)

@app.get("/")
def home():
    return {"message": "Attendance System API Running"}