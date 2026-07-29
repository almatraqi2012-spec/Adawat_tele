import os
import asyncio
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string
from supabase import create_client, Client
from telethon import TelegramClient
from telethon.sessions import StringSession

app = Flask(__name__)

# إعدادات Supabase و Telegram API من متغيرات البيئة لضمان الأمان
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://juuleypxvvcfgjdikpwu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_Kh6iN4Aq6X6gLNcElNzgRg_CjlLMaZL")
API_ID = int(os.getenv("TELEGRAM_API_ID", "21349867")
API_HASH = os.getenv("TELEGRAM_API_HASH", "7ced3ee4c80117bd5138410811b91f9f")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
pending_logins = {}

# ==========================================
# 1. الواجهة الأمامية الشاملة (HTML/CSS/JS)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>منصة التلغرام الذكية | Telegram Cloud Platform</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <style>
        body { background-color: #0b0f19; color: #e2e8f0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .card-custom { background: #151c2c; border: 1px solid #1e293b; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        .btn-primary-custom { background: #0284c7; border: none; font-weight: bold; }
        .btn-primary-custom:hover { background: #0369a1; }
        .badge-active { background: #059669; }
        .badge-inactive { background: #dc2626; }
        .form-control { background-color: #0f172a; border-color: #334155; color: #fff; }
        .form-control:focus { background-color: #0f172a; color: #fff; border-color: #0284c7; box-shadow: none; }
    </style>
</head>
<body class="py-5">
    <div class="container">
        <!-- شريط الترويسة -->
        <div class="d-flex justify-content-between align-items-center mb-4 pb-3 border-bottom border-secondary">
            <h3 class="fw-bold text-info">⚡ لوحة التحكم بالخدمة</h3>
            <span id="subStatus" class="badge p-2 badge-inactive">جاري فحص الاشتراك...</span>
        </div>

        <div class="row g-4">
            <!-- القسم الأول: ربط أرقام التلغرام -->
            <div class="col-md-6">
                <div class="card-custom p-4 h-100">
                    <h5 class="text-white mb-3">📱 1. ربط وإدارة الحسابات</h5>
                    <form id="phoneForm">
                        <div class="mb-3">
                            <label class="form-label text-muted">رقم الهاتف (مع المفتاح الدولي):</label>
                            <input type="text" id="phone" class="form-control" placeholder="+966500000000" required>
                        </div>
                        <button type="button" onclick="sendCode()" class="btn btn-primary-custom w-100 py-2">أرسل كود التحقق</button>
                    </form>

                    <!-- مربع إدخال الـ OTP و 2FA -->
                    <div id="otpSection" class="mt-4 pt-3 border-top border-secondary" style="display:none;">
                        <div class="mb-3">
                            <label class="form-label text-muted">كود التحقق (من التلغرام):</label>
                            <input type="text" id="otpCode" class="form-control" placeholder="12345">
                        </div>
                        <div class="mb-3">
                            <label class="form-label text-muted">كلمة مرور التحقق بخطوتين (إن وجدت):</label>
                            <input type="password" id="twoFaPassword" class="form-control" placeholder="أدخل كلمة المرور إذا كانت مفعّلة">
                        </div>
                        <button type="button" onclick="verifyCode()" class="btn btn-success w-100 py-2 fw-bold">تأكيد وربط الرقم</button>
                    </div>
                </div>
            </div>

            <!-- القسم الثاني: إنشاء حملة سحب وإضافة -->
            <div class="col-md-6">
                <div class="card-custom p-4 h-100">
                    <h5 class="text-white mb-3">🚀 2. إطلاق حملة إضافة سحابية</h5>
                    <form id="campaignForm">
                        <div class="mb-3">
                            <label class="form-label text-muted">الجروب المصدر (السحب منه):</label>
                            <input type="text" id="srcGroup" class="form-control" placeholder="https://t.me/source_group" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label text-muted">الجروب الهدف (الإضافة إليها):</label>
                            <input type="text" id="trgGroup" class="form-control" placeholder="https://t.me/target_group" required>
                        </div>
                        <div class="mb-3">
                            <label class="form-label text-muted">عدد الأعضاء المطلوب إضافتهم:</label>
                            <input type="number" id="memberCount" class="form-control" value="50" min="5" max="500">
                        </div>
                        <button type="button" onclick="startCampaign()" class="btn btn-warning w-100 py-2 fw-bold text-dark">بدء عملية الإضافة</button>
                    </form>
                </div>
            </div>
        </div>

        <!-- صندوق الإشعارات والرسائل -->
        <div class="row mt-4">
            <div class="col-12">
                <div id="alertBox" class="alert d-none" role="alert"></div>
            </div>
        </div>
    </div>

    <script>
        // الـ Auth UUID يُحفظ تلقائياً عند تسجيل دخول المستخدم للموقع
        const USER_ID = localStorage.getItem("user_id") || "ضع_UUID_العميل_التلقائي";

        function showAlert(msg, isSuccess = true) {
            const box = document.getElementById("alertBox");
            box.className = `alert ${isSuccess ? 'alert-success' : 'alert-danger'} d-block`;
            box.innerText = msg;
        }

        async function sendCode() {
            const phone = document.getElementById("phone").value;
            const res = await fetch("/api/send-code", {
                method: "POST",
                headers: {"Content-Type": "application/x-www-form-urlencoded"},
                body: new URLSearchParams({user_id: USER_ID, phone: phone})
            });
            const data = await res.json();
            if(res.ok) {
                document.getElementById("otpSection").style.display = "block";
                showAlert(data.message, true);
            } else {
                showAlert(data.message, false);
            }
        }

        async function verifyCode() {
            const code = document.getElementById("otpCode").value;
            const password = document.getElementById("twoFaPassword").value;
            const res = await fetch("/api/verify-code", {
                method: "POST",
                headers: {"Content-Type": "application/x-www-form-urlencoded"},
                body: new URLSearchParams({user_id: USER_ID, code: code, password: password})
            });
            const data = await res.json();
            showAlert(data.message, res.ok);
        }

        async function startCampaign() {
            const src = document.getElementById("srcGroup").value;
            const trg = document.getElementById("trgGroup").value;
            const count = document.getElementById("memberCount").value;

            showAlert("جاري معالجة الطلب وبدء السحب والتنفيذ في الخلفية...", true);

            const res = await fetch("/api/start-addition", {
                method: "POST",
                headers: {"Content-Type": "application/x-www-form-urlencoded"},
                body: new URLSearchParams({user_id: USER_ID, src: src, trg: trg, count: count})
            });
            const data = await res.json();
            showAlert(data.message, res.ok);
        }
    </script>
</body>
</html>
"""

# ==========================================
# 2. المسارات والـ Backend APIs
# ==========================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/send-code', methods=['POST'])
def send_code():
    user_id = request.form.get('user_id')
    phone = request.form.get('phone', '').strip()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        send_res = loop.run_until_complete(client.send_code_request(phone))
        
        pending_logins[user_id] = {
            'phone': phone,
            'phone_code_hash': send_res.phone_code_hash,
            'session_str': client.session.save()
        }
        loop.run_until_complete(client.disconnect())
        return jsonify({'status': 'success', 'message': 'تم إرسال كود التحقق بنجاح إلى تلغرام!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'فشل الإرسال: {str(e)}'}), 400

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    user_id = request.form.get('user_id')
    code = request.form.get('code', '').strip()
    password = request.form.get('password', '').strip()

    login_data = pending_logins.get(user_id)
    if not login_data:
        return jsonify({'status': 'error', 'message': 'جلسة التحقق انتهت، يرجى طلب كود جديد.'}), 400

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        client = TelegramClient(StringSession(login_data['session_str']), API_ID, API_HASH)
        loop.run_until_complete(client.connect())

        try:
            loop.run_until_complete(client.sign_in(phone=login_data['phone'], code=code, phone_code_hash=login_data['phone_code_hash']))
        except Exception as e:
            if "Two-steps verification" in str(e) or "password" in str(e).lower():
                if not password:
                    return jsonify({'status': '2fa_required', 'message': 'الحساب محمي بكلمة مرور (2FA). يرجى أدخالها في الخانة المخصصة.'}), 400
                loop.run_until_complete(client.sign_in(password=password))
            else:
                raise e

        # حفظ الجلسة في جدول telegram_accounts
        final_session = client.session.save()
        supabase.table('telegram_accounts').insert({
            'user_id': user_id,
            'phone_number': login_data['phone'],
            'session_string': final_session
        }).execute()

        loop.run_until_complete(client.disconnect())
        del pending_logins[user_id]
        return jsonify({'status': 'success', 'message': 'تم ربط الحساب بالنظام بنجاح وتجهيزه للإضافة!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'خطأ أثناء التفعيل: {str(e)}'}), 400

# للتشغيل على Vercel
app = app

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
