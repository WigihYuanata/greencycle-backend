import segno
import io
import base64
from functools import lru_cache

@lru_cache(maxsize=2000)
def generate_local_qr(data: str) -> str:
    qr=segno.make(data, error='h')
    buffer=io.BytesIO()
    qr.save(buffer, kind="png", scale=8, border=4)
    img_base64=base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_base64}"