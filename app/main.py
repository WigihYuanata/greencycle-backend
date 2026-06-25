from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from app.core.config import settings
from app.core.database import engine, Base, get_db
from app.models import User, Transaction, reward, VoucherCatalog, MachineStatus
from app.schemas import UserCreate, UserResponse, TransactionCreate, TransactionResponse, RewardCreate, RewardResponse, UserLogin, Token, ForgotPin, ResetPinExecute, VoucherCatalogCreate, VoucherCatalogResponse, TransactionHistory, RewardHistory, UserUpdate, MachineStatusUpdate, QRVerifyRequest, OTPVerify, ResendOTP
from passlib.context import CryptContext
from jose import JWTError, jwt
import gspread
from datetime import datetime, timezone, timedelta
import os
import smtplib
import json
import requests as req
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from zoneinfo import ZoneInfo
import uuid
import secrets
from typing import List

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_DAY =7
EMAIL_SENDER=settings.EMAIL_SENDER
EMAIL_PASSWORD=settings.EMAIL_PASSWORD

WHATSAPP_API_URL=settings.WHATSAPP_API_URL
WHATSAPP_API_TOKEN=settings.WHATSAPP_API_TOKEN

TELEGRAM_BOT_TOKEN=settings.TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=settings.TELEGRAM_CHAT_ID
TELEGRAM_API_URL=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

CAPACITY_MAKS=0.80


HARGA_BOTOL_KECIL=10
HARGA_BOTOL_SEDANG=20
HARGA_BOTOL_BESAR=30

pwd_context=CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme= HTTPBearer()

def notifikasi_admin_telegram(text: str):
    try:
        req.post(TELEGRAM_API_URL, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print(f"ERROR: Gagal mengirim notifikasi ke telegram - {e}")

def send_registration_whatsapp(target_phone, otp_code):
    message=(
        f"*[GCM SYSTEM - Verifikasi Pendaftaran]*\n\n"
        f"Selamat datang di Green Collective Movement!\n"
        f"Kode OTP Anda untuk menyelesaikan pendaftaran akun:\n\n"
        f"*{otp_code}*\n\n"
        f"_Kode ini berlaku selama 15 menit. Jangan berikan kepada siapapun termasuk Tim GCM._"
    )
    try:
        resp= req.post(WHATSAPP_API_URL, headers={"Authorization":WHATSAPP_API_TOKEN}, json={"target": target_phone, "message": message}, timeout=10)
        try:
            resp_data=resp.json()
        except ValueError:
            resp_data={}
        gagal_dari_gateway=resp.status_code != 200 or resp_data.get("status") is False

        if gagal_dari_gateway:
            print(f"ERROR: Gateway WA menolak/gagal mengirim OTP ke {target_phone} - status_code: {resp.status_code}, response: {resp_data}")
            notifikasi_admin_telegram(f"[GCM - PERINGATAN] Gagal kirim OTP pendaftaran ke {target_phone}. \nResponse gateway WA: {resp_data}")
        else:
            print(f"INFO: Pesan pendaftaran berhasil dikirim ke Nomor: {target_phone}")
    except Exception as e:
        print(f"ERROR: Gagal mengirim pesan OTP pendaftaran ke {target_phone} : {e} ")
        notifikasi_admin_telegram(f"[GCM - PERINGATAN] Exception saat mengirim OTP ke {target_phone}: {e}")

def send_reset_email(target_email, token):
    msg=MIMEMultipart()
    msg['From']=EMAIL_SENDER
    msg['To']=target_email
    msg['Subject']="[GCM] Kode Verifikasi Reset PIN"

    body= f"""Yth Mahasiswa UPNVJT,

    
    Kami menerima permintaan reset PIN untuk akun GCM anda.
    Gunakan kode berikut untuk memverifikasi identitas anda:
    
    Kode: {token}

    Kode ini bersifat rahasia. Jangan berikan kepada siapapun termasuk tim GCM.

    Salam,
    GreenCollectiveMovement Team - Teaching Industry UPNVJT

"""
    msg.attach(MIMEText(body, 'plain'))

    try:
        server= smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"INFO: Email reset berhasil dikirim ke {target_email}")
    except Exception as e:
        print(f"ERROR: Gagal mengirim email: {e}")



