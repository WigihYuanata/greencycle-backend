from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
from typing import List

from app.core.database import get_db
from app.core.config import settings
from app.core.security import machine_validate, get_current_user
from app.models import User, Transaction, reward, VoucherCatalog
from app.schemas import VoucherCatalogCreate, VoucherCatalogResponse
from app.services.sheets import update_status_sheet

router=APIRouter()

@router.post("/admin/vouchers", response_model=VoucherCatalogResponse)
def add_voucher_to_catalog(data: VoucherCatalogCreate, db:Session=Depends(get_db), kunci: str=Depends(machine_validate)):
    new_item= VoucherCatalog(**data.model_dump())
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

@router.get("/vouchers/available", response_model=List[VoucherCatalogResponse])
def get_available_voucher(db: Session=Depends(get_db)):
    return db.query(VoucherCatalog).filter(VoucherCatalog.is_active==True).all()

@router.get("/vouchers/available-status")
def get_voucher_status(db: Session=Depends(get_db), current_user: User=Depends(get_current_user)):
    total_points=db.query(func.sum(Transaction.points)).filter(Transaction.user_id==current_user.id).scalar() or 0
    vouchers=db.query(VoucherCatalog).filter(VoucherCatalog.is_active==True).all()
    list_voucher_status=[]

    for v in vouchers:
        is_unlocked=total_points>=v.milestone_threshold
        list_voucher_status.append({
            "id": v.id,
            "name": v.name,
            "cafe_name": v.cafe_name,
            "point_cost": v.point_cost,
            "description": v.description,
            "milestone_threshold": v.milestone_threshold,
            "is_unlocked": is_unlocked,
            "point_needed": max(0, v.milestone_threshold-total_points)

        })
    return list_voucher_status

@router.get("/voucher/public-verify/{secure_token}")
def verify_voucher_qr(secure_token: str, db: Session=Depends(get_db)):
    vouch=db.query(reward).filter(reward.secure_token==secure_token).first()
    if not vouch:
       raise HTTPException(status_code=404, detail="KODE TIDAK VALID: Voucher tidak ditemukan")
    if vouch.status=="Terpakai":
        raise HTTPException(status_code=400, detail="Maaf voucher yang akan digunakan telah terpakai sebelumnya")
    if vouch.status=="Kadaluarsa":
        raise HTTPException(status_code=400, detail="Maaf voucher ini sudah kadaluarsa dan tidak dapat digunakan")
    if vouch.expires_at is not None and datetime.now(timezone.utc)>vouch.expires_at:
        vouch.status="Kadaluarsa"
        db.commit()
        raise HTTPException(status_code=400, detail="Maaf voucher ini sudah kadaluarsa dan tidak dapat digunakan")
    
    katalog= db.query(VoucherCatalog).filter(VoucherCatalog.id==vouch.catalog_id).first()

    return {
        "status": "success",
        "pesan": "Voucher siap ditukarkan",
        "data_voucher":{
            "kode": vouch.voucher_code,
            "nama_caffe": katalog.cafe_name if katalog else "Selasar Caffe",
            "nama_voucher": katalog.name if katalog else "Reward Diskon",
            "potongan_poin": vouch.amount,
            "status_saat_ini": vouch.status,
            "expires_at":vouch.expires_at
        }

    }

@router.get("/voucher/public-consume/{secure_token}")
def consume_voucher_qr(secure_token: str, bg_tasks: BackgroundTasks, db:Session=Depends(get_db)):
    vouch= db.query(reward).filter(reward.secure_token==secure_token).with_for_update().first()
    if not vouch:
        raise HTTPException(status_code=404, detail="Voucher tidak valid")
    if vouch.status=="Terpakai":
        raise HTTPException(status_code=400, detail="Tidak dapat ditukar, Voucher sudah pernah digunakan")
    if vouch.status=="Kadaluarsa":
        raise HTTPException(status_code=400, detail="Tidak dapat menukar voucher, voucher sudah kadaluarsa")
    if vouch.expires_at is not None and datetime.now(timezone.utc)>vouch.expires_at:
        vouch.status="Kadaluarsa"
        db.commit()
        raise HTTPException(status_code=400, detail="Tidak dapat menukar voucher, voucher sudah kadaluarsa")
    
    vouch.status="Terpakai"
    db.commit()
    bg_tasks.add_task(update_status_sheet, vouch.id, "Terpakai")

    return {"message": f"voucher {vouch.voucher_code} berhasil dipakai"}
