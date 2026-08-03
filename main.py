# ==========================================
# 🟢 القسم 1: المكتبات والتهيئة (Imports & Setup)
# ==========================================
import os
import re
import uuid
import random
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from supabase import create_client, Client

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest, InviteToChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import (
    UserAlreadyParticipantError,
    UserPrivacyRestrictedError,
    UserNotMutualContactError,
    ChatAdminRequiredError,
    FloodWaitError,
    PeerFloodError
)

app = FastAPI(title="Dragon Engine Pro API")

# تحديد المسار المطلق لمجلد القوالب لضمان العثور عليه في Render
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://juuleypxvvcfgjdikpwu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_Kh6iN4Aq6X6gLNcElNzgRg_CjlLMaZL")

API_ID = int(os.getenv("TELEGRAM_API_ID", "21349867"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "7ced3ee4c80117bd5138410811b91f9f")

OXAPAY_MERCHANT_KEY = os.getenv("OXAPAY_MERCHANT_KEY", "VVWSV1-17YEGL-05LITH-PLZ5EX")
ADMIN_TELEGRAM_BOT_TOKEN = os.getenv("ADMIN_TELEGRAM_BOT_TOKEN", "8725004596:AAF7fH3qyLq4nhRRp3RIbVGQj8bMo632oM8")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "6016547718")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Shrkatbot")
MONTHLY_PRICE_USD = 80

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
pending_sessions = {}


# ==========================================
# 🟢 القسم 2: نماذج البيانات والدوال المساعدة (Models & Helpers)
# ==========================================
class RegisterUserRequest(BaseModel):
    full_name: str
    username_or_phone: str

class PaymentRequest(BaseModel):
    user_id: str

class PhoneRequest(BaseModel):
    user_id: str
    phone_number: str

class VerifyRequest(BaseModel):
    user_id: str
    phone_number: str
    phone_code_hash: str
    code: str
    password: Optional[str] = None

class AddMembersRequest(BaseModel):
    user_id: str
    source_group: str
    target_group: str

class DeleteAccountRequest(BaseModel):
    user_id: str
    phone: str

def check_user_subscription(user_id: str) -> bool:
    user_id_str = str(user_id)
    res = supabase.table("users_subscriptions").select("is_active").eq("user_id", user_id_str).execute()
    if res.data and res.data[0].get("is_active"):
        return True
    return False

async def send_telegram_notification(text: str):
    """إرسال إشعار تليجرام بشكل غير متزامن لتجنب تعطيل السيرفر"""
    try:
        url = f"https://api.telegram.org/bot{ADMIN_TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "HTML"}
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, timeout=5.0)
    except Exception as e:
        print(f"فشل إرسال الإشعار: {e}")


