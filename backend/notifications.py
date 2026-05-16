from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import SessionLocal
from .deps import get_current_user
from .models import Employee, Notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_notification(db: Session, title: str, message: str, notification_type: str, recipient_id=None, created_by=None):
    notification = Notification(
        recipient_id=recipient_id,
        created_by=created_by,
        title=title,
        message=message,
        type=notification_type,
    )
    db.add(notification)
    return notification


def notify_admins(db: Session, title: str, message: str, notification_type: str, created_by=None):
    admins = db.query(Employee).filter(Employee.role.in_(["admin", "super_admin"])).all()
    for admin in admins:
        create_notification(db, title, message, notification_type, admin.id, created_by)


def notify_all_employees(db: Session, title: str, message: str, notification_type: str, created_by=None):
    employees = db.query(Employee).filter(Employee.role != "super_admin").all()
    for employee in employees:
        create_notification(db, title, message, notification_type, employee.id, created_by)


@router.get("/my")
def my_notifications(
    unread_only: bool = False,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Notification).filter(Notification.recipient_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))

    notifications = query.order_by(Notification.created_at.desc(), Notification.id.desc()).all()
    unread_count = db.query(Notification).filter(
        Notification.recipient_id == current_user.id,
        Notification.read_at.is_(None),
    ).count()

    return {
        "unread_count": unread_count,
        "notifications": [
            {
                "id": item.id,
                "title": item.title,
                "message": item.message,
                "type": item.type,
                "created_at": item.created_at,
                "read_at": item.read_at,
            }
            for item in notifications
        ],
    }


@router.get("/detail/{notification_id}")
def notification_detail(
    notification_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.recipient_id == current_user.id,
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.read_at = notification.read_at or datetime.utcnow()
    db.commit()
    db.refresh(notification)

    return {
        "id": notification.id,
        "title": notification.title,
        "message": notification.message,
        "type": notification.type,
        "created_at": notification.created_at,
        "read_at": notification.read_at,
    }


@router.put("/read-all")
def mark_all_notifications_read(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.query(Notification).filter(
        Notification.recipient_id == current_user.id,
        Notification.read_at.is_(None),
    ).update({"read_at": datetime.utcnow()}, synchronize_session=False)
    db.commit()

    return {"message": "All notifications marked as read"}


@router.put("/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.recipient_id == current_user.id,
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.read_at = notification.read_at or datetime.utcnow()
    db.commit()

    return {"message": "Notification marked as read"}


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.recipient_id == current_user.id,
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    db.delete(notification)
    db.commit()

    return {"message": "Notification deleted"}
