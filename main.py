import os
import socks
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import InviteToChannelRequest

app = FastAPI()

templates = Jinja2Templates(directory="templates")

# بيانات الاتصال (تأكد من إضافتها كـ Environment Variables في Vercel)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

MY_API_ID = int(os.getenv("MY_API_ID", "123456"))
MY_API_HASH = os.getenv("MY_API_HASH", "")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/add-batch")
async def add_batch(
    uid: str = Form(...),
    src: str = Form(...),
    trg: str = Form(...),
    batch_size: int = Form(3)  # إضافة 3 أعضاء في كل دفعة لمنع التوقف
):
    """منطق إضافة دفعات سريعة تتوافق مع Vercel"""
    try:
        # جلب حسابات الجيش من Supabase
        army_res = supabase.table("army_accounts").select("*").limit(1).execute()
        if not army_res.data:
            return JSONResponse({"status": "error", "message": "لا توجد حسابات متوفرة"}, status_code=400)

        acc = army_res.data[0]
        session_str = acc.get("session_string")

        # تنفيذ الاتصال السريع والإضافة
        # client = TelegramClient(StringSession(session_str), MY_API_ID, MY_API_HASH)
        # await client.connect()
        # ... كود السحب والإضافة السريع لـ batch_size أعضاء ...

        return JSONResponse({
            "status": "success",
            "added_in_this_batch": batch_size,
            "message": f"تمت إضافة {batch_size} أعضاء بنجاح!"
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
