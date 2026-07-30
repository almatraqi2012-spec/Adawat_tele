import os
import asyncio
import random
import uuid
import requests
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase import create_client, Client

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest
from telethon.tl.types import InputPeerUser
from telethon.errors import (
    PeerFloodError,
    UserPrivacyRestrictedError,
    FloodWaitError,
    UserNotMutualContactError,
    UserIdInvalidError,
    UserChannelsTooMuchError,
    UserBotError
)

# ==========================================
# 1. الإعدادات والربط
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://juuleypxvvcfgjdikpwu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_Kh6iN4Aq6X6gLNcElNzgRg_CjlLMaZL")

API_ID = int(os.getenv("TELEGRAM_API_ID", "21349867"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "7ced3ee4c80117bd5138410811b91f9f")

OXAPAY_MERCHANT_KEY = os.getenv("OXAPAY_MERCHANT_KEY", "VVWSV1-17YEGL-05LITH-PLZ5EX")
ADMIN_TELEGRAM_BOT_TOKEN = os.getenv("ADMIN_TELEGRAM_BOT_TOKEN", "8725004596:AAF7fH3qyLq4nhRRp3RIbVGQj8bMo632oM8")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "6016547718")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Shrkatbot")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI(title="Dragon Engine - Heavy Duty Edition")

pending_sessions = {}
MONTHLY_PRICE_USD = 80
USDT_ADDRESS = "TLtLuhkU2kkkR1Wz1TtrBTpoNRTNviYpsA"

# ==========================================
# 2. النماذج (Data Models)
# ==========================================
class RegisterUserRequest(BaseModel):
    full_name: str
    username_or_phone: str

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
# 3. الوظائف المساعدة والاشتراكات
# ==========================================
def send_telegram_notification(message: str):
    if ADMIN_TELEGRAM_BOT_TOKEN != "YOUR_BOT_TOKEN" and ADMIN_CHAT_ID != "YOUR_TELEGRAM_CHAT_ID":
        try:
            url = f"https://api.telegram.org/bot{ADMIN_TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "HTML"})
        except Exception as e:
            print(f"Failed to send Telegram notification: {e}")

