import os
import asyncio
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import InviteToChannelRequest
from supabase import create_client, Client

# ==========================================
# 1. الإعدادات وربط Supabase و Telegram API
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://juuleypxvvcfgjdikpwu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_Kh6iN4Aq6X6gLNcElNzgRg_CjlLMaZL")

API_ID = int(os.getenv("TELEGRAM_API_ID", "21349867"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "7ced3ee4c80117bd5138410811b91f9f")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI(title="Telegram Engine Direct")

# تخزين مؤقت للعمليات الجارية
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
# 3. الواجهة التفاعلية السلسة (مباشرة بدون UUID)
# ==========================================
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>منصة إضافة أعضاء التلغرام</title>
        <style>
            body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; display: flex; justify-content: center; }
            .card { background: #1e293b; padding: 25px; border-radius: 12px; max-width: 480px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }
            h2 { color: #38bdf8; text-align: center; margin-bottom: 20px; font-size: 22px; }
            h3 { font-size: 16px; color: #e2e8f0; margin-top: 0; }
            label { display: block; margin-top: 12px; font-size: 13px; color: #94a3b8; }
            input { width: 100%; padding: 12px; margin-top: 6px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; box-sizing: border-box; font-size: 15px; }
            input:focus { border-color: #38bdf8; outline: none; }
            button { width: 100%; padding: 12px; margin-top: 16px; border: none; border-radius: 8px; background: #0284c7; color: white; font-size: 15px; font-weight: bold; cursor: pointer; transition: 0.2s; }
            button:hover { background: #0369a1; }
            .btn-green { background: #16a34a; }
            .btn-green:hover { background: #15803d; }
            .status { margin-top: 15px; padding: 12px; border-radius: 8px; font-size: 14px; display: none; line-height: 1.5; }
            .success { background: #065f46; color: #34d399; }
            .error { background: #881337; color: #fecdd3; }
            hr { border: 0; height: 1px; background: #334155; margin: 25px 0; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>⚡ أداة إضافة الأعضاء التلقائية</h2>
            
            <h3>1️⃣ تسجيل الدخول وربط الرقم</h3>
            <label>رقم الهاتف (مع المفتاح الدولي):</label>
            <input type="text" id="phone" placeholder="+966500000000">
            <button onclick="sendCode()">أرسل كود التحقق</button>
            
            <div id="verifyBox" style="display:none;">
                <label>كود التحقق (من تطبيق التلغرام):</label>
                <input type="text" id="otpCode" placeholder="12345">
                <button onclick="verifyCode()" class="btn-green">تأكيد وتسجيل الدخول</button>
            </div>
            
            <hr>
            
            <h3>2️⃣ تشغيل الإضافة</h3>
            <label>رابط/يوزر الجروب المصدر (السحب منه):</label>
            <input type="text" id="sourceGroup" placeholder="https://t.me/source_group">
            
            <label>رابط/يوزر الجروب الهدف (الإضافة إليه):</label>
            <input type="text" id="targetGroup" placeholder="https://t.me/target_group">
            
            <button onclick="startAdding()" class="btn-green">بدء عمليات الإضافة السحابية</button>
            
            <div id="statusBox" class="status"></div>
        </div>

        <script>
            // إنشاء وتخزين UUID تلقائي للمستخدم داخل المتصفح دون تدخله
            let USER_ID = localStorage.getItem("user_device_id");
            if (!USER_ID) {
                USER_ID = 'user_' + Math.random().toString(36).substr(2, 9);
                localStorage.setItem("user_device_id", USER_ID);
            }

            let phoneHash = "";

            function showStatus(msg, isError = false) {
                const box = document.getElementById("statusBox");
                box.style.display = "block";
                box.className = "status " + (isError ? "error" : "success");
                box.innerText = msg;
            }

            async function sendCode() {
                const phone = document.getElementById("phone").value.trim();
                if(!phone) return alert("يرجى إدخال رقم الهاتف أولاً");

                showStatus("جاري الاتصال وإرسال الكود إلى تلغرام...");
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
                    showStatus(data.detail || "حدث خطأ أثناء إرسال الكود", true);
                }
            }

            async function verifyCode() {
                const phone = document.getElementById("phone").value.trim();
                const code = document.getElementById("otpCode").value.trim();

                if(!code) return alert("أدخل كود التحقق الواصل لحسابك");

                showStatus("جاري التأكد من الكود وتفعيل الحساب...");
                const res = await fetch("/api/verify-code", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({user_id: USER_ID, phone_number: phone, phone_code_hash: phoneHash, code: code})
                });
                const data = await res.json();
                if(res.ok) {
                    showStatus(data.message);
                } else {
                    showStatus(data.detail || "فشل التحقق من الكود", true);
                }
            }

            async function startAdding() {
                const source = document.getElementById("sourceGroup").value.trim();
                const target = document.getElementById("targetGroup").value.trim();

                if(!source || !target) return alert("يرجى إدخال روابط الجروبات المطلوبة");

                showStatus("🚀 تم إطلاق الحملة بنجاح! السيرفر يعمل الآن في الخلفية لسحب وإضافة الأعضاء...");

                const res = await fetch("/api/start-adding", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({user_id: USER_ID, source_group: source, target_group: target})
                });
                const data = await res.json();
                if(res.ok) {
                    showStatus(data.message);
                } else {
                    showStatus(data.detail || "يرجى تسجيل الدخول برقمك أولاً قبل بدء الإضافة", true);
                }
            }
        </script>
    </body>
    </html>
    """

# ==========================================
# 4. الوظائف الخلفية
# ==========================================

@app.post("/api/send-code")
async def send_code(req: PhoneRequest):
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent_code = await client.send_code_request(req.phone_number)
        pending_sessions[req.phone_number] = client.session.save()
        await client.disconnect()
        return {"status": "success", "phone_code_hash": sent_code.phone_code_hash, "message": "تم إرسال كود التحقق بنجاح إلى حسابك في تلغرام!"}
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/verify-code")
async def verify_code(req: VerifyRequest):
    session_str = pending_sessions.get(req.phone_number)
    if not session_str:
        raise HTTPException(status_code=400, detail="انتهت الجلسة، يرجى طلب كود جديد.")

    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    try:
        await client.sign_in(phone=req.phone_number, code=req.code, phone_code_hash=req.phone_code_hash)
        final_session = client.session.save()
        await client.disconnect()

        # حفظ الجلسة باسم المستخدم الآلي تلقائياً
        supabase.table("telegram_accounts").insert({
            "user_id": req.user_id,
            "phone": req.phone_number,
            "session_string": final_session
        }).execute()

        del pending_sessions[req.phone_number]
        return {"status": "success", "message": "🟢 تم تسجيل الدخول وربط الرقم بنجاح! يمكنك الآن بدء الإضافة."}
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=f"خطأ في التحقق: {str(e)}")

@app.post("/api/start-adding")
async def start_adding(req: AddMembersRequest):
    # جلب الحسابات المربوطة
    accounts = supabase.table("telegram_accounts").select("session_string").eq("user_id", req.user_id).execute()
    if not accounts.data:
        raise HTTPException(status_code=400, detail="لم تقم بربط أي رقم بعد. يرجى إدخال رقمك وتأكيده أولاً.")

    # تشغيل عملية السحب والإضافة الفعلية في الخلفية
    asyncio.create_task(run_real_adding_process(accounts.data, req.source_group, req.target_group))
    return {"status": "success", "message": "⚡ جاري سحب وإضافة الأعضاء تلقائياً في الخلفية..."}

# ==========================================
# 5. محرك السحب والإضافة الفعلي
# ==========================================
async def run_real_adding_process(accounts, source, target):
    for acc in accounts:
        client = TelegramClient(StringSession(acc["session_string"]), API_ID, API_HASH)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                continue

            src_entity = await client.get_entity(source)
            trg_entity = await client.get_entity(target)

            # سحب الأعضاء
            participants = await client.get_participants(src_entity, limit=100)

            added_count = 0
            for user in participants:
                if user.bot or user.deleted:
                    continue

                try:
                    # إضافة العضو للجروب Target
                    await client(InviteToChannelRequest(trg_entity, [user]))
                    added_count += 1
                    
                    # فاصل زمني 15 ثانية لحماية الحساب من الحظر
                    await asyncio.sleep(5)

                    if added_count >= 50:
                        break

                except Exception as add_error:
                    if "FLOOD" in str(add_error).upper():
                        break
                    continue

        except Exception as e:
            print(f"Error: {e}")
        finally:
            await client.disconnect()
