import os
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from supabase import create_client, Client

# ==========================================
# 1. إعدادات المفاتيح وربط Supabase
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://juuleypxvvcfgjdikpwu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "ضع_مفتاح_SUPABASE_SERVICE_ROLE_هنا")

# بيانات Telegram API (استبدلها ببياناتك من my.telegram.org)
API_ID = int(os.getenv("TELEGRAM_API_ID", "1234567"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "your_api_hash_here")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI(title="Telegram Ultra Adder")

# ذاكرة مؤقتة لعملية التحقق
pending_sessions = {}

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

# ==========================================
# 3. واجهة الموقع الإلكتروني (HTML/JS)
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Telegram Ultra Adder - لوحة التحكم</title>
        <style>
            body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; display: flex; justify-content: center; }
            .card { background: #1e293b; padding: 25px; border-radius: 12px; max-width: 500px; width: 100%; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
            h2 { color: #38bdf8; text-align: center; margin-bottom: 20px; }
            label { display: block; margin-top: 15px; font-size: 14px; color: #94a3b8; }
            input { width: 100%; padding: 10px; margin-top: 5px; border-radius: 6px; border: 1px solid #334155; background: #0f172a; color: white; box-sizing: border-box; }
            button { width: 100%; padding: 12px; margin-top: 18px; border: none; border-radius: 6px; background: #0284c7; color: white; font-size: 16px; font-weight: bold; cursor: pointer; }
            button:hover { background: #0369a1; }
            .status { margin-top: 15px; padding: 10px; border-radius: 6px; font-size: 14px; display: none; }
            .success { background: #065f46; color: #34d399; }
            .error { background: #881337; color: #fecdd3; }
            hr { border: 0; height: 1px; background: #334155; margin: 25px 0; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>لوحة إضافة الأعضاء التلقائية</h2>
            
            <!-- قسم ربط أرقام التلغرام -->
            <h3>1️⃣ ربط رقم تلغرام جديد</h3>
            <label>معرف المستخدم (User UUID):</label>
            <input type="text" id="userId" placeholder="أدخل UUID المخصص لك">
            
            <label>رقم الهاتف (مع المفتاح الدولي):</label>
            <input type="text" id="phone" placeholder="+966500000000">
            <button onclick="sendCode()">أرسل كود التحقق</button>
            
            <div id="verifyBox" style="display:none;">
                <label>كود التحقق الوارد في تلغرام:</label>
                <input type="text" id="otpCode" placeholder="12345">
                <button onclick="verifyCode()">تأكيد وربط الحساب</button>
            </div>
            
            <hr>
            
            <!-- قسم بدء عملية الإضافة -->
            <h3>2️⃣ تشغيل الإضافة</h3>
            <label>رابط/يوزر الجروب المصدر (السحب منه):</label>
            <input type="text" id="sourceGroup" placeholder="https://t.me/source_group">
            
            <label>رابط/يوزر الجروب الهدف (الإضافة إليه):</label>
            <input type="text" id="targetGroup" placeholder="https://t.me/target_group">
            
            <button onclick="startAdding()" style="background: #16a34a;">بدء عمليات الإضافة السحابية</button>
            
            <div id="statusBox" class="status"></div>
        </div>

        <script>
            let phoneHash = "";

            function showStatus(msg, isError = false) {
                const box = document.getElementById("statusBox");
                box.style.display = "block";
                box.className = "status " + (isError ? "error" : "success");
                box.innerText = msg;
            }

            async function sendCode() {
                const userId = document.getElementById("userId").value;
                const phone = document.getElementById("phone").value;
                if(!userId || !phone) return alert("يرجى ملء جميع الحقول");

                const res = await fetch("/api/send-code", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({user_id: userId, phone_number: phone})
                });
                const data = await res.json();
                if(res.ok) {
                    phoneHash = data.phone_code_hash;
                    document.getElementById("verifyBox").style.display = "block";
                    showStatus(data.message);
                } else {
                    showStatus(data.detail || "حدث خطأ أثناء الإرسال", true);
                }
            }

            async function verifyCode() {
                const userId = document.getElementById("userId").value;
                const phone = document.getElementById("phone").value;
                const code = document.getElementById("otpCode").value;

                const res = await fetch("/api/verify-code", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({user_id: userId, phone_number: phone, phone_code_hash: phoneHash, code: code})
                });
                const data = await res.json();
                if(res.ok) {
                    showStatus(data.message);
                } else {
                    showStatus(data.detail || "فشل التحقق من الكود", true);
                }
            }

            async function startAdding() {
                const userId = document.getElementById("userId").value;
                const source = document.getElementById("sourceGroup").value;
                const target = document.getElementById("targetGroup").value;

                showStatus("جاري بدء العملية في الخلفية... الرجاء الانتظار");

                const res = await fetch("/api/start-adding", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({user_id: userId, source_group: source, target_group: target})
                });
                const data = await res.json();
                if(res.ok) {
                    showStatus(data.message);
                } else {
                    showStatus(data.detail || "فشل بدء العملية", true);
                }
            }
        </script>
    </body>
    </html>
    """

# ==========================================
# 4. وظائف السيرفر (API Endpoints)
# ==========================================

# إرسال كود OTP
@app.post("/api/send-code")
async def send_code(req: PhoneRequest):
    # فحص الاشتراك من جدول users_profile
    profile = supabase.table("users_profile").select("is_subscribed").eq("id", req.user_id).execute()
    if not profile.data or not profile.data[0].get("is_subscribed"):
        raise HTTPException(status_code=403, detail="الحساب غير مفعّل، يرجى تفعيل الاشتراك الشهري أولاً.")

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent_code = await client.send_code_request(req.phone_number)
        pending_sessions[req.phone_number] = client.session.save()
        await client.disconnect()
        return {"status": "success", "phone_code_hash": sent_code.phone_code_hash, "message": "تم إرسال الكود بنجاح إلى تلغرام"}
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=str(e))

# تأكيد الكود وحفظ الجلسة في telegram_accounts
@app.post("/api/verify-code")
async def verify_code(req: VerifyRequest):
    session_str = pending_sessions.get(req.phone_number)
    if not session_str:
        raise HTTPException(status_code=400, detail="انتهت الجلسة، يرجى إعادة طلب الكود.")

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    try:
        await client.sign_in(phone=req.phone_number, code=req.code, phone_code_hash=req.phone_code_hash)
        final_session = client.session.save()
        await client.disconnect()

        # حفظ الرقم والجلسة في جدول telegram_accounts
        supabase.table("telegram_accounts").insert({
            "user_id": req.user_id,
            "phone_number": req.phone_number,
            "session_string": final_session
        }).execute()

        del pending_sessions[req.phone_number]
        return {"status": "success", "message": "تم تمكين الحساب وربطه بنجاح!"}
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=f"خطأ في التحقق: {str(e)}")

# بدء العمليات والإضافة الأوتوماتيكية
@app.post("/api/start-adding")
async def start_adding(req: AddMembersRequest):
    # جلب الحسابات الخاصة بالعميل من telegram_accounts
    accounts = supabase.table("telegram_accounts").select("session_string").eq("user_id", req.user_id).execute()
    if not accounts.data:
        raise HTTPException(status_code=400, detail="لا توجد حسابات تلغرام مربوطة لهذا المستخدم.")

    # تشغيل المهمة أوتوماتيكياً في الخلفية لعدم تجميد الموقع
    asyncio.create_task(run_adding_process(accounts.data, req.source_group, req.target_group))
    return {"status": "success", "message": "بدأت عملية الإضافة في الخلفية بنجاح!"}

# محرك الإضافة السحابي
async def run_adding_process(accounts, source, target):
    for acc in accounts:
        try:
            client = TelegramClient(StringSession(acc["session_string"]), API_ID, API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                # جلب الأعضاء وحفظهم ثم إضافتهم تدريجياً (يمكن تخصيص المنطق هنا)
                pass 
            await client.disconnect()
        except Exception:
            continue
            
app = app
