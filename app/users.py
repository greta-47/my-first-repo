from __future__ import annotations

from typing import Dict, Generator, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import SessionLocal, engine, users_table

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    created_at: str
    is_active: bool


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user: UserCreate, db: Session = Depends(get_db), current_user: Dict = Depends(get_current_user)
) -> UserResponse:
    from datetime import datetime, timezone

    stmt = select(users_table).where(users_table.c.email == user.email)
    with engine.connect() as conn:
        existing = conn.execute(stmt).fetchone()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User with this email already exists"
        )

    created_at = datetime.now(timezone.utc).isoformat()

    insert_stmt = insert(users_table).values(
        email=user.email, full_name=user.full_name, created_at=created_at, is_active=1
    )

    with engine.connect() as conn:
        result = conn.execute(insert_stmt)
        conn.commit()
        user_id = result.inserted_primary_key[0]

    return UserResponse(
        id=user_id,
        email=user.email,
        full_name=user.full_name,
        created_at=created_at,
        is_active=True,
    )


@router.get("/me", response_model=Dict)
async def get_current_user_info(current_user: Dict = Depends(get_current_user)) -> Dict:
    return current_user


@router.get("/", response_model=List[UserResponse])
async def list_users(
    db: Session = Depends(get_db), current_user: Dict = Depends(get_current_user)
) -> List[UserResponse]:
    stmt = select(users_table).order_by(users_table.c.created_at.desc())

    with engine.connect() as conn:
        rows = conn.execute(stmt).fetchall()

    return [
        UserResponse(
            id=row.id,
            email=row.email,
            full_name=row.full_name,
            created_at=row.created_at,
            is_active=bool(row.is_active),
        )
        for row in rows
    ]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int, db: Session = Depends(get_db), current_user: Dict = Depends(get_current_user)
) -> UserResponse:
    stmt = select(users_table).where(users_table.c.id == user_id)

    with engine.connect() as conn:
        row = conn.execute(stmt).fetchone()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return UserResponse(
        id=row.id,
        email=row.email,
        full_name=row.full_name,
        created_at=row.created_at,
        is_active=bool(row.is_active),
    )
