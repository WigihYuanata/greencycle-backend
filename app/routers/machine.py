from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.database import get_db
from app.core.config import settings
from app.core.security import machine_validate
from app.models import MachineStatus
from app.schemas import MachineStatusUpdate
from app.services.notifikasi import send_capacity_alert

router=APIRouter()

CAPACITY_MAKS=settings.CAPACITY_MAKS

@router.post("/iot/machine-status")
def update_machine_status(data: MachineStatusUpdate, bg_tasks: BackgroundTasks, db: Session=Depends(get_db), kunci: str=Depends(machine_validate)):
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