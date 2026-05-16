from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .attrition_service import model_status, predict_attrition
from .database import SessionLocal
from .deps import get_current_user

router = APIRouter(prefix="/ml", tags=["Machine Learning"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(user):
    if user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/attrition")
def attrition_predictions(
    store: bool = True,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)
    return predict_attrition(db, store=store)


@router.get("/attrition/model-status")
def attrition_model_status(current_user=Depends(get_current_user)):
    require_admin(current_user)
    return model_status()
