from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models import User
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone

SECRET_KEY = settings.SECRET_KEY
ALGORITHM =settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_DAY =settings.ACCESS_TOKEN_EXPIRE_DAY
API_KEY_MESIN =settings.API_KEY_MESIN

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

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
        username: str=payload.get("sub")
        if username is None: raise HTTPException(status_code=401, detail="Token tidak valid")
    except JWTError: raise HTTPException(status_code=401, detail="Token tidak valid")
    user=db.query(User).filter(User.username==username).first()
    if user is None: raise HTTPException(status_code=401, detail="User tidak ditemukan")
    return user

def machine_validate(api_key: str= Security(api_key_header)):
    if api_key!=API_KEY_MESIN:
        raise HTTPException(status_code=404, detail="Akses ditolak: Kunci API tidak valid!")
    return api_key