# ==========================================
# 🟢 القسم 3: مسارات المستخدمين والاشتراكات (User & Auth APIs)
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/api/register-user")
async def register_user(req: RegisterUserRequest):
    try:
        clean_contact = req.username_or_phone.strip().lower()
        clean_name = req.full_name.strip()

        if not clean_contact or not clean_name:
            raise HTTPException(status_code=400, detail="يرجى إدخال البيانات بشكل صحيح")

        existing = supabase.table("users1").select("user_id").eq("username_or_phone", clean_contact).execute()
        
        if existing.data and len(existing.data) > 0:
            user_id = existing.data[0]["user_id"]
            return {
                "status": "success", 
                "user_id": user_id, 
                "message": "مرحباً بعودتك! تم العثور على حسابك بنجاح 🟢"
            }

        user_id = 'user_' + uuid.uuid4().hex[:9]
        
        supabase.table("users1").insert({
            "user_id": user_id,
            "full_name": clean_name,
            "username_or_phone": clean_contact
        }).execute()

        supabase.table("users_subscriptions").insert({
            "user_id": user_id,
            "username": clean_contact,
            "is_active": False,
            "subscription_end": None
        }).execute()

        await send_telegram_notification(
            f"🚨 <b>مشترك جديد يسجل في المنصة!</b>\n"
            f"👤 <b>الاسم:</b> {clean_name}\n"
            f"📞 <b>التواصل:</b> {clean_contact}\n"
            f"🆔 <b>المعرف:</b> <code>{user_id}</code>\n\n"
            f"💡 <i>توجه إلى Supabase لتفعيل الاشتراك لهذا المعرف.</i>"
        )
        
        return {
            "status": "success", 
            "user_id": user_id, 
            "message": "تم إنشاء الحساب بنجاح! حسابك بانتظار التفعيل من الإدارة."
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/subscription-status")
async def subscription_status(user_id: str):
    res = supabase.table("users_subscriptions").select("*").eq("user_id", user_id).execute()
    if res.data and res.data[0].get("is_active"):
        end_date = (res.data[0].get("subscription_end") or "")[:10]
        return {"is_active": True, "ends_at": end_date}
    return {"is_active": False}

@app.post("/api/create-oxapay-payment")
async def create_oxapay_payment(req: PaymentRequest):
    payload = {
        "merchant": OXAPAY_MERCHANT_KEY,
        "amount": MONTHLY_PRICE_USD,
        "currency": "USD",
        "lifeTime": 60,
        "orderId": req.user_id,
        "callbackUrl": "https://adawat-tele.vercel.app/api/oxapay-webhook",
        "description": "اشتراك شهري للمحرك الخارق"
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.oxapay.com/merchants/request", json=payload, timeout=10.0)
            response = res.json()
            if response.get("result") == 100:
                return {"pay_url": response.get("payLink")}
        raise HTTPException(status_code=400, detail="خطأ بإنشاء رابط OxaPay")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@app.post("/api/oxapay-webhook")
async def oxapay_webhook(request: Request):
    data = await request.json()
    if data.get("status") == "Paid":
        user_id = data.get("orderId")
        new_end_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        supabase.table("users_subscriptions").upsert({
            "user_id": user_id,
            "is_active": True,
            "subscription_end": new_end_date.isoformat()
        }).execute()

        send_telegram_notification(f"✅ <b>تأكيد دفع اشتراك تلقائي (OxaPay)!</b>\n🆔 المعرف: <code>{user_id}</code>")
        
    return {"status": "ok"}


# ==========================================
# 🟢 القسم 4: إدارة وتوثيق أرقام تليجرام (Telegram Accounts APIs)
# ==========================================
@app.get("/api/user-stats")
async def get_user_stats(user_id: str):
    try:
        accounts_res = supabase.table("telegram_accounts") \
            .select("id", count="exact") \
            .eq("user_id", user_id) \
            .execute()
        
        total_accounts = accounts_res.count if accounts_res.count is not None else len(accounts_res.data)

        sub_res = supabase.table("users_subscriptions") \
            .select("is_active, subscription_end") \
            .eq("user_id", user_id) \
            .execute()

        is_active = False
        ends_at = "غير محدد"

        if sub_res.data and len(sub_res.data) > 0:
            is_active = sub_res.data[0].get("is_active", False)
            raw_end = sub_res.data[0].get("subscription_end")
            if raw_end:
                ends_at = str(raw_end)[:10]

        return {
            "status": "success",
            "stats": {
                "total_accounts": total_accounts,
                "is_active": is_active,
                "subscription_status": "نشط 🟢" if is_active else "غير مفعل 🔴",
                "subscription_end": ends_at
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"فشل جلب الإحصائيات: {str(e)}")

@app.get("/api/account-count")
async def get_account_count(user_id: str):
    response = supabase.table("telegram_accounts").select("id", count="exact").eq("user_id", user_id).execute()
    return {"count": response.count if response.count is not None else len(response.data)}

@app.get("/api/get-accounts")
async def get_accounts(user_id: str):
    try:
        res = supabase.table("telegram_accounts").select("phone").eq("user_id", user_id).execute()
        return {"status": "success", "accounts": res.data if res.data else []}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/delete-account")
async def delete_account(req: DeleteAccountRequest):
    try:
        supabase.table("telegram_accounts") \
            .delete() \
            .eq("user_id", req.user_id) \
            .eq("phone", req.phone) \
            .execute()
        return {"status": "success", "message": f"تم حذف الحساب {req.phone} بنجاح!"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/send-code")
async def send_code(req: PhoneRequest):
    if not check_user_subscription(req.user_id):
        raise HTTPException(status_code=403, detail="عذراً، يجب تفعيل الاشتراك أولاً.")

    phone = req.phone_number.strip().replace(" ", "")
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    
    try:
        sent_code = await client.send_code_request(phone)
        
        pending_sessions[str(req.user_id)] = {
            "client": client,
            "phone": phone,
            "phone_code_hash": sent_code.phone_code_hash
        }
        
        return {
            "status": "success", 
            "phone_code_hash": sent_code.phone_code_hash, 
            "message": "تم إرسال الكود بنجاح! افحص تطبيق تليجرام."
        }
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=f"فشل إرسال الكود: {str(e)}")

@app.get("/api/stats")
async def get_stats(user_id: str):
    try:
        accounts_res = supabase.table("telegram_accounts") \
            .select("id", count="exact") \
            .eq("user_id", user_id) \
            .execute()
        
        total_accounts = accounts_res.count if accounts_res.count is not None else len(accounts_res.data)

        sub_res = supabase.table("users_subscriptions") \
            .select("is_active") \
            .eq("user_id", user_id) \
            .execute()

        is_active = False
        if sub_res.data and len(sub_res.data) > 0:
            is_active = sub_res.data[0].get("is_active", False)

        return {
            "status": "success",
            "total": total_accounts,
            "active": total_accounts if is_active else 0
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
@app.post("/api/verify-code")
async def verify_code(req: VerifyRequest):
    if not check_user_subscription(req.user_id):
        raise HTTPException(status_code=403, detail="عذراً، يجب تفعيل الاشتراك أولاً.")

    user_key = str(req.user_id)
    session_data = pending_sessions.get(user_key)

    if not session_data:
        raise HTTPException(
            status_code=400, 
            detail="انتهت مهلة الجلسة أو لم تقم بطلب الكود أولاً. حاول طلب الكود من جديد."
        )

    client: TelegramClient = session_data["client"]
    phone_code_hash = session_data["phone_code_hash"]
    phone = session_data["phone"]

    if not client.is_connected():
        await client.connect()

    try:
        clean_code = req.code.strip().replace(" ", "")
        
        try:
            await client.sign_in(
                phone=phone, 
                code=clean_code, 
                phone_code_hash=phone_code_hash
            )
        except Exception as sign_in_err:
            if "SessionPasswordNeededError" in str(sign_in_err):
                if not req.password or not req.password.strip():
                    raise HTTPException(
                        status_code=400, 
                        detail="هذا الحساب محمي بالتحقق بخطوتين (2FA). يرجى أدخال كلمة السر في الخانة المخصصة."
                    )
                await client.sign_in(password=req.password.strip())
            else:
                raise sign_in_err
        
        final_session = client.session.save()
        await client.disconnect()

        supabase.table("telegram_accounts").insert({
            "user_id": req.user_id,
            "phone": phone,
            "session_string": final_session
        }).execute()

        if user_key in pending_sessions:
            del pending_sessions[user_key]

        return {"status": "success", "message": "🟢 تم ربط الرقم بنجاح وإضافته للأسطول!"}
        
    except Exception as e:
        err_msg = str(e)
        if "PasswordHashInvalidError" in err_msg:
            raise HTTPException(status_code=400, detail="كلمة سر التحقق بخطوتين (2FA) غير صحيحة.")
        elif "PhoneCodeInvalidError" in err_msg:
            raise HTTPException(status_code=400, detail="الكود الذي أدخلته غير صحيح. تأكد من الأرقام وأعد المحاولة.")
        elif "PhoneCodeExpiredError" in err_msg:
            await client.disconnect()
            if user_key in pending_sessions:
                del pending_sessions[user_key]
            raise HTTPException(status_code=400, detail="انتهت صلاحية الكود. يرجى طلب كود جديد.")
        else:
            raise HTTPException(status_code=400, detail=f"خطأ في التحقق: {err_msg}")


# ==========================================
# 🟢 القسم 5: أمر إطلاق عملية الإضافة (Trigger Endpoint)
# ==========================================
@app.post("/api/start-adding")
async def start_adding(req: AddMembersRequest):
    if not check_user_subscription(req.user_id):
        raise HTTPException(status_code=403, detail="عذراً، يجب تفعيل الاشتراك أولاً.")

    accounts = supabase.table("telegram_accounts").select("session_string, phone").eq("user_id", req.user_id).execute()
    if not accounts.data:
        raise HTTPException(status_code=400, detail="لا توجد حسابات مربوطة في أسطولك.")

    asyncio.create_task(run_heavy_duty_engine(accounts.data, req.source_group, req.target_group))
    return {"status": "success", "message": f"⚡ تم البدء بالفعل عبر ({len(accounts.data)}) حساب! الأعضاء يضافون الآن لجروبك."}


# ==========================================
# 🟢 القسم 6: المحرك الخارق (سحب، انضمام، وإضافة متوازية)
# ==========================================
async def safe_join_chat(client: TelegramClient, raw_url: str) -> bool:
    clean_url = raw_url.strip()
    if "+" in clean_url or "joinchat" in clean_url:
        match = re.search(r'(?:\+|\/joinchat\/)([a-zA-Z0-9_-]+)', clean_url)
        if match:
            invite_hash = match.group(1)
            try:
                await client(ImportChatInviteRequest(invite_hash))
                return True
            except UserAlreadyParticipantError:
                return True
            except Exception:
                return False
    
    clean_name = clean_url.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").strip()
    try:
        entity = await client.get_entity(clean_name)
        await client(JoinChannelRequest(entity))
        return True
    except UserAlreadyParticipantError:
        return True
    except Exception:
        return False

# الإعدادات السرعة والتحكم
MAX_ADDS_PER_ACCOUNT = 50
MIN_DELAY = 2.0  # سرعة خاطفة ودبابة
MAX_DELAY = 4.0  # حماية ذكية ومضادة للحظر

async def get_active_sessions():
    try:
        res = supabase.table("telegram_accounts").select("*").in_("status", ["ready", "active"]).execute()
        return res.data
    except Exception as e:
        print(f"❌ خطأ أثناء جلب الحسابات: {e}")
        return []

# المحرك الأسطوري المدمج (سحب ذكي + إضافة متوازية خرافية)
async def dragon_ultimate_engine():
    print("🔥 [DRAGON ULTIMATE ENGINE v3.0] تم إطلاق المحرك الأقوى في الواقع.. جاهز لكسح الجميع!")
    
    while True:
        try:
            mission_res = supabase.table("adding_missions").select("*").eq("status", "running").execute()
            missions = mission_res.data
            
            if not missions:
                await asyncio.sleep(2)
                continue
                
            for mission in missions:
                mission_id = mission['id']
                source_raw = mission['source_group']
                target_raw = mission['destination_group']
                filter_type = mission.get('filter_type', 'all')
                
                print(f"\n🚀 [بدء المعركة الكبرى] غزو الوجهة: {target_raw} من المصدر: {source_raw}")
                
                account_list = await get_active_sessions()
                if not account_list:
                    print("⚠️ تحذير: لا توجد حسابات نشطة في الأسطول!")
                    supabase.table("adding_missions").update({
                        "status": "failed", 
                        "status_log": "فشلت المهمة: لا توجد حسابات جاهزة في الأسطول."
                    }).eq("id", mission_id).execute()
                    continue

                master_acc = account_list[0]
                master_client = TelegramClient(StringSession(master_acc['session_string']), API_ID, API_HASH)
                scraped_users = []
                seen_ids = set()

                try:
                    await master_client.connect()
                    await safe_join_chat(master_client, source_raw)
                    
                    src_entity = await master_client.get_entity(source_raw.replace("https://t.me/", "").replace("@", "").strip())
                    
                    participants = await master_client.get_participants(src_entity, limit=3000)
                    for u in participants:
                        if not getattr(u, 'bot', False) and not getattr(u, 'deleted', False) and u.username:
                            if filter_type == "online" and not hasattr(u.status, 'UserStatusOnline'): 
                                continue
                            if u.id not in seen_ids:
                                seen_ids.add(u.id)
                                scraped_users.append(u)

                    async for message in master_client.iter_messages(src_entity, limit=3000):
                        if message.sender_id and message.sender_id not in seen_ids:
                            try:
                                user = await master_client.get_entity(message.sender_id)
                                if not getattr(user, 'bot', False) and not getattr(user, 'deleted', False) and user.username:
                                    seen_ids.add(user.id)
                                    scraped_users.append(user)
                            except Exception:
                                pass
                                
                        if hasattr(message, 'reactions') and message.reactions and getattr(message.reactions, 'recent_reactions', None):
                            for reaction in message.reactions.recent_reactions:
                                u_id = getattr(reaction.peer_id, 'user_id', None)
                                if u_id and u_id not in seen_ids:
                                    try:
                                        user = await master_client.get_entity(u_id)
                                        if not getattr(user, 'bot', False) and not getattr(user, 'deleted', False) and user.username:
                                            seen_ids.add(user.id)
                                            scraped_users.append(user)
                                    except Exception:
                                        pass

                    print(f"🎯 [تم بنجاح] تم استخراج وتصفية {len(scraped_users)} عضو حقيقي ومتفاعل جاهز للضخ الفوري.")
                except Exception as e:
                    print(f"❌ فشل الرادار الرئيسي في السحب: {e}")
                    supabase.table("adding_missions").update({
                        "status": "failed", 
                        "status_log": f"فشل السحب من المصدر: {str(e)}"
                    }).eq("id", mission_id).execute()
                    continue
                finally:
                    await master_client.disconnect()

                if not scraped_users:
                    supabase.table("adding_missions").update({
                        "status": "completed", 
                        "status_log": "انتهى الفحص: لم يتم العثور على أعضاء مطابقين."
                    }).eq("id", mission_id).execute()
                    continue

                acc_index = 0
                added_count = mission.get('progress', 0)
                account_stats = {}

                for user in scraped_users:
                    if not account_list:
                        print("🚨 نفدت جميع حسابات الأسطول!")
                        supabase.table("adding_missions").update({
                            "status": "failed", 
                            "status_log": f"توقف: نفدت الحسابات بعد نقل {added_count} عضو."
                        }).eq("id", mission_id).execute()
                        break
                        
                    if acc_index >= len(account_list):
                        acc_index = 0
                        
                    current_acc = account_list[acc_index]
                    phone = current_acc.get("phone", "Unknown")
                    
                    if account_stats.get(phone, 0) >= MAX_ADDS_PER_ACCOUNT:
                        print(f"🎖️ الحساب +{phone} أتم حصته الكاملة ({MAX_ADDS_PER_ACCOUNT} عضو)، يتم تدويره لإراحة الحساب.")
                        account_list.pop(acc_index)
                        continue

                    client = TelegramClient(StringSession(current_acc['session_string']), API_ID, API_HASH)

                    try:
                        await client.connect()
                        
                        await safe_join_chat(client, target_raw)
                        
                        target_clean = target_raw.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").strip()
                        target_entity = await client.get_entity(target_clean)
                        
                        user_to_add = await client.get_input_entity(user)
                        await client(InviteToChannelRequest(target_entity, [user_to_add]))
                        
                        added_count += 1
                        account_stats[phone] = account_stats.get(phone, 0) + 1
                        
                        print(f"⚡ [نجاح ساحق] الحساب +{phone} أضاف @{user.username} | إجمالي المجموع: {added_count}")
                        
                        supabase.table("adding_missions").update({
                            "progress": added_count,
                            "status_log": f"الحساب +{phone} أضاف العضو @{user.username} بنجاح (العدد: {added_count})"
                        }).eq("id", mission_id).execute()
                        
                        await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                        
                    except ChatAdminRequiredError:
                        print(f"🚨 خطأ: مجموعة الوجهة مغلقة وصلاحيات الإضافة للمشرفين فقط!")
                        supabase.table("adding_missions").update({
                            "status": "failed",
                            "status_log": "فشلت المهمة: مجموعة الوجهة مغلقة ولا تقبل الإضافة العادية."
                        }).eq("id", mission_id).execute()
                        break

                    except FloodWaitError as e:
                        print(f"⚠️ الحساب +{phone} اصطدم بفلوود ({e.seconds} ثانية).. استبدال فوري.")
                        account_list.pop(acc_index)
                        try:
                            supabase.table("telegram_accounts").update({"status": "cooldown"}).eq("id", current_acc['id']).execute()
                        except Exception:
                            pass
                        continue
                        
                    except UserPrivacyRestrictedError:
                        continue
                        
                    except UserAlreadyParticipantError:
                        continue
                        
                    except Exception as error:
                        print(f"❌ عطل في الحساب +{phone}: {error}")
                        try:
                            supabase.table("telegram_accounts").update({"status": "banned"}).eq("id", current_acc['id']).execute()
                        except Exception:
                            pass
                        account_list.pop(acc_index)
                        continue
                    finally:
                        await client.disconnect()
                        
                    acc_index += 1

                supabase.table("adding_missions").update({
                    "status": "completed", 
                    "status_log": f"👑 اكتملت الحملة بنجاح أسطوري! تم ضخ {added_count} عضو حقيقي."
                }).eq("id", mission_id).execute()
                print(f"🏁 انتهت المهمة بنجاح تام. إجمالي المنقولين: {added_count}")

        except Exception as global_error:
            print(f"🚨 خطأ عام بالمحرك: {global_error}")
            await asyncio.sleep(3)


async def run_heavy_duty_engine(accounts_data: list, source_group: str, target_group: str):
    if not accounts_data:
        await send_telegram_notification("❌ لا توجد حسابات مضافة للتشغيل!")
        return

    master_acc = accounts_data[0]
    master_client = TelegramClient(StringSession(master_acc["session_string"]), API_ID, API_HASH)

    scraped_users = []
    try:
        await master_client.connect()
        if not await master_client.is_user_authorized():
            await send_telegram_notification("❌ الحساب الرئيسي لسحب الأعضاء غير مفعل!")
            return

        await send_telegram_notification("🔍 جاري انضمام الحساب الرئيسي وسحب الأعضاء من المصدر...")
        await safe_join_chat(master_client, source_group)
        
        src_clean = source_group.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").strip()
        src_entity = await master_client.get_entity(src_clean)
        
        participants = await master_client.get_participants(src_entity, limit=3000)
        for u in participants:
            if not getattr(u, 'bot', False) and not getattr(u, 'deleted', False) and u.username:
                scraped_users.append(u)

    except Exception as e:
        await send_telegram_notification(f"💥 خطأ أثناء سحب الأعضاء: {e}")
        return
    finally:
        await master_client.disconnect()

    if not scraped_users:
        await send_telegram_notification("❌ لم يتم العثور على أعضاء أو الجروب المصدر محمي من السحب!")
        return

    await send_telegram_notification(f"🔥 تم سحب ({len(scraped_users)}) عضو بنجاح! جاري التشغيل...")


# ==========================================
# 📊 API الإحصائيات التفصيلية (سجل الإضافات)
# ==========================================
@app.get("/api/detailed-stats")
async def get_detailed_stats(user_id: str, campaign_id: Optional[int] = None):
    try:
        if not campaign_id:
            camps = supabase.table("adding_campaigns") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
            if not camps.data:
                return {"status": "success", "has_data": False, "message": "لا توجد عمليات سابقة."}
            campaign = camps.data[0]
            campaign_id = campaign["id"]
        else:
            camp_res = supabase.table("adding_campaigns").select("*").eq("id", campaign_id).eq("user_id", user_id).execute()
            if not camp_res.data:
                raise HTTPException(status_code=404, detail="العملية غير موجودة")
            campaign = camp_res.data[0]

        logs_res = supabase.table("adding_logs") \
            .select("account_phone, status") \
            .eq("campaign_id", campaign_id) \
            .execute()

        per_account_stats = {}
        for log in logs_res.data:
            phone = log["account_phone"]
            status = log["status"]
            if phone not in per_account_stats:
                per_account_stats[phone] = {"success": 0, "failed": 0, "total": 0}
            
            per_account_stats[phone]["total"] += 1
            if status == "success":
                per_account_stats[phone]["success"] += 1
            else:
                per_account_stats[phone]["failed"] += 1

        recent_logs = supabase.table("adding_logs") \
            .select("account_phone, target_username, status, created_at") \
            .eq("campaign_id", campaign_id) \
            .order("created_at", desc=True) \
            .limit(50) \
            .execute()

        return {
            "status": "success",
            "has_data": True,
            "campaign": campaign,
            "per_account_stats": per_account_stats,
            "recent_logs": recent_logs.data if recent_logs.data else []
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