def get_pin(pin): return pwd_context.hash(pin)
def verifikasi_pin(plain_pin, hashed_pin): return pwd_context.verify(plain_pin, hashed_pin)

def generate_otp():
    otp_token=str(secrets.randbelow(900000)+100000)
    waktu_expire=datetime.now(timezone.utc)+timedelta(minutes=15)
    return otp_token, waktu_expire

def is_row_sampah(existing_user):
    if existing_user is None:
        return False
    if existing_user.is_verified:
        return False
    if existing_user.reset_token_expire is None:
        return False
    return datetime.now(timezone.utc) > existing_user.reset_token_expire

def create_access_token(data: dict):
    to_encode= data.copy()
    expire= datetime.now(timezone.utc)+timedelta(days=ACCESS_TOKEN_EXPIRE_DAY)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials=Depends(bearer_scheme), db: Session=Depends(get_db)):
    token=credentials.credentials
    try:
        payload=jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        npm: str=payload.get("sub")
        if npm is None: raise HTTPException(status_code=401, detail="Token tidak valid")
    except JWTError: raise HTTPException(status_code=401, detail="Token tidak valid")
    user=db.query(User).filter(User.npm==npm).first()
    if user is None: raise HTTPException(status_code=401, detail="User tidak ditemukan")

    return user


Base.metadata.create_all(bind=engine)
with engine.connect() as conn:
    conn.execute(text(""" ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expire TIMESTAMP;"""))
    conn.execute(text("""ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20) UNIQUE;"""))
    conn.execute(text("""ALTER TABLE voucher_catalog ADD COLUMN IF NOT EXISTS milestone_threshold INTEGER DEFAULT 0;"""))
    conn.execute(text("""ALTER TABLE rewards ADD COLUMN IF NOT EXISTS secure_token VARCHAR(36) UNIQUE;"""))
    conn.execute(text("""ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;"""))
    conn.execute(text("""ALTER TABLE rewards ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;"""))
    conn.execute(text("""ALTER TABLE voucher_catalog ADD COLUMN IF NOT EXISTS voucher_duration_days INTEGER DEFAULT 7;"""))
    conn.commit()
app= FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ORIGINS_DIIZINKAN.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
limiter=Limiter(key_func=get_remote_address)
app.state.limiter=limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


API_KEY_MESIN= settings.API_KEY_MESIN
api_key_header=APIKeyHeader(name="X-API-Key", auto_error=True)



def machine_validate(api_key: str= Security(api_key_header)):
    if api_key!=API_KEY_MESIN:
        raise HTTPException(status_code=404, detail="Akses ditolak: Kunci API tidak valid!")
    return api_key
ws_users=ws_trans=ws_reward=None
try:
    credentials_json=os.getenv("GOOGLE_CREDENTIALS")
    if not credentials_json:
        raise RuntimeError("GOOGLE_CREDENTIALS belum diatur")
    credentials_dict=json.loads(credentials_json)
    gc= gspread.service_account_from_dict(credentials_dict)
    sh= gc.open("GreenCycle")
    ws_users= sh.worksheet("Data_Kontributor")
    ws_trans= sh.worksheet("Transaksi")
    ws_reward=sh.worksheet("Reward")
    print(f"INFO: Koneksi API Google Sheet Berhasil")
except Exception as e:
    print(f"ERROR: Koneksi API Google Sheet Gagal - {e}")

def push_to_sheet(sheet, row_data):
    if sheet is None:
        return
    try:
        sheet.append_row(row_data, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"ERROR: Gagal mengirim data ke google Spreadsheet - {e}")


@app.get("/")
def home():
    return {"message": "Welcome to Green Collective Movement",
    "project": settings.PROJECT_NAME}     
    
