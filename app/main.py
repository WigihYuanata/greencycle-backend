from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.core.config import settings
from app.core.database import engine, Base, get_db
from app.models import User, Transaction, reward, PickUpOrder, VoucherCatalog
from app.schemas import UserCreate, UserResponse, TransactionCreate, TransactionResponse, RewardCreate, RewardResponse, CardRegistration, UserLogin, Token, ForgotPin, ResetPinExecute, PickUpOrderCreate, PickUpOrderResponse, VoucherCatalogCreate, VoucherCatalogResponse, TransactionHistory, RewardHistory, UserUpdate
from passlib.context import CryptContext
from jose import JWTError, jwt
import gspread
from datetime import datetime, timezone, timedelta
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from zoneinfo import ZoneInfo
import uuid
import secrets
from typing import List

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAY = 7
EMAIL_SENDER=settings.EMAIL_SENDER
EMAIL_PASSWORD=settings.EMAIL_PASSWORD


pwd_context=CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme= HTTPBearer()

def send_reset_email(target_email, token):
    msg=MIMEMultipart()
    msg['From']=EMAIL_SENDER
    msg['To']=target_email
    msg['Subject']="[GreenCycle] Kode Verifikasi Reset PIN"

    body= f"""Yth Mahasiswa UPNVJT,

    
    Kami menerima permintaan reset PIN untuk akun Greencycle anda.
    Gunakan kode berikut untuk memverifikasi identitas anda:
    
    Kode: {token}
    Kode ini bersifat rahasia. Jangan berikan kepada siapapun termasuk tim GreenCycle.

    Salam,
    GreenCycle Team - Teaching Industry UPNVJT

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


BASE_DIREKTORI=(os.path.dirname(os.path.abspath(__file__)))

credential_path= os.path.join(BASE_DIREKTORI, 'credentials.json')
Base.metadata.create_all(bind=engine)
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

try:
    gc= gspread.service_account(filename=credential_path)
    sh= gc.open("GreenCycle")
    ws_users= sh.worksheet("Data_Kontributor")
    ws_trans= sh.worksheet("Transaksi")
    ws_reward=sh.worksheet("Reward")
    print(f"INFO: Koneksi API Google Sheet Berhasil")
except Exception as e:
    print(f"ERROR: Koneksi API Google Sheet Gagal - {e}")

def push_to_sheet(sheet, row_data):
    try:
        sheet.append_row(row_data, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"ERROR: Gagal mengirim data ke google Spreadsheet - {e}")


@app.get("/")
def home():
    return {"message": "Welcome to GreenCycle",
    "project": settings.PROJECT_NAME}     
    
@app.post("/users/", response_model=UserResponse)
def create_user(user: UserCreate, bg_task: BackgroundTasks, db: Session=Depends(get_db)):

    expected_email=f"{user.npm}@student.upnjatim.ac.id"   
    if user.email != expected_email:
        raise HTTPException(status_code=400, detail=f"Email tidak valid. Mohon gunakan format yang benar (Contoh: {expected_email})")
    
    user_terdaftar= db.query(User).filter(User.npm==user.npm).first()
    if user_terdaftar:
        raise HTTPException(status_code=400, detail="NPM atau RFID UID sudah terdaftar di sistem GreenCycle")
    new_user= User(npm=user.npm, name= user.name, faculty=user.faculty, email=user.email, rfid_uid=None, hashed_pin=get_pin(user.pin))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    row_data= [
        "=ROW()-3",
        new_user.npm,
        new_user.name,
        new_user.faculty,
        new_user.email,
        (datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S")),
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$G:$G)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$H:$H)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$I:$I)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$J:$J) - SUMIFS(Reward!$F:$F; Reward!$D:$D; INDIRECT("C"&ROW()); Reward!$J:$J; "Success")',

    ]

    bg_task.add_task(push_to_sheet, ws_users, row_data)
    return new_user

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

@app.post("/iot/register-card")
def register_card_direct(data: CardRegistration, db: Session=Depends(get_db), kunci: str=Depends(machine_validate)):
    user=db.query(User).filter(User.npm==data.npm).first()
    if not user:
        raise HTTPException(status_code=401, detail="NPM tidak terdaftar di sistem. Silahkan daftar terlebih dahulu")
    if user.rfid_uid:
        raise HTTPException(status_code=400, detail="Akun ini sudah memiliki kartu yang tertaut")
    
    is_card_used=db.query(User).filter(User.rfid_uid==data.rfid_uid).first()
    if is_card_used:
        raise HTTPException(status_code=400, detail="Kartu ini sudah terdaftar pada akun lain")
    
    user.rfid_uid=data.rfid_uid
    db.commit()
    return{"status": "SUCCESS", "message": f"Kartu berhasil ditautkan ke akun {user.name}"}
    

@app.get("/machine/verify/{rfid_uid}")
def verify_rfid(rfid_uid: str, db : Session=Depends(get_db), kunci: str=Depends(machine_validate)):
    user=db.query(User).filter(User.rfid_uid==rfid_uid).first()
    if not user:
        raise HTTPException(status_code=404, detail=" Kartu anda belum terdaftar. Silahkan registrasi di website GreenCycle terlebih dahulu")
    return {
        "status": "Akses diberikan",
        "npm": user.npm,
        "name": user.name,
        "instruksi_mesin": "Buka pintu masuk botol"
    }
@app.post("/admin/vouchers", response_model=VoucherCatalogResponse)
def add_voucher_to_catalog(data: VoucherCatalogCreate, db:Session=Depends(get_db), kunci: str=Depends(machine_validate)):
    new_item= VoucherCatalog(**data.dict())
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

@app.get("/vouchers/available", response_model=List[VoucherCatalogResponse])
def get_available_voucher(db: Session=Depends(get_db)):
    return db.query(VoucherCatalog).filter(VoucherCatalog.is_active==True).all()

@app.post("/transactions/", response_model=TransactionResponse)
@limiter.limit("60/minute")
def Record_Transaction(request: Request, data: TransactionCreate, background_tasks: BackgroundTasks, db: Session= Depends(get_db), kunci: str = Depends(machine_validate)):
    user= db.query(User).filter(User.npm==data.npm).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan. Kartu anda belum terdaftar")
    bottle_small_point=data.bottle_small*10
    bottle_medium_point=data.bottle_medium*20
    bottle_large_point=data.bottle_large*30
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
        raise HTTPException(status_code=404, detail="User tidak ditemukan. Kartu anda belum terdaftar")
    total_points= db.query(func.sum(Transaction.points)).filter(Transaction.user_id == user.id).scalar() or 0
    total_redeem= db.query(func.sum(reward.amount)).filter(reward.user_id == user.id).scalar() or 0
    current_points=total_points-total_redeem
    if current_points < voucher_type.point_cost:
        raise HTTPException(status_code=400, detail=f"Poin tidak cukup untuk penarikan, harga voucher {voucher_type.point_cost}. Kumpulkan lebih banyak botol untuk mendapatkan poin.")
   
  
    unique_code=f"GC-{str(uuid.uuid4()).upper()[:8]}"
    new_voucher= reward(
        user_id=user.id,
        catalog_id= voucher_type.id,
        amount=voucher_type.point_cost,
        voucher_code=unique_code,
        status="Active"
    )

    db.add(new_voucher)
    db.commit()
    db.refresh(new_voucher)
    waktu_sekarang=datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S")
    row_data=[new_voucher.id, waktu_sekarang, user.npm, user.name, voucher_type.point_cost, unique_code, "Selasar Caffe", "Active"]
    bg_task.add_task(push_to_sheet, ws_reward, row_data)
    tautan_kasir =f"{settings.BASE_URL}/kasir?kode={unique_code}" 
    return {
        "status": new_voucher.status,
        "voucher_code": unique_code,
        "qr_code_url": f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={tautan_kasir}",
        "cafe_name": f"{voucher_type.cafe_name} ({voucher_type.name})",
        "sisa_point": current_points-voucher_type.point_cost
    }
@app.put("/admin/rewards/{reward_id}")
def update_reward_status(reward_id: int, status: str, bg_tasks: BackgroundTasks, db: Session=Depends(get_db), kunci: str=Depends(machine_validate)):

    withdraw=db.query(reward).filter(reward.id==reward_id).first()
    if not withdraw:
        raise HTTPException(status_code=404, detail= "Data penarikan tidak ditemukan di databse")
    withdraw.status=status
    db.commit()
    bg_tasks.add_task(update_status_sheet, reward_id, status)

    return {
        "message": f"Eksekusi berhasil dilakukan. Status penarikan ID {reward_id} telah diubah menjadi {status} di database dan spreedsheet"
    }

def update_status_sheet(r_id, new_status):
    try:
        cell= ws_reward.find(str(r_id), in_column=2)
        if cell:

            ws_reward.update_cell(cell.row, 10, new_status)
    except Exception as e:
        print(f"Peringatan: Gagal melakukan sinkronisasi update ke Google Sheets - {e}")


@app.get("/admin/vouchers/verify/{voucher_code}")
def verifikasi_kasir(voucher_code: str, db: Session=Depends(get_db), kunci: str=Depends(machine_validate)):
    vouch=db.query(reward).filter(reward.voucher_code==voucher_code).first()
    if not vouch:
       raise HTTPException(status_code=404, detail="KODE TIDAK VALID: Voucher tidak diketahui")
    if vouch.status=="Terpakai":
        raise HTTPException(status_code=400, detail="Maaf voucher yang akan digunakan telah terpakai sebelumnya")
    katalog= db.query(VoucherCatalog).filter(VoucherCatalog.id==vouch.catalog_id).first()

    return {
        "status": "success",
        "pesan": "Voucher siap ditukarkan",
        "data_voucher":{
            "kode": vouch.voucher_code,
            "nama_caffe": "Selasar Caffe",
            "potongan_poin": vouch.amount,
            "status_saat_ini": vouch.status
        }

    }
@app.put("/admin/vouchers/consume/{voucher_code}")
def konsumsi_voucher(voucher_code: str, bg_tasks: BackgroundTasks, db:Session=Depends(get_db), kunci: str= Depends(machine_validate)):
    vouch= db.query(reward).filter(reward.voucher_code==voucher_code, reward.status=="Active").first()
    if not vouch:
        raise HTTPException(status_code=404, detail="Voucher tidak valid atau sudah pernah digunakan")
    
    vouch.status="Terpakai"
    db.commit()

    bg_tasks.add_task(update_status_sheet, vouch.id, "Terpakai")

    return {"message": f"voucher {voucher_code} berhasil dipakai"}



@app.post("/pickup/order/", response_model=PickUpOrderResponse)
def create_pickup_order(data:PickUpOrderCreate, db:Session=Depends(get_db), current_user:User=Depends(get_current_user)):
    existing_order= db.query(PickUpOrder).filter(
        PickUpOrder.user_id==current_user.id,
        PickUpOrder.status=="Pending"
    ).first()
    if existing_order:
        raise HTTPException(status_code=400, detail="Anda masih memiliki pesanan penjemputan yang berstatus 'Pending'")
    new_order=PickUpOrder(
        user_id=current_user.id,
        pickup_address=data.pickup_address,
        contact_number=data.contact_number,
        scheduled_day=data.scheduled_day.value,
        status="Pending"
    )

    db.add(new_order)
    db.commit()
    db.refresh (new_order)

    return new_order

@app.get("/pickup/my-orders", response_model=List[PickUpOrderResponse])
def get_my_pickup_orders(db:Session=Depends(get_db), current_user: User=Depends(get_current_user)):
    return db.query(PickUpOrder).filter(PickUpOrder.user_id==current_user.id).all()
@app.delete("/pickup/cancel/{order_id}")
def cancel_pickup_order(order_id: int, db: Session=Depends(get_db), current_user: User=Depends(get_current_user)):
    order= db.query(PickUpOrder).filter(
        PickUpOrder.id==order_id,
        PickUpOrder.user_id==current_user.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    if order.status!="Pending":
        raise HTTPException(status_code=400, detail="Hanya pesanan berstatus 'Pending' yang dapat dibatalkan")
    order.status="Dibatalkan"
    db.commit()
    return{"message": f"Pesanan penjemputan ID {order_id} berhasil dibatalkan"}

@app.put("/admin/pickup/{order_id}")
def update_pickup_status(order_id: int, status: str, db: Session=Depends(get_db),kunci:str=Depends(machine_validate)):
    order=db.query(PickUpOrder).filter(PickUpOrder.id==order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    order.status=status
    db.commit()
    return{"message": f"Status pesanan ID {order_id} berhasil diubah menjadi {status}"}

@app.get("/dashboard/")
def get_dashboard_data(db: Session=Depends(get_db), current_user: User=Depends(get_current_user)):
    user= current_user
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan. Kartu anda belum terdaftar")
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
    active_pickup= db.query(PickUpOrder).filter(
        PickUpOrder.user_id==user.id, 
        PickUpOrder.status=="Pending"
    ).first()

    status_jemput=None
    if active_pickup:
        status_jemput=f"Dijadwalkan hari {active_pickup.scheduled_day} (Status: {active_pickup.status})"
    return {
        "ktm terhubung": current_user.rfid_uid is not None,
        "profil":{
        "npm": user.npm,
        "name": user.name,
        "faculty": user.faculty,
        "email": user.email,

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
            "jadwal_penjemputan": status_jemput or "Tidak ada jadwal aktif"
        }
        
    }

@app.get("/transaction/history", response_model=List[TransactionHistory])
def get_history_transaksi(db:Session=Depends(get_db), current_user:User=Depends(get_current_user)):
    return db.query(Transaction).filter(Transaction.user_id==current_user.id).order_by(desc(Transaction.created_at)).all()


@app.get("/redeem/history", response_model=List[RewardHistory])
def get_kode_redeem(db:Session=Depends(get_db), current_user:User=Depends(get_current_user)):
    return db.query(reward).filter(reward.user_id==current_user.id).order_by(desc(reward.created_at)).all()
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

    return {"Top_10_GreenCycle": ranking}