import os
import asyncio
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template
from supabase import create_client, Client
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import InviteToChannelRequest, GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsRecent

app = Flask(__name__)

# إعدادات Supabase
SUPABASE_URL = "https://juuleypxvvcfgjdikpwu.supabase.co"
SUPABASE_KEY = "sb_publishable_Kh6iN4Aq6X6gLNcElNzgRg_CjlLMaZL"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# بيانات التطبيق من my.telegram.org
API_ID = 1234567  # ضع API_ID الخاص بك هنا
API_HASH = "YOUR_API_HASH_HERE"  # ضع API_HASH الخاص بك هنا

# مخزن موقت لطلبات تسجيل دخول الأرقام
pending_logins = {}

# 1️⃣ فحص حالة الاشتراك الشهري
@app.route('/api/check-subscription', methods=['POST'])
def check_subscription():
    user_id = request.form.get('user_id')
    res = supabase.table('users_profile').select('*').eq('id', user_id).execute()
    
    if not res.data:
        # إنشاء ملف للمستخدم
        supabase.table('users_profile').insert({'id': user_id, 'is_subscribed': False}).execute()
        return jsonify({'is_active': False, 'message': 'يرجى الاشتراك في الخدمة بـ 80$ شهرياً.'})
    
    user = res.data[0]
    expires_at = user.get('subscription_expires_at')
    
    if user.get('is_subscribed') and expires_at:
        exp_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) < exp_date:
            return jsonify({'is_active': True, 'expires_at': expires_at})
            
    return jsonify({'is_active': False, 'message': 'اشتراكك غير مفعّل أو انتهت صلاحيته. سعر الاشتراك 80$ شهرياً.'})

# 2️⃣ إرسال كود التحقق لرقم التلغرام
@app.route('/api/send-code', methods=['POST'])
def send_code():
    user_id = request.form.get('user_id')
    phone = request.form.get('phone').strip()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        send_res = loop.run_until_complete(client.send_code_request(phone))
        
        # حفظ الجلسة المؤقتة لاستكمال التأكيد
        pending_logins[user_id] = {
            'phone': phone,
            'phone_code_hash': send_res.phone_code_hash,
            'session_str': client.session.save()
        }
        loop.run_until_complete(client.disconnect())
        return jsonify({'status': 'success', 'message': 'تم إرسال كود التحقق لـ حسابك في التلغرام!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

# 3️⃣ تأكيد الكود وربط الحساب بالنظام
@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    user_id = request.form.get('user_id')
    code = request.form.get('code').strip()
    password = request.form.get('password', '').strip()

    login_data = pending_logins.get(user_id)
    if not login_data:
        return jsonify({'status': 'error', 'message': 'انتهت جلسة أرسال الكود، اطلب كوداً جديداً.'}), 400

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
                    return jsonify({'status': '2fa_required', 'message': 'الحساب محمي بكلمة مرور (2FA). يرجى إدخالها.'})
                loop.run_until_complete(client.sign_in(password=password))
            else:
                raise e

        # حفظ الجلسة الدائمة في Supabase
        final_session = client.session.save()
        supabase.table('user_telegram_accounts').insert({
            'user_id': user_id,
            'phone_number': login_data['phone'],
            'session_string': final_session
        }).execute()

        loop.run_until_complete(client.disconnect())
        del pending_logins[user_id]
        
        return jsonify({'status': 'success', 'message': 'تم ربط رقمك بالنظام بنجاح!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

# 4️⃣ بدء عملية السحب والإضافة باستخدام الحساب المربوط
@app.route('/api/start-addition', methods=['POST'])
def start_addition():
    user_id = request.form.get('user_id')
    src = request.form.get('src')
    trg = request.form.get('trg')
    count = int(request.form.get('count', 10))

    # فحص الاشتراك أولاً
    sub_res = supabase.table('users_profile').select('*').eq('id', user_id).execute()
    if not sub_res.data or not sub_res.data[0].get('is_subscribed'):
        return jsonify({'status': 'error', 'message': 'عذراً! يجب تفعيل الاشتراك الشهري (80$) للبدء.'}), 403

    # جلب حسابات المستخدم المربوطة
    acc_res = supabase.table('user_telegram_accounts').select('*').eq('user_id', user_id).execute()
    if not acc_res.data:
        return jsonify({'status': 'error', 'message': 'لم تقم بربط أي رقم تلغرام بعد!'}), 400

    session_string = acc_res.data[0]['session_string']

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        added = loop.run_until_complete(execute_transfer(session_string, src, trg, count))
        return jsonify({'status': 'success', 'message': f'تمت الإضافة بنجاح! تم إضافة {added} عضو.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'خطأ أثناء التنفيذ: {str(e)}'}), 500

async def execute_transfer(session_str, src, trg, count):
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    
    src_entity = await client.get_entity(src)
    trg_entity = await client.get_entity(trg)

    participants = await client(GetParticipantsRequest(
        channel=src_entity, filter=ChannelParticipantsRecent(),
        offset=0, limit=count, hash=0
    ))

    success = 0
    for user in participants.users:
        if user.bot: continue
        try:
            await client(InviteToChannelRequest(trg_entity, [user]))
            success += 1
            await asyncio.sleep(2)
        except: continue

    await client.disconnect()
    return success

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
