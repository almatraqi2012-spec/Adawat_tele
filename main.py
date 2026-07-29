import os
import asyncio
import requests
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.errors import PeerFloodError, UserPrivacyRestrictedError, FloodWaitError
from supabase import create_client, Client

# ==========================================
# 1. الإعدادات والربط
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://juuleypxvvcfgjdikpwu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_Kh6iN4Aq6X6gLNcElNzgRg_CjlLMaZL")

API_ID = int(os.getenv("TELEGRAM_API_ID", "21349867"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "7ced3ee4c80117bd5138410811b91f9f")

# مفتاح OxaPay (ضع مفتاحك الخاص من لوحة OxaPay)
OXAPAY_MERCHANT_KEY = os.getenv("OXAPAY_MERCHANT_KEY", "VVWSV1-17YEGL-05LITH-PLZ5EX")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI(title="Dragon Engine with OxaPay Subscription")

pending_sessions = {}
MONTHLY_PRICE_USD = 80

# ==========================================
# 2. النماذج (Data Models)
# ==========================================
class PhoneRequest(BaseModel):
    user_id: str
    phone_number: str

class VerifyRequest(BaseModel):
    user_id: str
    phone_number: str
    phone_code_hash: str
    code: str

class AddMembersRequest(BaseModel):
    user_id: str
    source_group: str
    target_group: str

class PaymentRequest(BaseModel):
    user_id: str

# ==========================================
# 3. دواعي فحص الاشتراك
# ==========================================
def check_user_subscription(user_id: str) -> bool:
    """التحقق مما إذا كان للمستخدم اشتراك ساري بـ 80$"""
    res = supabase.table("users_subscriptions").select("*").eq("user_id", user_id).execute()
    if not res.data:
        return False
    
    sub = res.data[0]
    if not sub.get("is_active"):
        return False

    sub_end_str = sub.get("subscription_end")
    if not sub_end_str:
        return False

    # مقارنة التاريخ
    sub_end = datetime.fromisoformat(sub_end_str.replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > sub_end:
        # انتهى الاشتراك
        supabase.table("users_subscriptions").update({"is_active": False}).eq("user_id", user_id).execute()
        return False

    return True

# ==========================================
# 4. الواجهة التفاعلية (مع بوابات الدفع)
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dragon Engine - منصة إضافة الأعضاء والاشتراكات</title>
        <style>
            body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; display: flex; justify-content: center; }
            .card { background: #1e293b; padding: 25px; border-radius: 12px; max-width: 500px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }
            h2 { color: #38bdf8; text-align: center; margin-bottom: 15px; font-size: 22px; }
            
            .sub-box { background: #1e1b4b; border: 1px solid #6366f1; border-radius: 8px; padding: 15px; text-align: center; margin-bottom: 20px; }
            .sub-status { font-weight: bold; font-size: 16px; margin-bottom: 10px; }
            .active { color: #34d399; }
            .inactive { color: #f87171; }
            
            .counter-box { background: #0f172a; border: 1px solid #38bdf8; border-radius: 8px; padding: 10px; text-align: center; margin-bottom: 20px; font-size: 14px; }
            .counter-box span { font-size: 20px; font-weight: bold; color: #38bdf8; }

            h3 { font-size: 16px; color: #e2e8f0; margin-top: 0; }
            label { display: block; margin-top: 12px; font-size: 13px; color: #94a3b8; }
            input { width: 100%; padding: 12px; margin-top: 6px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; box-sizing: border-box; font-size: 15px; }
            button { width: 100%; padding: 12px; margin-top: 10px; border: none; border-radius: 8px; background: #0284c7; color: white; font-size: 15px; font-weight: bold; cursor: pointer; }
            .btn-green { background: #16a34a; }
            .btn-orange { background: #ea580c; }
            .status { margin-top: 15px; padding: 12px; border-radius: 8px; font-size: 14px; display: none; }
            .success { background: #065f46; color: #34d399; }
            .error { background: #881337; color: #fecdd3; }
            hr { border: 0; height: 1px; background: #334155; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🐉 محرك Dragon لإضافة الأعضاء</h2>
            
            <!-- قسم حالة الاشتراك والدفع -->
            <div class="sub-box">
                <div class="sub-status">حالة الاشتراك الشهري ($80): <span id="subText" class="inactive">جاري التحقق...</span></div>
                <button onclick="payOxaPay()" class="btn-orange">💳 تجديد/اشتراك تلقائي عبر OxaPay ($80)</button>
                <div style="font-size: 12px; color: #94a3b8; margin-top: 8px;">للدفع اليدوي (تواصل مع الدعم الفني للبوت للتفعيل الفوري)</div>
            </div>

            <!-- عداد الحسابات -->
            <div class="counter-box">
                حسابات الأسطول المربوطة: <span id="accountCount">0</span> حساب
            </div>
            
            <h3>1️⃣ ربط أرقام الجلسات</h3>
            <label>رقم الهاتف (مع المفتاح الدولي):</label>
            <input type="text" id="phone" placeholder="+966500000000">
            <button onclick="sendCode()">أرسل كود التحقق</button>
            
            <div id="verifyBox" style="display:none;">
                <label>كود التحقق:</label>
                <input type="text" id="otpCode" placeholder="12345">
                <button onclick="verifyCode()" class="btn-green">حفظ الرقم في المنظومة</button>
            </div>
            
            <hr>
            
            <h3>2️⃣ تشغيل الحملة</h3>
            <label>الجروب المصدر:</label>
            <input type="text" id="sourceGroup" placeholder="https://t.me/source_group">
            
            <label>الجروب الهدف:</label>
            <input type="text" id="targetGroup" placeholder="https://t.me/target_group">
            
            <button onclick="startAdding()" class="btn-green">🚀 بدء التناوب والإضافة</button>
            
            <div id="statusBox" class="status"></div>
        </div>

        <script>
            let USER_ID = localStorage.getItem("user_device_id");
            if (!USER_ID) {
                USER_ID = 'user_' + Math.random().toString(36).substr(2, 9);
                localStorage.setItem("user_device_id", USER_ID);
            }

            let phoneHash = "";

            async function checkSub() {
                try {
                    const res = await fetch(`/api/subscription-status?user_id=${USER_ID}`);
                    const data = await res.json();
                    const el = document.getElementById("subText");
                    if(data.is_active) {
                        el.innerText = "نشط 🟢 (حتى " + data.ends_at + ")";
                        el.className = "active";
                    } else {
                        el.innerText = "غير مفعل 🔴";
                        el.className = "inactive";
                    }
                } catch(e){}
            }

            async function updateCount() {
                try {
                    const res = await fetch(`/api/account-count?user_id=${USER_ID}`);
                    const data = await res.json();
                    if(res.ok) document.getElementById("accountCount").innerText = data.count;
                } catch(e){}
            }

            checkSub();
            updateCount();

            function showStatus(msg, isError = false) {
                const box = document.getElementById("statusBox");
                box.style.display = "block";
                box.className = "status " + (isError ? "error" : "success");
                box.innerText = msg;
            }

            async function payOxaPay() {
                showStatus("جاري إنشاء رابط الدفع عبر OxaPay...");
                const res = await fetch("/api/create-oxapay-payment", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({user_id: USER_ID})
                });
                const data = await res.json();
                if(res.ok && data.pay_url) {
                    window.location.href = data.pay_url; // التوجيه لبوابة الدفع
                } else {
                    showStatus(data.detail || "فشل إنشاء رابط الدفع", true);
                }
            }

            async function sendCode() {
                const phone = document.getElementById("phone").value.trim();
                if(!phone) return alert("أدخل الرقم أولاً");

                showStatus("جاري إرسال الكود...");
                const res = await fetch("/api/send-code", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({user_id: USER_ID, phone_number: phone})
                });
                const data = await res.json();
                if(res.ok) {
                    phoneHash = data.phone_code_hash;
                    document.getElementById("verifyBox").style.display = "block";
                    showStatus(data.message);
                } else {
                    showStatus(data.detail || "حدث خطأ", true);
                }
            }

            async function verifyCode() {
                const phone = document.getElementById("phone").value.trim();
                const code = document.getElementById("otpCode").value.trim();

                showStatus("جاري التأكد وحفظ الرقم...");
                const res = await fetch("/api/verify-code", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({user_id: USER_ID, phone_number: phone, phone_code_hash: phoneHash, code: code})
                });
                const data = await res.json();
                if(res.ok) {
                    showStatus(data.message);
                    updateCount();
                } else {
                    showStatus(data.detail, true);
                }
            }

            async function startAdding() {
                const source = document.getElementById("sourceGroup").value.trim();
                const target = document.getElementById("targetGroup").value.trim();

                showStatus("🔥 جاري تشغيل المحرك...");
                const res = await fetch("/api/start-adding", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({user_id: USER_ID, source_group: source, target_group: target})
                });
                const data = await res.json();
                if(res.ok) {
                    showStatus(data.message);
                } else {
                    showStatus(data.detail, true);
                }
            }
        </script>
    </body>
    </html>
    """

# ==========================================
# 5. APIs الدفع والاشتراكات
# ==========================================

@app.get("/api/subscription-status")
async def subscription_status(user_id: str):
    res = supabase.table("users_subscriptions").select("*").eq("user_id", user_id).execute()
    if res.data and res.data[0].get("is_active"):
        end_date = res.data[0].get("subscription_end", "")[:10]
        return {"is_active": True, "ends_at": end_date}
    return {"is_active": False}

@app.post("/api/create-oxapay-payment")
async def create_oxapay_payment(req: PaymentRequest):
    """إنشاء طلب دفع تلقائي عبر OxaPay بـ $80"""
    payload = {
        "merchant": OXAPAY_MERCHANT_KEY,
        "amount": MONTHLY_PRICE_USD,
        "currency": "USD",
        "lifeTime": 60,
        "feePaidByUser": 0,
        "orderId": req.user_id,
        "callbackUrl": "https://adawat-tele.vercel.app/api/oxapay-webhook", # رابط الـ Webhook الخاص بك
        "description": "اشتراك شهري في محرك إضافة الأعضاء Dragon Engine"
    }
    try:
        response = requests.post("https://api.oxapay.com/merchants/request", json=payload).json()
        if response.get("result") == 100:
            return {"pay_url": response.get("payLink")}
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "خطأ في بوابة OxaPay"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/oxapay-webhook")
async def oxapay_webhook(request: Request):
    """استقبال التأكيد التلقائي عند اكتمال الدفع من OxaPay"""
    data = await request.json()
    if data.get("status") == "Paid":
        user_id = data.get("orderId")
        new_end_date = datetime.now(timezone.utc) + timedelta(days=30)
        
        # تفعيل الاشتراك لمدة 30 يوماً
        supabase.table("users_subscriptions").upsert({
            "user_id": user_id,
            "is_active": True,
            "subscription_end": new_end_date.isoformat()
        }).execute()
        
    return {"status": "ok"}

# تفعيل يدوي من الأدمن (عبر API أو البوت)
@app.post("/api/admin/manual-activate")
async def manual_activate(user_id: str, days: int = 30):
    new_end_date = datetime.now(timezone.utc) + timedelta(days=days)
    supabase.table("users_subscriptions").upsert({
        "user_id": user_id,
        "is_active": True,
        "subscription_end": new_end_date.isoformat()
    }).execute()
    return {"message": f"تم تفعيل الاشتراك يدوياً للمستخدم {user_id} لمدة {days} يوم."}

# ==========================================
# 6. باقي الخدمات (مجهزة بشرط فحص الاشتراك)
# ==========================================

@app.get("/api/account-count")
async def get_account_count(user_id: str):
    response = supabase.table("telegram_accounts").select("id", count="exact").eq("user_id", user_id).execute()
    return {"count": response.count if response.count is not None else len(response.data)}

@app.post("/api/send-code")
async def send_code(req: PhoneRequest):
    # فحص الاشتراك أولاً
    if not check_user_subscription(req.user_id):
        raise HTTPException(status_code=403, detail="عذراً، يجب تجديد اشتراكك الشهري ($80) أولاً لاستخدام الخدمة.")

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent_code = await client.send_code_request(req.phone_number)
        pending_sessions[req.phone_number] = client.session.save()
        await client.disconnect()
        return {"status": "success", "phone_code_hash": sent_code.phone_code_hash, "message": "تم إرسال الكود بنجاح!"}
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/verify-code")
async def verify_code(req: VerifyRequest):
    if not check_user_subscription(req.user_id):
        raise HTTPException(status_code=403, detail="عذراً، يجب تجديد اشتراكك الشهري ($80) أولاً.")

    session_str = pending_sessions.get(req.phone_number)
    if not session_str:
        raise HTTPException(status_code=400, detail="انتهت الجلسة.")

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    try:
        await client.sign_in(phone=req.phone_number, code=req.code, phone_code_hash=req.phone_code_hash)
        final_session = client.session.save()
        await client.disconnect()

        supabase.table("telegram_accounts").insert({
            "user_id": req.user_id,
            "phone": req.phone_number,
            "session_string": final_session
        }).execute()

        del pending_sessions[req.phone_number]
        return {"status": "success", "message": "🟢 تم تفعيل الرقم بنجاح وإضافته للأسطول!"}
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=f"خطأ في التحقق: {str(e)}")

@app.post("/api/start-adding")
async def start_adding(req: AddMembersRequest):
    if not check_user_subscription(req.user_id):
        raise HTTPException(status_code=403, detail="عذراً، اشتراكك انتهى أو غير مفعل. قم بدفع $80 للتجديد.")

    accounts = supabase.table("telegram_accounts").select("session_string, phone").eq("user_id", req.user_id).execute()
    if not accounts.data:
        raise HTTPException(status_code=400, detail="لا توجد حسابات مربوطة.")

    asyncio.create_task(run_multi_account_engine(accounts.data, req.source_group, req.target_group))
    return {"status": "success", "message": f"⚡ تم تشغيل الحملة بـ ({len(accounts.data)}) حساب! المحرك يعمل في الخلفية."}

# ==========================================
# 7. محرك Dragon للتناوب
# ==========================================
async def run_multi_account_engine(accounts_data, source, target):
    if not accounts_data:
        return

    target_users = {}
    first_acc = accounts_data[0]
    master_client = TelegramClient(StringSession(first_acc["session_string"]), API_ID, API_HASH)
    
    try:
        await master_client.connect()
        src_entity = await master_client.get_entity(source)

        try:
            participants = await master_client.get_participants(src_entity, limit=2000)
            for u in participants:
                if not u.bot and not u.deleted:
                    target_users[u.id] = u
        except Exception:
            pass

        async for message in master_client.iter_messages(src_entity, limit=300):
            if message.sender_id and message.sender:
                if not getattr(message.sender, 'bot', False) and not getattr(message.sender, 'deleted', False):
                    target_users[message.sender_id] = message.sender

    except Exception as e:
        print(f"Error scraping: {e}")
        return
    finally:
        await master_client.disconnect()

    user_list = list(target_users.values())
    if not user_list:
        return

    user_index = 0
    total_users = len(user_list)

    for acc in accounts_data:
        if user_index >= total_users:
            break

        client = TelegramClient(StringSession(acc["session_string"]), API_ID, API_HASH)
        added_by_this_account = 0
        MAX_PER_ACCOUNT = 40

        try:
            await client.connect()
            if not await client.is_user_authorized():
                continue

            trg_entity = await client.get_entity(target)

            while added_by_this_account < MAX_PER_ACCOUNT and user_index < total_users:
                user_to_add = user_list[user_index]
                user_index += 1

                try:
                    await client(InviteToChannelRequest(trg_entity, [user_to_add]))
                    added_by_this_account += 1
                    await asyncio.sleep(10)

                except (PeerFloodError, FloodWaitError):
                    break
                except UserPrivacyRestrictedError:
                    continue
                except Exception:
                    continue

        except Exception as acc_err:
            print(f"Session Error: {acc_err}")
        finally:
            await client.disconnect()
            
        await asyncio.sleep(3)
