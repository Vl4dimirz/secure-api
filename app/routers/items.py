"""Items CRUD backed by the database. Reads are public; writes require a valid JWT."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth, schemas
from app.database import get_db
from app.models import Item

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[schemas.Item])
async def list_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).order_by(Item.id.desc()))
    return result.scalars().all()


@router.post("", response_model=schemas.Item, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: schemas.ItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(auth.get_current_user),
):
    item = Item(title=payload.title, description=payload.description)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(auth.get_current_user),
):
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
    await db.commit()
    return None
