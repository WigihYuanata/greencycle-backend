from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import List
import uuid

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.models import User, Transaction, reward, VoucherCatalog
from app.schemas import RewardCreate, RewardResponse, RewardHistory
from app.services.sheets import push_to_sheet, ws_reward

router=APIRouter()


@router.post("/redeem/", response_model=RewardResponse)
def redeem_reward(data: RewardCreate, bg_task: BackgroundTasks, db: Session=Depends(get_db), current_user:User=Depends(get_current_user)):
    user=db.query(User).filter(User.id==current_user.id).with_for_update().first()

    voucher_type=db.query(VoucherCatalog).filter(VoucherCatalog.id==data.catalog_id, VoucherCatalog.is_active==True).first()
    if not voucher_type:
        raise HTTPException(status_code=404, detail="Voucher tidak ditemukan atau tidak tersedia")
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan. Username atau akun anda belum terdaftar di sistem GCM")
    total_points= db.query(func.sum(Transaction.points)).filter(Transaction.user_id == user.id).scalar() or 0
    total_redeem= db.query(func.sum(reward.amount)).filter(reward.user_id == user.id).scalar() or 0
    current_points=total_points-total_redeem
    if total_points < voucher_type.milestone_threshold:
        raise HTTPException(status_code=400, detail= f"Voucher ini masih terkunci! Kumpulkan lebih banyak botol untuk membukanya")
    if current_points < voucher_type.point_cost:
        raise HTTPException(status_code=400, detail=f"Poin tidak cukup untuk penarikan, harga voucher {voucher_type.point_cost}. Kumpulkan lebih banyak botol untuk mendapatkan poin.")
   
  
    unique_code=f"GC-{str(uuid.uuid4()).upper()[:8]}"
    crypto_token=str(uuid.uuid4())
    waktu_expires=datetime.now(timezone.utc)+timedelta(days=voucher_type.voucher_duration_days)
    new_voucher= reward(
        user_id=user.id,
        catalog_id= voucher_type.id,
        amount=voucher_type.point_cost,
        voucher_code=unique_code,
        secure_token=crypto_token,
        status="Active",
        expires_at=waktu_expires
    )

    db.add(new_voucher)
    db.commit()
    db.refresh(new_voucher)
    waktu_sekarang=datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S")
    row_data=[new_voucher.id, waktu_sekarang, user.username, user.name, voucher_type.point_cost, unique_code, voucher_type.cafe_name, "Active"]
    bg_task.add_task(push_to_sheet, ws_reward, row_data)
    tautan_kasir =f"{settings.BASE_URL}/kasir?kode={crypto_token}" 
    return {
        "status": new_voucher.status,
        "voucher_code": unique_code,
        "qr_code_url": f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={tautan_kasir}",
        "cafe_name": f"{voucher_type.cafe_name} ({voucher_type.name})",
        "sisa_point": current_points-voucher_type.point_cost,
        "expires_at": waktu_expires
    }

@router.get("/redeem/history", response_model=List[RewardHistory])
def get_kode_redeem(skip: int= Query(0, ge=0), limit: int=Query(20, ge=1, le=100), db:Session=Depends(get_db), current_user:User=Depends(get_current_user)):
    waktu_sekarang_utc=datetime.now(timezone.utc)
    rows_terupdate=db.query(reward).filter(
        reward.user_id==current_user.id,
        reward.status=="Active",
        reward.expires_at.isnot(None),
        reward.expires_at<waktu_sekarang_utc
    ).update({"status": "Kadaluarsa"}, synchronize_session=False)
    
    if rows_terupdate>0:
        db.commit()
    
    daftar_reward=db.query(reward).options(
        joinedload(reward.catalog)
    ).filter(
        reward.user_id==current_user.id
    ).order_by(desc(reward.created_at)).offset(skip).limit(limit).all()

    hasil=[]
    
    for r in daftar_reward:
        if r.status=="Active":
            tautan_kasir=f"{settings.BASE_URL}/kasir?kode={r.secure_token}"
            qr_code_url=f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={tautan_kasir}"
            can_show_qr=True
        else:
            qr_code_url=None
            can_show_qr=False

        hasil.append(RewardHistory(
            id=r.id,
            voucher_code=r.voucher_code,
            amount=r.amount,
            status=r.status,
            created_at=r.created_at,
            expires_at=r.expires_at,
            voucher_name=r.catalog.name if r.catalog else None,
            cafe_name=r.catalog.cafe_name if r.catalog else None,
            image_url=r.catalog.image_url if r.catalog else None,
            qr_code_url=qr_code_url,
            can_show_qr=can_show_qr
        ))

    return hasil