@app.post("/users/")
def create_user(user: UserCreate, bg_task: BackgroundTasks, db: Session=Depends(get_db)):
    existing_npm=db.query(User).filter(User.npm==user.npm).first()
    if existing_npm:
        if is_row_sampah(existing_npm):
            db.delete(existing_npm)
            db.commit()
        else:
            raise HTTPException(status_code=400, detail="NPM sudah terdaftar di sistem GCM")
    
    existing_email=db.query(User).filter(User.email==user.email).first()
    if existing_email:
        if is_row_sampah(existing_email):
            db.delete(existing_email)
            db.commit()
        else:
            raise HTTPException(status_code=400, detail="Email sudah terdaftar di sistem GCM. Mohon gunakan email lain")
    existing_phone=db.query(User).filter(User.phone_number==user.phone_number).first()
    if existing_phone:
        if is_row_sampah(existing_phone):
            db.delete(existing_phone)
            db.commit()
        else:
            raise HTTPException(status_code=400, detail="Nomor telepon sudah terdaftar ke sistem GCM. Mohon gunakan nomor telepon lain")
    otp_token, waktu_expire=generate_otp()

    new_user= User(npm=user.npm, name= user.name, faculty=user.faculty, email=user.email, phone_number=user.phone_number, hashed_pin=get_pin(user.pin), reset_token=otp_token, reset_token_expire=waktu_expire, is_verified=False)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    if user.phone_number:
        bg_task.add_task(send_registration_whatsapp, user.phone_number, otp_token)
    return {"message": "Pendaftaran awal berhasil. Silahkan masukan kode OTP yang dikirim ke WhatsApp anda.", "npm": new_user.npm}

@app.post("/users/verify-otp/")
def verify_registration_otp(data: OTPVerify, bg_task: BackgroundTasks, db: Session=Depends(get_db)):
    user=db.query(User).filter(User.npm==data.npm).first()
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
        user.npm,
        user.name,
        user.faculty,
        user.email,
        (datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S")),
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$G:$G)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$H:$H)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$I:$I)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$J:$J) - SUMIFS(Reward!$F:$F; Reward!$D:$D; INDIRECT("C"&ROW()); Reward!$I:$I; "Terpakai")',
    ]

    bg_task.add_task(push_to_sheet, ws_users, row_data)
    return{
        "message": "Verifikasi berhasil. Silahkan Login ke akun GCM",
        "npm":user.npm,
        "is_verified": True
    }

@app.post("/users/resend-otp/")
@limiter.limit("3/minute")
def resend_otp(request: Request, data: ResendOTP, bg_task: BackgroundTasks, db: Session=Depends(get_db)):
    user=db.query(User).filter(User.npm==data.npm).first()
    if not user:
        raise HTTPException(status_code=404, detail="NPM tidak ditemukan. Silahkan melakukan registrasi ulang akun di web GCM terlebih dahulu")
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Akun anda sudah terverifikasi sebelumnya, silahkan login")
    
    otp_token, waktu_expire=generate_otp()
    user.reset_token=otp_token
    user.reset_token_expire=waktu_expire
    db.commit()

    bg_task.add_task(send_registration_whatsapp, user.phone_number, otp_token)
    return {"message": f"Kode OTP baru telah dikirim ke WhatsApp {user.phone_number}"}

@app.get("/machine/verify/{npm}")
def verify_qr_code(npm:str, db: Session=Depends(get_db), kunci:str=Depends(machine_validate)):
    user=db.query(User).filter(User.npm==npm).first()
    if not user:
        raise HTTPException(status_code=404, detail="NPM belum terdaftar. Silahkan registrasi terlebih dahulu melalui web GCM")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Akun belum diverifikasi OTP. Selesaikan verifikasi WhatsApp di web GCM terlebih dahulu sebelum menggunakan Vending Machine")
    return {"status": "Akses diberikan", "npm": user.npm, "nama": user.name, "instruksi_mesin": "Buka pintu masuk botol"}

@app.get("/users/my-qr")
def get_user_qr(current_user: User=Depends(get_current_user)):
    qr_url=f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={current_user.npm}"
    return {"npm": current_user.npm, "qr_code_url": qr_url, "message": "Gunakan QR ini untuk melakukan transaksi di mesin GCM. Pastikan QR dapat dipindai dengan jelas untuk menghindari kegagalan transaksi."}

@app.put("/users/profile", response_model=UserResponse)
def update_profile(data: UserUpdate, db: Session=Depends(get_db), current_user: User=Depends(get_current_user)):
    if data.name:
        current_user.name=data.name
    if data.faculty:
        current_user.faculty=data.faculty
    db.commit()
    db.refresh(current_user)
    return current_user
    
