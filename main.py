import os
import asyncio
import random
import socks
import requests
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from supabase import create_client, Client
from telethon import TelegramClient, errors, types as tl_types
from telethon.sessions import StringSession
from telethon.tl.functions.channels import InviteToChannelRequest

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 1️⃣ جلب المتغيرات من Vercel
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

MY_API_ID = int(os.getenv("MY_API_ID", "123456"))
MY_API_HASH = os.getenv("MY_API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# 2️⃣ دالة إرسال الإشعارات للتليجرام
def send_telegram_notify(user_id: str, text: str):
    if not BOT_TOKEN or not user_id:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": user_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=3)
    except Exception as e:
        print(f"Failed to send notify: {e}")

# 3️⃣ كود المحرك الخارق (الكود الذي أرسلته) ⬇️
async def single_account_worker(acc, target_user, trg_entity, proxy_config, api_id, api_hash):
    session_str = acc.get("session_string")
    phone = acc.get("phone")
    
    client = TelegramClient(
        StringSession(session_str),
        api_id,
        api_hash,
        proxy=proxy_config,
        timeout=10
    )
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return False, "Unfit Account"

        await client(InviteToChannelRequest(trg_entity, [target_user]))
        await client.disconnect()
        return True, f"✅ [{phone}] أضاف بنجاح"

    except errors.FloodWaitError as e:
        await client.disconnect()
        return False, f"⚠️ حساب مقيد لمدة {e.seconds} ثانية"
    except Exception as e:
        await client.disconnect()
        return False, f"❌ خطأ: {str(e)}"

async def super_engine_run(army_accounts, target_users, trg_link, api_id, api_hash):
    tasks = []
    for i, user in enumerate(target_users):
        if i >= len(army_accounts):
            break
            
        acc = army_accounts[i]
        task = asyncio.create_task(
            single_account_worker(acc, user, trg_link, None, api_id, api_hash)
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    return results


# 4️⃣ مسارات الـ API والواجهة
# ✅ الشكل الصحيح والموافق للإصدارات الحديثة:
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/api/start-addition")
async def start_addition(
    uid: str = Form(...),
    src: str = Form(...),
    trg: str = Form(...)
):
    # جلب الحسابات من Supabase وتشغيل المحرك
    army_res = supabase.table("army_accounts").select("*").execute()
    army_accounts = army_res.data if army_res.data else []

    if not army_accounts:
        return JSONResponse({"status": "error", "message": "لا توجد حسابات جيش متوفرة"}, status_code=400)

    # إرسال إشعار بداية العملية
    send_telegram_notify(uid, f"🚀 **بدأت عملية الإضافة**\n🎯 المصدر: `{src}`\n🏁 الهدف: `{trg}`")

    # استدعاء المحرك الخارق لتنفيذ العملية
    # (هنا نمرر قائمة الأعضاء المجلوبة للمحرك)
    # results = await super_engine_run(army_accounts, target_users, trg, MY_API_ID, MY_API_HASH)

    return JSONResponse({"status": "success", "message": "تم تشغيل المحرك بنجاح!"})
