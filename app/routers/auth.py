from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import uuid
import secrets

from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import get_pin, verifikasi_pin, create_access_token
from app.models import User
from app.schemas import UserCreate, OTPVerify, ResendOTP, UserLogin, Token, ForgotPin, ResetPinExecute
from app.services.otp import generate_otp
from app.services.notifikasi import send_registration_whatsapp, send_forgot_pin_wa
from app.services.sheets import ws_users, push_to_sheet
from app.services.email import send_email_otp

router=APIRouter()

@router.post("/users/")
@limiter.limit("30/15minutes")
def create_user(request: Request, user: UserCreate, bg_task: BackgroundTasks, db: Session=Depends(get_db)):
    existing_user=db.query(User).filter(User.username==user.username).with_for_update().first()
    
    if existing_user and existing_user.is_verified:
        raise HTTPException(status_code=400, detail="Username sudah terdaftar di sistem GCM. Silahkan Login")
    
    
    existing_email=db.query(User).filter(User.email==user.email, User.username!=user.username).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email sudah terdaftar di sistem GCM. Mohon gunakan email lain")
    
    existing_phone=db.query(User).filter(User.phone_number==user.phone_number, User.username!=user.username).first()
    if existing_phone:
        raise HTTPException(status_code=400, detail="Nomor telepon sudah terdaftar ke sistem GCM. Mohon gunakan nomor telepon lain")
    
    otp_token, waktu_expire=generate_otp()

    if existing_user:
        existing_user.name=user.name
        existing_user.email=user.email
        existing_user.phone_number=user.phone_number
        existing_user.hashed_pin=get_pin(user.pin)
        existing_user.reset_token=otp_token
        existing_user.reset_token_expire=waktu_expire
        db.commit()
        target_phone=existing_user.phone_number
        target_username=existing_user.username

    else:
        new_user= User(username=user.username, name= user.name, email=user.email, phone_number=user.phone_number, hashed_pin=get_pin(user.pin), reset_token=otp_token, reset_token_expire=waktu_expire, is_verified=False, qr_token=str(uuid.uuid4()))
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        target_phone=new_user.phone_number
        target_username=new_user.username

    bg_task.add_task(send_email_otp, user.email, otp_token, "Kode OTP Pendaftaran GCM")
    return {"message": "Pendaftaran awal berhasil. Silahkan masukan kode OTP yang dikirim ke EMAIL anda.", "username": target_username}

@router.post("/users/verify-otp/")
@limiter.limit("20/15minutes")
def verify_registration_otp(request: Request, data: OTPVerify, bg_task: BackgroundTasks, db: Session=Depends(get_db)):
    user=db.query(User).filter(User.username==data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")
    if getattr(user, 'is_verified', False):
        raise HTTPException(status_code=400, detail="Akun anda sudah terverifikasi sebelumnya")
    if user.reset_token!= data.otp_code:
        raise HTTPException(status_code=400, detail="Kode OTP tidak valid/salah")
    if user.reset_token_expire is None or datetime.now(timezone.utc)> user.reset_token_expire:
        raise HTTPException(status_code=400, detail= "Kode OTP sudah kedaluarsa, silahkan minta kode baru")
    
    user.is_verified=True
    user.reset_token=None
    user.reset_token_expire=None
    db.commit()
    row_data= [
        "=ROW()-3",
        user.username,
        user.name,
        user.email,
        user.phone_number,
        (datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S")),
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$F:$F)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$G:$G)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$H:$H)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$I:$I) - SUMIFS(Reward!$F:$F; Reward!$D:$D; INDIRECT("C"&ROW()); Reward!$I:$I; "Terpakai")',
    ]

    bg_task.add_task(push_to_sheet, ws_users, row_data)
    return{
        "message": "Verifikasi berhasil. Silahkan Login ke akun GCM",
        "username":user.username,
        "is_verified": True
    }

@router.post("/users/resend-otp/")
@limiter.limit("10/15minutes")
def resend_otp(request: Request, data: ResendOTP, bg_task: BackgroundTasks, db: Session=Depends(get_db)):
    user=db.query(User).filter(User.username==data.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Username tidak ditemukan. Silahkan melakukan registrasi ulang akun di web GCM terlebih dahulu")
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Akun anda sudah terverifikasi sebelumnya, silahkan login")
    
    otp_token, waktu_expire=generate_otp()
    user.reset_token=otp_token
    user.reset_token_expire=waktu_expire
    db.commit()

    bg_task.add_task(send_email_otp, user.email, otp_token, "Kode Resend OTP GCM")
    return {"message": f"Kode OTP baru telah dikirim ke EMAIL {user.email}"}

@router.post("/auth/login/", response_model=Token)
def login(data: UserLogin, db: Session=Depends(get_db)):
    user=db.query(User).filter(User.username==data.username).first()
    if not user or not verifikasi_pin(data.pin, user.hashed_pin):
        raise HTTPException(status_code=401, detail="Username atau PIN salah, coba kembali")
    if not getattr(user, 'is_verified', False):
        raise HTTPException(status_code=403, detail="Akun belum diverifikasi. Silahkan masukan OTP pendaftaran anda")
    access_token=create_access_token(data={"sub": user.username})
    return{"access_token": access_token, "token_type": "bearer"}

@router.post("/auth/forgot-pin/")
@limiter.limit("10/15minutes")
def forgot_pin(request: Request, data: ForgotPin, bg_task: BackgroundTasks, db: Session=Depends(get_db)):
    user=db.query(User).filter(User.username==data.username).first()
    if not user: raise HTTPException(status_code=404, detail="Username tidak terdaftar")
    
    if not user.is_verified:
        raise HTTPException(status_code= 400, detail="Akun belum diverifikasi.Selesaikan verifikasi OTP pendaftaran terlebih dahulu")
    reset_token=str(secrets.randbelow(900000)+ 100000)
    user.reset_token=reset_token
    user.reset_token_expire= datetime.now(timezone.utc)+timedelta(minutes=15)
    db.commit()
    bg_task.add_task(send_email_otp, user.email, reset_token, "Kode OTP Reset Pin GCM")
    return {"message": f"Kode verifikasi reset PIN telah dikirim ke email {user.email}"}

@router.post("/auth/reset-pin")
@limiter.limit("20/15minutes")
def reset(request: Request, data: ResetPinExecute, db: Session=Depends(get_db)):
    user= db.query(User).filter(User.username==data.username).first()
    if not user or user.reset_token !=data.kode_verifikasi:
        raise HTTPException(status_code=400, detail="Token reset tidak valid atau kadaluwarsa")
    if user.reset_token_expire is None or datetime.now(timezone.utc)>user.reset_token_expire:
        raise HTTPException(status_code=400, detail="Kode Verifikasi telah kadaluwarsa")
    user.hashed_pin=get_pin(data.new_pin)
    user.reset_token=None
    user.reset_token_expire=None
    db.commit()
    return {"message": "PIN berhasil diperbarui. Silahkan login kembali"}
   
