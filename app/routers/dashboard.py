from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, Transaction, reward, VoucherCatalog
from app.services.qr import generate_local_qr

router=APIRouter()

@router.get("/dashboard/")
def get_dashboard_data(db: Session=Depends(get_db), current_user: User=Depends(get_current_user)):
    user= current_user
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan. Username atau akun anda belum terdaftar di sistem GCM")
    total_points=db.query(func.sum(Transaction.points)).filter(Transaction.user_id==user.id).scalar() or 0
    total_redeem= db.query(func.sum(reward.amount)).filter(reward.user_id == user.id).scalar() or 0
    current_balance=total_points-total_redeem

    bottles=db.query(
        func.sum(Transaction.bottle_small).label("bottle_small"),
        func.sum(Transaction.bottle_medium).label("bottle_medium"),
        func.sum(Transaction.bottle_large).label("bottle_large")
    ).filter(Transaction.user_id==user.id).first()

    small_bottle= bottles.bottle_small or 0
    medium_bottle= bottles.bottle_medium or 0
    large_bottle= bottles.bottle_large or 0

    active_voucher=db.query(reward.voucher_code, VoucherCatalog.cafe_name, VoucherCatalog.name ).join(
        VoucherCatalog,
        reward.catalog_id==VoucherCatalog.id
    ).filter(
        reward.user_id==user.id,
        reward.status=="Active"
    ).all()

    daftar_voucher=[{"kode":v.voucher_code, "Cafee": v.cafe_name} for v in active_voucher]
    return {
        "profil":{
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "phone_number": user.phone_number,
        "qr_code_url": generate_local_qr(user.qr_token)

        },
        "statistik_finansial":{
            "total poin didapat": total_points,
            "poin_berhasil_ditukar": total_redeem,
            "sisa_saldo_aktif": current_balance
        },
        "kontribusi_botol":{
            "botol_kecil":small_bottle,
            "botol_sedang": medium_bottle,
            "botol_besar":large_bottle,
            "total_kontribusi_lingkungan":(small_bottle+medium_bottle+large_bottle)
        },
        "aset_mahasiswa":{
            "voucher_diskon_aktif": daftar_voucher,
        }
        
    }
