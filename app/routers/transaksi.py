from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List

from app.core.database import get_db
from app.core.limiter import limiter
from app.core.config import settings
from app.core.security import machine_validate, get_current_user
from app.models import User, Transaction
from app.schemas import TransactionCreate, TransactionResponse, TransactionHistory
from app.services.sheets import push_to_sheet, ws_trans

router=APIRouter()

HARGA_BOTOL_KECIL=settings.HARGA_BOTOL_KECIL
HARGA_BOTOL_SEDANG=settings.HARGA_BOTOL_SEDANG
HARGA_BOTOL_BESAR=settings.HARGA_BOTOL_BESAR

@router.post("/transactions/", response_model=TransactionResponse)
@limiter.limit("60/minute")
def Record_Transaction(request: Request, data: TransactionCreate, background_tasks: BackgroundTasks, db: Session= Depends(get_db), kunci: str = Depends(machine_validate)):
    user= db.query(User).filter(User.username==data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan. Username atau akun anda belum terdaftar di sistem GCM")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Akun belum diverifikasi. Selesaikan verifikasi nomor telepon sebelum melanjutkan transaksi")
    
    bottle_small_point=data.bottle_small*HARGA_BOTOL_KECIL
    bottle_medium_point=data.bottle_medium*HARGA_BOTOL_SEDANG
    bottle_large_point=data.bottle_large*HARGA_BOTOL_BESAR
    total_point= bottle_small_point + bottle_medium_point + bottle_large_point
    new_transaction=Transaction(
        user_id=user.id,
        bottle_small=data.bottle_small,
        bottle_medium=data.bottle_medium,
        bottle_large=data.bottle_large,
        points= total_point
        )
    db.add(new_transaction)
    db.commit()
    db.refresh(new_transaction)

    row_data=[
        new_transaction.id,
        (datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S")),
        user.username,
        user.name,
        data.bottle_small,
        data.bottle_medium,
        data.bottle_large,
        total_point

    ]

    background_tasks.add_task(push_to_sheet, ws_trans,row_data)
    return {
        "id": new_transaction.id,
        "user_id": new_transaction.user_id,
        "points": new_transaction.points,
        "created_at": new_transaction.created_at,
        "message": f"Berhasil! Kecil: {data.bottle_small}, Sedang: {data.bottle_medium}, Besar: {data.bottle_large} botol ditukar dengan {total_point} point"
    }

@router.get("/transaction/history", response_model=List[TransactionHistory])
def get_history_transaksi(skip: int = Query(0, ge=0), limit: int=Query(20, ge=1, le=100), db:Session=Depends(get_db), current_user:User=Depends(get_current_user)):
    return db.query(Transaction).filter(Transaction.user_id==current_user.id).order_by(desc(Transaction.created_at)).offset(skip).limit(limit).all()


@router.get("/leaderboard/")
def get_leaderboard(db: Session=Depends(get_db)):
    top_contributors=db.query(
        User.username,
        User.name,
        func.sum(Transaction.points).label('total_points')
    ). join(Transaction).group_by(User.id).order_by(desc('total_points')).limit(10).all()

    ranking=[]
    for index, contributor in enumerate(top_contributors, start=1):
        ranking.append({
            "peringkat": index,
            "nama":contributor.name,
            "username":contributor.username,
            "total_point":contributor.total_points or 0
        })

    return {"Top_10_GCM_Contributor": ranking}