@app.post("/auth/login/", response_model=Token)
def login(data: UserLogin, db: Session=Depends(get_db)):
    user=db.query(User).filter(User.npm==data.npm).first()
    if not user or not verifikasi_pin(data.pin, user.hashed_pin):
        raise HTTPException(status_code=401, detail="NPM atau PIN salah, coba kembali")
    if not getattr(user, 'is_verified', False):
        raise HTTPException(status_code=403, detail="Akun belum diverifikasi. Silahkan masukan OTP pendaftaran anda")
    access_token=create_access_token(data={"sub": user.npm})
    return{"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/forgot-pin/")
def forgot_pin(data: ForgotPin, bg_task: BackgroundTasks, db: Session=Depends(get_db)):
    user=db.query(User).filter(User.npm==data.npm).first()
    if not user: raise HTTPException(status_code=404, detail="NPM tidak terdaftar")
    reset_token=str(secrets.randbelow(900000)+ 100000)
    user.reset_token=reset_token
    user.reset_token_expire= datetime.now(timezone.utc)+timedelta(minutes=15)
    db.commit()
    bg_task.add_task(send_reset_email, user.email,reset_token)
    return {"message": f"Token reset telah dikirim ke email {user.email}"}

@app.post("/auth/reset-pin")
def reset(data: ResetPinExecute, db: Session=Depends(get_db)):
    user= db.query(User).filter(User.npm==data.npm).first()
    if not user or user.reset_token !=data.kode_verifikasi:
        raise HTTPException(status_code=400, detail="Token reset tidak valid atau kadaluwarsa")
    if user.reset_token_expire is None or datetime.now(timezone.utc)>user.reset_token_expire:
        raise HTTPException(status_code=400, detail="Kode Verifikasi telah kadaluwarsa")
    user.hashed_pin=get_pin(data.new_pin)
    user.reset_token=None
    user.reset_token_expire=None
    db.commit()
    return {"message": "PIN berhasil diperbarui. Silahkan login kembali"}
   

@app.post("/admin/vouchers", response_model=VoucherCatalogResponse)
def add_voucher_to_catalog(data: VoucherCatalogCreate, db:Session=Depends(get_db), kunci: str=Depends(machine_validate)):
    new_item= VoucherCatalog(**data.model_dump())
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

@app.get("/vouchers/available", response_model=List[VoucherCatalogResponse])
def get_available_voucher(db: Session=Depends(get_db)):
    return db.query(VoucherCatalog).filter(VoucherCatalog.is_active==True).all()
@app.get("/vouchers/available-status")
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

@app.post("/transactions/", response_model=TransactionResponse)
@limiter.limit("60/minute")
def Record_Transaction(request: Request, data: TransactionCreate, background_tasks: BackgroundTasks, db: Session= Depends(get_db), kunci: str = Depends(machine_validate)):
    user= db.query(User).filter(User.npm==data.npm).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan. NPM  atau akun anda belum terdaftar di sistem GCM")
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
        user.npm,
        user.name,
        user.faculty,
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

@app.post("/redeem/", response_model=RewardResponse)
def redeem_reward(data: RewardCreate, bg_task: BackgroundTasks, db: Session=Depends(get_db), current_user:User=Depends(get_current_user)):
    user=db.query(User).filter(User.id==current_user.id).with_for_update().first()

    voucher_type=db.query(VoucherCatalog).filter(VoucherCatalog.id==data.catalog_id, VoucherCatalog.is_active==True).first()
    if not voucher_type:
        raise HTTPException(status_code=404, detail="Voucher tidak ditemukan atau tidak tersedia")
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan. NPM atau akun anda belum terdaftar di sistem GCM")
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
    row_data=[new_voucher.id, waktu_sekarang, user.npm, user.name, voucher_type.point_cost, unique_code, "Selasar Caffe", "Active"]
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

def update_status_sheet(r_id, new_status):
    try:
        cell= ws_reward.find(str(r_id), in_column=2)
        if cell:

            ws_reward.update_cell(cell.row, 9, new_status)
    except Exception as e:
        print(f"Peringatan: Gagal melakukan sinkronisasi update ke Google Sheets - {e}")

@app.get("/dashboard/")
def get_dashboard_data(db: Session=Depends(get_db), current_user: User=Depends(get_current_user)):
    user= current_user
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan. NPM atau akun anda belum terdaftar di sistem GCM")
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
        "npm": user.npm,
        "name": user.name,
        "faculty": user.faculty,
        "email": user.email,
        "phone_number": user.phone_number,
        "qr_code_url": f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={user.npm}"

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