def check_user_subscription(user_id: str) -> bool:
    res = supabase.table("users_subscriptions").select("*").eq("user_id", user_id).execute()
    if not res.data:
        return False
    
    sub = res.data[0]
    if not sub.get("is_active"):
        return False

    sub_end_str = sub.get("subscription_end")
    if not sub_end_str:
        return False

    sub_end = datetime.fromisoformat(sub_end_str.replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > sub_end:
        supabase.table("users_subscriptions").update({"is_active": False}).eq("user_id", user_id).execute()
        return False

    return True

# ==========================================
# 4. الواجهة التفاعلية
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dragon Engine Pro - المحرك الخارق</title>
        <style>
            body {{ font-family: system-ui, -apple-system, sans-serif; background: #0b0f19; color: #f8fafc; padding: 20px; display: flex; justify-content: center; }}
            .card {{ background: #111827; padding: 25px; border-radius: 16px; max-width: 520px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.6); border: 1px solid #1f2937; }}
            h2 {{ color: #38bdf8; text-align: center; margin-bottom: 15px; font-size: 22px; font-weight: 800; }}
            
            .sub-box {{ background: #1e1b4b; border: 1px solid #6366f1; border-radius: 10px; padding: 15px; text-align: center; margin-bottom: 20px; }}
            .sub-status {{ font-weight: bold; font-size: 16px; margin-bottom: 10px; }}
            .active {{ color: #34d399; }}
            .inactive {{ color: #f87171; }}
            
            .counter-box {{ background: #0f172a; border: 1px solid #38bdf8; border-radius: 10px; padding: 12px; text-align: center; margin-bottom: 20px; font-size: 14px; color: #94a3b8; }}
            .counter-box span {{ font-size: 22px; font-weight: bold; color: #38bdf8; }}

            label {{ display: block; margin-top: 12px; font-size: 13px; color: #94a3b8; }}
            input {{ width: 100%; padding: 12px; margin-top: 6px; border-radius: 8px; border: 1px solid #374151; background: #030712; color: white; box-sizing: border-box; font-size: 15px; }}
            button {{ width: 100%; padding: 12px; margin-top: 10px; border: none; border-radius: 8px; background: #0284c7; color: white; font-size: 15px; font-weight: bold; cursor: pointer; transition: 0.2s; }}
            button:hover {{ opacity: 0.9; transform: translateY(-1px); }}
            .btn-green {{ background: #059669; }}
            .btn-orange {{ background: #ea580c; }}
            .btn-purple {{ background: #7c3aed; }}
            
            .status {{ margin-top: 15px; padding: 12px; border-radius: 8px; font-size: 14px; display: none; line-height: 1.5; }}
            .success {{ background: #064e3b; color: #34d399; border: 1px solid #059669; }}
            .error {{ background: #4c0519; color: #fecdd3; border: 1px solid #9f1239; }}
            hr {{ border: 0; height: 1px; background: #1f2937; margin: 20px 0; }}

            .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); justify-content: center; align-items: center; z-index: 1000; backdrop-filter: blur(4px); }}
            .modal-content {{ background: #111827; padding: 25px; border-radius: 14px; max-width: 420px; width: 90%; text-align: center; border: 1px solid #38bdf8; }}
            .crypto-addr {{ background: #030712; padding: 10px; border-radius: 6px; font-family: monospace; font-size: 13px; color: #38bdf8; word-break: break-all; margin: 10px 0; border: 1px dashed #374151; }}
        </style>
    </head>
    <body>

        <!-- نافذة التسجيل -->
        <div id="registerModal" class="modal" style="display: flex;">
            <div class="modal-content">
                <h3 style="color: #38bdf8; margin-top:0;">⚡ دخول المنظومة الخارقة</h3>
                <p style="font-size: 13px; color: #94a3b8;">أدخل اسمك ومعرفك للتسجيل أو استعادة أسطولك المربوط</p>
                
                <label style="text-align: right;">الاسم الكامل:</label>
                <input type="text" id="regFullName" placeholder="أحمد علي">
                
                <label style="text-align: right;">اسم المستخدم أو رقم التلغرام:</label>
                <input type="text" id="regUserContact" placeholder="@username أو +966500000000">
                
                <button onclick="submitRegister()" class="btn-green">دخول / استعادة الحساب</button>
            </div>
        </div>

        <!-- نافذة الدفع اليدوي -->
        <div id="manualPayModal" class="modal">
            <div class="modal-content">
                <h3 style="color: #38bdf8; margin-top:0;">💎 الدفع اليدوي عبر USDT</h3>
                <p style="font-size: 14px; color: #e2e8f0;">حول <b>$80 USDT</b> على شبكة (TRC20):</p>
                
                <div class="crypto-addr" id="cryptoAddress">{USDT_ADDRESS}</div>
                <button onclick="copyCrypto()" style="padding: 6px; font-size: 12px; background: #374151;">نسخ العنوان 📋</button>
                
                <hr>
                <p style="font-size: 13px; color: #94a3b8;">بعد التحويل، اذكر ID حسابك للبوت لتفعيلك:</p>
                
                <button onclick="redirectToBot()" class="btn-green">📩 إرسال إثبات الدفع للبوت</button>
                <button onclick="closeModal('manualPayModal')" style="background: #4b5563; margin-top: 5px;">إغلاق</button>
            </div>
        </div>

        <!-- الواجهة الرئيسية -->
        <div class="card">
            <h2>🔥 Dragon Heavy Engine v2.0</h2>
            
            <div class="sub-box">
                <div style="font-size: 13px; color: #94a3b8; margin-bottom: 5px;">المستخدم الحالي: <b id="displayUserName" style="color: #f8fafc;">...</b></div>
                <div class="sub-status">حالة الاشتراك الشهري ($80): <span id="subText" class="inactive">جاري التحقق...</span></div>
                
                <button onclick="payOxaPay()" class="btn-orange">💳 دفع تلقائي OxaPay ($80)</button>
                <button onclick="openModal('manualPayModal')" class="btn-purple">💎 دفع يدوي USDT (TRC20)</button>
                <button onclick="logout()" style="background: #dc2626; margin-top: 5px; font-size: 12px; padding: 6px;">تبديل الحساب / خروج</button>
            </div>

            <div class="counter-box">
                🚀 أسطول الحسابات النشطة: <span id="accountCount">0</span> حساب جاهز
            </div>
            
            <h3>1️⃣ إضافة أرقام الأسطول</h3>
            <label>رقم الهاتف (مع رمز الدولة):</label>
            <input type="text" id="phone" placeholder="+966500000000">
            <button onclick="sendCode()">أرسل كود التحقق</button>
            
            <div id="verifyBox" style="display:none;">
                <label>كود التحقق الواصل للتليجرام:</label>
                <input type="text" id="otpCode" placeholder="12345">
                <button onclick="verifyCode()" class="btn-green">ربط الرقم بالأسطول 🛡️</button>
            </div>
            
            <hr>
            
            <h3>2️⃣ إطلاق الحملة الخارقة (توازٍ كامل)</h3>
            <label>الجروب المصدر (السحب منه):</label>
            <input type="text" id="sourceGroup" placeholder="https://t.me/source_group">
            
            <label>الجروب الهدف (الإضافة إليه):</label>
            <input type="text" id="targetGroup" placeholder="https://t.me/target_group">
            
            <button onclick="startAdding()" class="btn-green">⚡ إطلاق السحب والإضافة التوافقية</button>
            
            <div id="statusBox" class="status"></div>
        </div>

        <script>
            let USER_ID = localStorage.getItem("user_device_id");
            let USER_NAME = localStorage.getItem("user_full_name");

            if (USER_ID && USER_NAME) {{
                document.getElementById("registerModal").style.display = "none";
                document.getElementById("displayUserName").innerText = USER_NAME;
            }}

            let phoneHash = "";

            async function submitRegister() {{
                const fullNameInput = document.getElementById("regFullName");
                const contactInput = document.getElementById("regUserContact");

                const fullName = fullNameInput ? fullNameInput.value.trim() : "";
                const contact = contactInput ? contactInput.value.trim().toLowerCase() : "";

                if (!fullName || !contact) {{
                    return alert("يرجى إدخال اسمك واسم المستخدم/الرقم بشكل صحيح");
                }}

                try {{
                    showStatus("جاري البحث عن الحساب واستعادة البيانات...");
                    
                    const res = await fetch("/api/register-user", {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{
                            full_name: fullName,
                            username_or_phone: contact
                        }})
                    }});

                    const data = await res.json();
                    
                    if (res.ok && data.user_id) {{
                        localStorage.setItem("user_device_id", data.user_id);
                        localStorage.setItem("user_full_name", fullName);
                        localStorage.setItem("user_contact", contact);
                        
                        USER_ID = data.user_id;

                        document.getElementById("registerModal").style.display = "none";
                        document.getElementById("displayUserName").innerText = fullName;
                        
                        await checkSub();
                        await updateCount();

                        alert(data.message || "تم تسجيل الدخول بنجاح!");
                    }} else {{
                        alert("خطأ: " + (data.detail || "تعذر التسجيل"));
                    }}
                }} catch (err) {{
                    alert("تعذر الاتصال بالسيرفر، تأكد من الاتصال بالإنترنت.");
                }}
            }}

            function logout() {{
                localStorage.clear();
                location.reload();
            }}

            async function checkSub() {{
                if(!USER_ID) return;
                try {{
                    const res = await fetch(`/api/subscription-status?user_id=${{USER_ID}}`);
                    const data = await res.json();
                    const el = document.getElementById("subText");
                    if(data.is_active) {{
                        el.innerText = "نشط 🟢 (حتى " + data.ends_at + ")";
                        el.className = "active";
                    }} else {{
                        el.innerText = "غير مفعل 🔴";
                        el.className = "inactive";
                    }}
                }} catch(e){{}}
            }}

            async function updateCount() {{
                if(!USER_ID) return;
                try {{
                    const res = await fetch(`/api/account-count?user_id=${{USER_ID}}`);
                    const data = await res.json();
                    if(res.ok) document.getElementById("accountCount").innerText = data.count;
                }} catch(e){{}}
            }}

            if (USER_ID) {{
                checkSub();
                updateCount();
            }}

            function openModal(id) {{ document.getElementById(id).style.display = "flex"; }}
            function closeModal(id) {{ document.getElementById(id).style.display = "none"; }}

            function copyCrypto() {{
                const addr = document.getElementById("cryptoAddress").innerText;
                navigator.clipboard.writeText(addr);
                alert("تم نسخ العنوان بنجاح!");
            }}

            function redirectToBot() {{
                const botUsername = "{BOT_USERNAME}";
                const startParam = `pay_${{USER_ID}}`;
                window.location.href = `https://t.me/${{botUsername}}?start=${{startParam}}`;
            }}

            function showStatus(msg, isError = false) {{
                const box = document.getElementById("statusBox");
                box.style.display = "block";
                box.className = "status " + (isError ? "error" : "success");
                box.innerText = msg;
            }}

            async function payOxaPay() {{
                showStatus("جاري تجهيز بوابة OxaPay...");
                const res = await fetch("/api/create-oxapay-payment", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{user_id: USER_ID}})
                }});
                const data = await res.json();
                if(res.ok && data.pay_url) {{
                    window.location.href = data.pay_url;
                }} else {{
                    showStatus(data.detail || "فشل إنشاء بوابة الدفع", true);
                }}
            }}

            async function sendCode() {{
                const phone = document.getElementById("phone").value.trim();
                if(!phone) return alert("أدخل الرقم أولاً");

                showStatus("جاري إرسال الكود مع التشفير...");
                const res = await fetch("/api/send-code", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{user_id: USER_ID, phone_number: phone}})
                }});
                const data = await res.json();
                if(res.ok) {{
                    phoneHash = data.phone_code_hash;
                    document.getElementById("verifyBox").style.display = "block";
                    showStatus(data.message);
                }} else {{
                    showStatus(data.detail || "حدث خطأ", true);
                }}
            }}

            async function verifyCode() {{
                const phone = document.getElementById("phone").value.trim();
                const code = document.getElementById("otpCode").value.trim();

                showStatus("جاري اختبار الجلسة وحفظ الرقم...");
                const res = await fetch("/api/verify-code", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{user_id: USER_ID, phone_number: phone, phone_code_hash: phoneHash, code: code}})
                }});
                const data = await res.json();
                if(res.ok) {{
                    showStatus(data.message);
                    updateCount();
                }} else {{
                    showStatus(data.detail, true);
                }}
            }}

            async function startAdding() {{
                const source = document.getElementById("sourceGroup").value.trim();
                const target = document.getElementById("targetGroup").value.trim();

                if(!source || !target) return alert("يرجى وضع روابط المجموعات المصدر والهدف");

                showStatus("🚀 تم إطلاق الحملة! الحسابات تعمل الآن بالخلفية وتضيف الأعضاء لجروبك الحقيقي...");
                const res = await fetch("/api/start-adding", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{user_id: USER_ID, source_group: source, target_group: target}})
                }});
                const data = await res.json();
                if(res.ok) {{
                    showStatus(data.message);
                }} else {{
                    showStatus(data.detail, true);
                }}
            }}
        </script>
    </body>
    </html>
    """

# ==========================================
# 5. APIs إدارة الحسابات
# ==========================================

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
                "message": "مرحباً بعودتك! تم استعادة حسابك واشتراكك بنجاح 🟢"
            }

        user_id = 'user_' + uuid.uuid4().hex[:9]
        
        supabase.table("users1").insert({
            "user_id": user_id,
            "full_name": clean_name,
            "username_or_phone": clean_contact
        }).execute()

        supabase.table("users_subscriptions").insert({
            "user_id": user_id,
            "is_active": False
        }).execute()

        send_telegram_notification(f"🚨 <b>مشترك جديد ينضم للخدمة!</b>\n👤 الاسم: {clean_name}\n📞 التواصل: {clean_contact}\n🆔 المعرف: <code>{user_id}</code>")
        
        return {"status": "success", "user_id": user_id, "message": "تم إنشاء الحساب بنجاح!"}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/subscription-status")
async def subscription_status(user_id: str):
    res = supabase.table("users_subscriptions").select("*").eq("user_id", user_id).execute()
    if res.data and res.data[0].get("is_active"):
        end_date = res.data[0].get("subscription_end", "")[:10]
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
        response = requests.post("https://api.oxapay.com/merchants/request", json=payload).json()
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

@app.get("/api/account-count")
async def get_account_count(user_id: str):
    response = supabase.table("telegram_accounts").select("id", count="exact").eq("user_id", user_id).execute()
    return {"count": response.count if response.count is not None else len(response.data)}

@app.post("/api/send-code")
async def send_code(req: PhoneRequest):
    if not check_user_subscription(req.user_id):
        raise HTTPException(status_code=403, detail="عذراً، يجب تفعيل الاشتراك أولاً.")

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent_code = await client.send_code_request(req.phone_number)
        pending_sessions[req.phone_number] = client.session.save()
        await client.disconnect()
        return {"status": "success", "phone_code_hash": sent_code.phone_code_hash, "message": "تم إرسال كود التفعيل!"}
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/verify-code")
async def verify_code(req: VerifyRequest):
    if not check_user_subscription(req.user_id):
        raise HTTPException(status_code=403, detail="عذراً، يجب تفعيل الاشتراك أولاً.")

    session_str = pending_sessions.get(req.phone_number)
    if not session_str:
        raise HTTPException(status_code=400, detail="انتهت الجلسة، حاول مجدداً.")

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
        return {"status": "success", "message": "🟢 تم ربط الرقم بنجاح وإضافته للأسطول!"}
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=f"خطأ في التحقق: {str(e)}")

@app.post("/api/start-adding")
async def start_adding(req: AddMembersRequest):
    if not check_user_subscription(req.user_id):
        raise HTTPException(status_code=403, detail="عذراً، يجب تفعيل الاشتراك أولاً.")

    accounts = supabase.table("telegram_accounts").select("session_string, phone").eq("user_id", req.user_id).execute()
    if not accounts.data:
        raise HTTPException(status_code=400, detail="لا توجد حسابات مربوطة في أسطولك.")

    # تشغيل المحرك الحقيقي فوراً بالخلفية
    asyncio.create_task(run_heavy_duty_engine(accounts.data, req.source_group, req.target_group))
    return {"status": "success", "message": f"⚡ تم البدء بالفعل عبر ({len(accounts.data)}) حساب! الأعضاء يضافون الآن لجروبك."}

# ==========================================
# 6. المحرك الخارق المصحح كلياً (Real Working Engine)
# ==========================================

MAX_ADDS_PER_ACCOUNT = 5
MIN_DELAY = 12
MAX_DELAY = 25

async def process_account_queue(acc_data, user_queue, target_clean_name, api_id, api_hash):
    phone = acc_data.get("phone", "Unknown")
    session_str = acc_data.get("session_string")
    
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    adds_count = 0
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print(f"❌ [الحساب {phone}] غير مفعل أو الجلسة ملغاة.")
            return

        # جلب كيان الجروب الهدف بشكل صحيح داخل الجلسة
        try:
            target_entity = await client.get_entity(target_clean_name)
            await client(JoinChannelRequest(target_entity))
        except Exception as e:
            print(f"⚠️ [الحساب {phone}] خطأ الوصول للهدف: {e}")
            try:
                target_entity = await client.get_entity(target_clean_name)
            except Exception:
                return

        while user_queue and adds_count < MAX_ADDS_PER_ACCOUNT:
            user_info = user_queue.pop(0)  # يتكون من (user_id, access_hash, username)
            u_id, u_hash, u_name = user_info
            
            try:
                # طريقة الإضافة المباشرة الفعالة:
                if u_name:
                    user_to_add = u_name
                else:
                    # استخدام InputPeerUser المباشر بالـ ID والهاش المجلوب من الحساب الرئيسي
                    user_to_add = InputPeerUser(user_id=u_id, access_hash=u_hash)

                await client(InviteToChannelRequest(target_entity, [user_to_add]))
                adds_count += 1
                print(f"✅ [الحساب {phone}] تم إضافة العضو ({u_name or u_id}) بنجاح! ({adds_count}/{MAX_ADDS_PER_ACCOUNT})")
                
                await asyncio.sleep(random.randint(MIN_DELAY, MAX_DELAY))

            except UserPrivacyRestrictedError:
                print(f"⚠️ [الحساب {phone}] العضو ({u_name or u_id}) مغلق الخصوصية.")
            except (PeerFloodError, FloodWaitError) as e:
                print(f"🛑 [الحساب {phone}] الحساب محظور حالياً من الإضافة (PeerFlood): {e}")
                user_queue.insert(0, user_info)
                break
            except Exception as e:
                print(f"⚠️ [الحساب {phone}] تعذر إضافة العضو ({u_name or u_id}): {e}")

    except Exception as e:
        print(f"💥 [الحساب {phone}] خطأ بالجلسة: {e}")
    finally:
        await client.disconnect()


async def run_heavy_duty_engine(accounts_data, source_group, target_group):
    if not accounts_data:
        print("❌ لا توجد حسابات مضافة.")
        return

    src_clean = source_group.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").strip()
    trg_clean = target_group.replace("https://t.me/", "").replace("http://t.me/", "").replace("@", "").strip()

    scraped_users = []
    master_acc = accounts_data[0]
    master_client = TelegramClient(StringSession(master_acc["session_string"]), API_ID, API_HASH)

    try:
        await master_client.connect()
        if not await master_client.is_user_authorized():
            print("❌ الحساب الرئيسي غير موثق!")
            return

        src_entity = await master_client.get_entity(src_clean)
        try:
            await master_client(JoinChannelRequest(src_entity))
        except Exception:
            pass

        print("🔍 جاري سحب الأعضاء النشطين بالكامل...")
        participants = await master_client.get_participants(src_entity, limit=1000)
        
        for u in participants:
            if not u.bot and not u.deleted:
                scraped_users.append((u.id, u.access_hash, u.username))

    except Exception as e:
        print(f"💥 خطأ السحب الرئيسي: {e}")
        return
    finally:
        await master_client.disconnect()

    if not scraped_users:
        print("❌ لم يتم العثور على أي أعضاء في المجموعة المصدر!")
        return

    print(f"🔥 تم سحب {len(scraped_users)} عضو! بدء توزيع المهام على الأسطول...")

    user_queue = list(scraped_users)
    tasks = []
    for acc in accounts_data:
        if user_queue:
            tasks.append(process_account_queue(acc, user_queue, trg_clean, API_ID, API_HASH))

    await asyncio.gather(*tasks)
    print("🎉 انتهت الحملة!")
