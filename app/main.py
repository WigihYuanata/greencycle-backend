from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Security, Request
from fastapi.security import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.core.config import settings
from app.core.database import engine, Base, get_db
from app.models import User, Transaction, reward
from app.schemas import UserCreate, UserResponse, TransactionCreate, TransactionResponse, RewardCreate, RewardResponse, RFIDPairing
import gspread
from datetime import datetime
import os
import string
import random

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))


BASE_DIREKTORI=(os.path.dirname(os.path.abspath(__file__)))

credential_path= os.path.join(BASE_DIREKTORI, 'credentials.json')
Base.metadata.create_all(bind=engine)
app= FastAPI(title=settings.PROJECT_NAME)

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
    otp=generate_otp()
    new_user= User(npm=user.npm, name= user.name, faculty=user.faculty, email=user.email, rfid_uid=None, activation_token=otp)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    row_data= [
        "=ROW()-3",
        new_user.npm,
        new_user.name,
        new_user.faculty,
        new_user.email,
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$G:$G)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$H:$H)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$I:$I)',
        '=SUMIF(Transaksi!$D:$D; INDIRECT("C"&ROW()); Transaksi!$J:$J) - SUMIFS(Reward!$F:$F; Reward!$D:$D; INDIRECT("C"&ROW()); Reward!$J:$J; "Success")',

    ]

    bg_task.add_task(push_to_sheet, ws_users, row_data)
    return new_user


@app.put("/machine/pair-ktm/")
def pair_ktm(data: RFIDPairing, db: Session=Depends(get_db), kunci: str = Depends(machine_validate)):
    user =db.query(User).filter(User.activation_token==data.activation_token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kode aktivasi salah atau kedaluarsa")
    uid_terdaftar= db.query(User).filter(User.rfid_uid==data.rfid_uid).first()
    if uid_terdaftar:
        raise HTTPException(status_code=404, detail="Kartu ini telah terdaftar pada akun lain")
    
    user.rfid_uid=data.rfid_uid
    user.activation_token=None
    db.commit()
    return{"status":"Sukses", "message": f"Kartu anda telah berhasil didaftarkan dan telah ditautkan ke akun {user.name}"}


@app.get("/machine/verify/{rfid_uid}")
def verify_rfid(rfid_uid: str, db : Session=Depends(get_db)):
    user=db.query(User).filter(User.rfid_uid==rfid_uid).first()
    if not user:
        raise HTTPException(status_code=404, detail=" Kartu anda belum terdaftar. Silahkan registrasi di website GreenCycle terlebih dahulu")
    return {
        "status": "Akses diberikan",
        "npm": user.npm,
        "name": user.name,
        "instruksi_mesin": "Buka pintu masuk botol"
    }


@app.post("/transactions/", response_model=TransactionResponse)
@limiter.limit("60\minute")
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
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
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
def redeem_reward(data: RewardCreate, bg_task: BackgroundTasks, db: Session=Depends(get_db)):
    user=db.query(User).filter(User.npm == data.npm).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan. Kartu anda belum terdaftar")
    total_points= db.query(func.sum(Transaction.points)).filter(Transaction.user_id == user.id).scalar() or 0
    total_withdraw= db.query(func.sum(reward.amount)).filter(reward.user_id == user.id).scalar() or 0
    current_points=total_points-total_withdraw
    MIN_WITHDRAW_POINTS=100
    if current_points < MIN_WITHDRAW_POINTS:
        raise HTTPException(status_code=400, detail=f"Poin tidak cukup untuk penarikan. Kumpulkan lebih banyak botol untuk mendapatkan poin")
    if data.amount > current_points:
        raise HTTPException(status_code=400, detail=f"Jumlah penarikan melebihi saldo point anda. Poin anda saat ini: {current_points}")
    new_withdraw= reward(
        user_id=user.id,
        amount=data.amount,
        provider=data.provider.value,
        account_number=data.account_number,
        account_name=data.account_name,
        status="Pending"
    )
    db.add(new_withdraw)
    db.commit()
    db.refresh(new_withdraw)
    waktu=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bg_task.add_task(push_to_sheet, ws_reward, [new_withdraw.id, waktu, user.npm, user.name, data.amount, new_withdraw.provider, data.account_number, data.account_name, "Pending"])
    return {
        "status": new_withdraw.status,
        "sisa_point": current_points - data.amount,
        "data_penarikan": {
            "amount": new_withdraw.amount,
            "provider": new_withdraw.provider,
            "nomor_rekening": new_withdraw.account_number,
            "nama_rekening": new_withdraw.account_name,
            "created_at": new_withdraw.created_at,
            "pesan": "Menunggu proses penarikan. Proses ini biasanya memakan waktu 1x24 jam kerja. Terima kasih telah berkontribusi bersama GreenCycle"
        }
    }

@app.get("/dashboard/")
def get_dashboard_data(npm: str, db: Session=Depends(get_db)):
    user= db.query(User).filter(User.npm==npm).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan. Kartu anda belum terdaftar")
    total_points=db.query(func.sum(Transaction.points)).filter(Transaction.user_id==user.id).scalar() or 0
    total_withdraw= db.query(func.sum(reward.amount)).filter(reward.user_id == user.id, reward.status=="Success").scalar() or 0
    current_balance=total_points-total_withdraw

    bottles=db.query(
        func.sum(Transaction.bottle_small).label("bottle_small"),
        func.sum(Transaction.bottle_medium).label("bottle_medium"),
        func.sum(Transaction.bottle_large).label("bottle_large")
    ).filter(Transaction.user_id==user.id).first()

    small_bottle= bottles.bottle_small or 0
    medium_bottle= bottles.bottle_medium or 0
    large_bottle= bottles.bottle_large or 0
    return {
        "profil":{
        "npm": user.npm,
        "name": user.name,
        "faculty": user.faculty,
        "email": user.email,

        },
        "statistik_finansial":{
            "total poin didapat": total_points,
            "poin_berhasil_ditukar": total_withdraw,
            "sisa_saldo_aktif": current_balance
        },
        "kontribusi_botol":{
            "botol_kecil":small_bottle,
            "botol_sedang": medium_bottle,
            "botol_besar":large_bottle,
            "total_kontribusi_lingkungan":(small_bottle+medium_bottle+large_bottle)
        }
        
    }

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

@app.put("/admin/rewards/{reward_id}")
def update_reward_status(reward_id: int, status: str, bg_tasks: BackgroundTasks, db: Session=Depends(get_db)):

    withdraw=db.query(reward).filter(reward.id==reward_id).first()
    if not withdraw:
        raise HTTPException(status_code=404, detail= "Data penarikan tidak ditemukan di databse")
    withdraw.status=status
    db.commit()

    def update_status_sheet(r_id, new_status):
        try:
            cell= ws_reward.find(str(r_id), in_column=2)
            if cell:

                ws_reward.update_cell(cell.row, 10, new_status)
        except Exception as e:
            print(f"Peringatan: Gagal melakukan sinkronisasi update ke Google Sheets - {e}")
    bg_tasks.add_task(update_status_sheet, reward_id, status)

    return {
        "message": f"Eksekusi berhasil dilakukan. Status penarikan ID {reward_id} telah diubah menjadi {status} di database dan spreedsheet"
    }