@app.get("/transaction/history", response_model=List[TransactionHistory])
def get_history_transaksi(skip: int=0, limit: int=20, db:Session=Depends(get_db), current_user:User=Depends(get_current_user)):
    return db.query(Transaction).filter(Transaction.user_id==current_user.id).order_by(desc(Transaction.created_at)).offset(skip).limit(limit).all()


@app.get("/redeem/history", response_model=List[RewardHistory])
def get_kode_redeem(skip: int=0, limit: int=20, db:Session=Depends(get_db), current_user:User=Depends(get_current_user)):
    return db.query(reward).filter(reward.user_id==current_user.id).order_by(desc(reward.created_at)).offset(skip).limit(limit).all()
@app.get("/leaderboard/")
def get_leaderboard(db: Session=Depends(get_db)):
    top_contributors=db.query(
        User.npm,
        User.name,
        User.faculty,
        func.sum(Transaction.points).label('total_points')
    ). join(Transaction).group_by(User.id).order_by(desc('total_points')).limit(10).all()

    ranking=[]
    for index, contributor in enumerate(top_contributors, start=1):
        ranking.append({
            "peringkat": index,
            "nama":contributor.name,
            "npm":contributor.npm,
            "fakultas":contributor.faculty,
            "total_point":contributor.total_points or 0
        })

    return {"Top_10_GCM_Contributor": ranking}

@app.get("/voucher/public-verify/{secure_token}")
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
@app.get("/voucher/public-consume/{secure_token}")
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

def send_capacity_alert(machine_id, pct: float):
    message=(
        f"[GCM ALERT] Kapasitas Mesin Hampir Penuh!\n\n"
        f"Mesin ID: {machine_id}\n"
        f"Kapasitas saat ini: {pct*100:.0f}%\n\n"
        f"Segera kosongkan mesin agar transaksi tidak terganggu.\n\n"
        f"GCM System - Auto Notification")
    try:
        resp= req.post(TELEGRAM_API_URL, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }, timeout=10 )
        if resp.status_code==200 and resp.json().get("ok"):
            print(f"INFO: Pesan peringatan kapasitas hampir makasimal berhasil dikirim ke Telegram Group")
        else:
            print(f"ERROR: Telegram menolak pesan - status {resp.status_code}, response: {resp.text}")
    except Exception as e:
        print(f"ERROR: Gagal mengirim pesan peringatan ke telegram - {e}")

@app.post("/iot/machine-status")
def  update_machine_status(data: MachineStatusUpdate, bg_tasks: BackgroundTasks, db: Session=Depends(get_db), kunci: str=Depends(machine_validate)):
    mesin=db.query(MachineStatus).filter(MachineStatus.machine_id==data.machine_id).first()
    if not mesin:
        mesin= MachineStatus(machine_id=data.machine_id, capacity_current=data.capacity_current, capacity_max=data.capacity_max)
        db.add(mesin)
    else:
        mesin.capacity_current=data.capacity_current
        mesin.capacity_max=data.capacity_max
    db.commit()
    db.refresh(mesin)

    if mesin.capacity_max<=0:
        return{
            "machine_id": mesin.machine_id,
            "status":"Error",
            "message":"Kapasitas maksimum mesin tidak boleh 0 atau negatif"
        }
    pct=mesin.capacity_current/mesin.capacity_max

    if pct<0.15 and mesin.last_notification_time is not None:
        mesin.last_notification_time=None
        db.commit()

    waktu_wib_sekarang= datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Jakarta"))
    sudah_notifikasi_hari_ini=(
        mesin.last_notification_time is not None 
        and mesin.last_notification_time.astimezone(ZoneInfo("Asia/Jakarta")).date()==waktu_wib_sekarang.date())
    
    notifikasi_dikirim=False
    if pct >= CAPACITY_MAKS and not sudah_notifikasi_hari_ini:
        mesin.last_notification_time=datetime.now(timezone.utc)
        db.commit()
        bg_tasks.add_task(send_capacity_alert, mesin.machine_id, pct)
        notifikasi_dikirim=True

    status_kapasitas= "Hampir Penuh" if pct>= CAPACITY_MAKS else "Normal"
    return {"machine_id": mesin.machine_id, "kapasitas": f"{pct*100:.1f}", "status":status_kapasitas, "notifikasi": notifikasi_dikirim}