from fastapi import Request, APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import cv2
import numpy as np

from app.core.database import get_db
from app.core.security import machine_validate, get_current_user
from app.core.limiter import limiter
from app.models import User
from app.services.qr import generate_local_qr

router=APIRouter()

@router.get("/machine/verify/{qr_token}")
def verify_qr_code(qr_token:str, db: Session=Depends(get_db), kunci:str=Depends(machine_validate)):
    user=db.query(User).filter(User.qr_token==qr_token).first()
    if not user:
        raise HTTPException(status_code=404, detail="QR tidak valid atau belum terdaftar. Silahkan registrasi terlebih dahulu melalui web GCM")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Akun belum diverifikasi OTP. Selesaikan verifikasi WhatsApp di web GCM terlebih dahulu sebelum menggunakan Vending Machine")
    return {"status": "Akses diberikan", "username": user.username, "nama": user.name, "instruksi_mesin": "Buka pintu masuk botol"}

@router.post("/machine/scan-qr-image")
@limiter.limit("60/minute")
def scan_qr_image(request: Request, file: UploadFile = File(...), db: Session=Depends(get_db), kunci: str=Depends(machine_validate)):
    if file.content_type not in ["image/jpeg", "image/jpg"]:
        raise HTTPException(status_code=400, detail="Format file tidak didukung, harus jpeg/jpg")
    isi_file=file.file.read()
    if len(isi_file)==0:
        raise HTTPException(status_code=400, detail="File Kosong")
    MAX_SIZE=2*1024*1024
    if len(isi_file)> MAX_SIZE:
        raise HTTPException(status_code=413, detail="Ukuran file terlalu besar, maskimal 2MB")
    
    np_array=np.frombuffer(isi_file, dtype=np.uint8)
    gambar=cv2.imdecode(np_array, cv2.IMREAD_COLOR)

    if gambar is None:
        raise HTTPException(status_code=400, detail="File bukan gambar yang valid atau rusak")
    
    detector= cv2.QRCodeDetector()
    data_qr, bbox, straight_qrcode=detector.detectAndDecode(gambar)
    if not data_qr:
        raise HTTPException(status_code=422, detail="QR code tidak terdeteksi di dalam gambar")
    
    user=db.query(User).filter(User.qr_token==data_qr).first()
    if not user:
        raise HTTPException(status_code=404, detail="QR tidak valid atau user belum terdaftar. Silahkan melakukan pendaftaran terlebih dahulu melalui web GCM")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Akun belum diverifikasi OTP. Selesaikan verifikasi OTP terlebih dahulu di Web GCM")
    
    return{"status": "Akses diberikan", "username": user.username, "nama": user.name, "instruksi_mesin": "Buka pintu masuk botol"}

@router.get("/users/my-qr")
def get_user_qr(current_user: User=Depends(get_current_user)):
    qr_url=generate_local_qr(current_user.qr_token)
    return {"username": current_user.username, "qr_code_url": qr_url, "message": "Gunakan QR ini untuk melakukan transaksi di mesin GCM. Pastikan QR dapat dipindai dengan jelas untuk menghindari kegagalan transaksi."}
    