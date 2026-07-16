import httpx
from app.core.config import settings
from app.services.notifikasi import notifikasi_admin_telegram

async def send_email_otp(target_email: str, otp_code: str, subject: str):
    url= "https://api.resend.com/emails"
    headers={
        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    html_content= f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <div style="text-align: center; margin-bottom: 20px;">
            <h2 style="color: #2e7d32; margin: 0;">GreenCycle</h2>
            <p style="color: #666; margin: 5px 0 0 0;">Verifikasi Keamanan Akun</p>
        </div>
        <hr style="border: none; border-top: 1px solid #eee;" />
        <div style="padding: 20px 0;">
            <p style="font-size: 16px; color: #333;">Halo,</p>
            <p style="font-size: 16px; color: #333;">Berikut adalah kode verifikasi OTP Anda untuk sistem GCM:</p>
            <div style="text-align: center; margin: 30px 0;">
                <span style="font-size: 32px; font-weight: bold; color: #2e7d32; letter-spacing: 5px; padding: 10px 20px; background-color: #f1f8e9; border: 1px dashed #81c784; border-radius: 4px;">
                    {otp_code}
                </span>
            </div>
            <p style="font-size: 14px; color: #666; line-height: 1.5;">
                Kode ini berlaku selama <strong>15 menit</strong>. Demi keamanan akun Anda, mohon jangan bagikan kode ini kepada siapa pun.
            </p>
        </div>
        <hr style="border: none; border-top: 1px solid #eee;" />
        <div style="text-align: center; font-size: 12px; color: #999; margin-top: 20px;">
            <p>&copy; 2026 GCM System. All rights reserved.</p>
            <p>Ini adalah email otomatis, mohon tidak membalas email ini.</p>
        </div>
    </div>
    """

    payload= {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [target_email],
        "subject": subject,
        "html": html_content
    }

    try:
        async with httpx.AsyncClient() as client:
            resp= await client.post(url, headers=headers, json=payload, timeout=10.0)

            if resp.status_code in [200, 201]:
                print(f"INFO: Email OTP asinkron berhasil dikirim ke {target_email}")
            else:
                print(f"ERROR: API Resend gagal mengirim email ke {target_email} - status: {resp.status_code}, response: {resp.text}")
                notifikasi_admin_telegram(f"[GCM ALERT] Gagal kirim email OTP ke {target_email}. status: {resp.status_code}")
    except Exception as e:
        print(f"ERROR: Terjadi exception saat mengirim email ke {target_email} - {e}")
        notifikasi_admin_telegram(f"[GCM ALERT] Exception saat mengirim email ke {target_email}: {e}")