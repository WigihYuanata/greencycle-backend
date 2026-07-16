from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine, Base
from app.core.limiter import limiter

from app.routers import auth, dashboard, machine, qr_router, reward, transaksi, voucher

app= FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ORIGINS_DIIZINKAN.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.state.limiter=limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(machine.router)
app.include_router(qr_router.router)
app.include_router(reward.router)
app.include_router(transaksi.router)
app.include_router(voucher.router)

@app.on_event("startup")
def startup_migrate():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        #gae pengingat
        #conn.execute(text("ALTER TABLE nama_tabele ADD COLUMN IF NOT EXISTS foto_profil(contoh kolom) VARCHAR ")
        conn.commit()

@app.get("/")
def home():
    return {"message": "Welcome to Green Collective Movement", "project": settings.PROJECT_NAME}
