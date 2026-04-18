import os
import threading
import asyncio
from flask import Flask, render_template_string, request, jsonify
from telethon import TelegramClient, events, errors

# --- BİLGİLERİN ---
API_ID = 27861882
API_HASH = 'd1c630d699c775e846bf64aadd18aefd'

app = Flask(__name__)

# Global Değişkenler
client = None
rules = {} 
logs = []
phone_number = None

def add_log(msg):
    logs.append(msg)
    print(f"[LOG]: {msg}")

# --- HTML ARAYÜZÜ ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram 2FA Bot Panel</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #f0f2f5; padding: 20px; font-family: sans-serif; }
        .card { border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); border: none; margin-bottom: 20px; }
        .log-box { background: #222; color: #0f0; height: 200px; overflow-y: auto; padding: 15px; font-family: monospace; border-radius: 10px; font-size: 12px; }
    </style>
</head>
<body>
<div class="container" style="max-width: 700px;">
    <div class="card p-4 text-center">
        <h2 style="color: #0088cc;">Telegram Bot Paneli (2FA Destekli)</h2>
    </div>

    <div class="card p-4">
        <h5>1. Adım: Giriş Yap</h5>
        <div id="step1">
            <div class="input-group mb-3">
                <input type="text" id="phone" class="form-control" placeholder="+905xxxxxxxxx">
                <button onclick="sendCode()" class="btn btn-primary">Kod Gönder</button>
            </div>
        </div>
        <div id="step2" style="display:none;">
            <div class="input-group mb-3">
                <input type="text" id="otp" class="form-control" placeholder="Onay Kodu">
                <button onclick="verifyCode()" class="btn btn-success">Kodu Onayla</button>
            </div>
        </div>
        <div id="step3" style="display:none;">
            <div class="alert alert-warning">Hesabınızda 2 Adımlı Doğrulama var. Lütfen şifrenizi girin:</div>
            <div class="input-group mb-3">
                <input type="password" id="password" class="form-control" placeholder="2FA Şifreniz">
                <button onclick="verifyPassword()" class="btn btn-danger">Şifreyle Giriş Yap</button>
            </div>
        </div>
    </div>

    <div class="card p-4">
        <h5>2. Adım: Kurallar</h5>
        <div class="row g-2">
            <div class="col-5"><input type="text" id="trigger" class="form-control" placeholder="Mesaj buysa..."></div>
            <div class="col-5"><input type="text" id="reply" class="form-control" placeholder="Cevap..."></div>
            <div class="col-2"><button onclick="addRule()" class="btn btn-dark w-100">Ekle</button></div>
        </div>
        <div id="rule-list" class="mt-3"></div>
    </div>

    <div class="card p-4">
        <h5>Loglar</h5>
        <div id="logs" class="log-box"></div>
    </div>
</div>

<script>
    let tempOTP = "";

    function sendCode() {
        const p = document.getElementById('phone').value;
        fetch('/send_code', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({phone:p}) })
        .then(res => res.json()).then(data => {
            alert(data.msg);
            if(data.status==='ok') document.getElementById('step2').style.display='block';
        });
    }

    function verifyCode() {
        tempOTP = document.getElementById('otp').value;
        fetch('/verify', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({otp:tempOTP}) })
        .then(res => res.json()).then(data => {
            if(data.status === 'password_required') {
                document.getElementById('step3').style.display='block';
            } else {
                alert(data.msg);
            }
        });
    }

    function verifyPassword() {
        const pass = document.getElementById('password').value;
        fetch('/verify_password', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:pass}) })
        .then(res => res.json()).then(data => alert(data.msg));
    }

    function addRule() {
        const t = document.getElementById('trigger').value;
        const r = document.getElementById('reply').value;
        fetch('/add_rule', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({trigger:t, reply:r}) })
        .then(() => {
            document.getElementById('rule-list').innerHTML += `<div class='badge bg-info m-1'>${t} -> ${r}</div>`;
        });
    }

    setInterval(() => {
        fetch('/get_logs').then(res => res.json()).then(data => {
            const box = document.getElementById('logs');
            box.innerHTML = data.join('<br>');
            box.scrollTop = box.scrollHeight;
        });
    }, 2000);
</script>
</body>
</html>
"""

# --- BACKEND ---

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/send_code', methods=['POST'])
def send_code():
    global client, phone_number
    phone_number = request.json.get('phone')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = TelegramClient(f"session_{phone_number}", API_ID, API_HASH)
    try:
        loop.run_until_complete(client.connect())
        loop.run_until_complete(client.send_code_request(phone_number))
        add_log(f"Kod gönderildi: {phone_number}")
        return jsonify({"status": "ok", "msg": "Kod gönderildi."})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

@app.route('/verify', methods=['POST'])
def verify():
    otp = request.json.get('otp')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Kodla giriş denemesi
        loop.run_until_complete(client.sign_in(phone_number, otp))
        start_bot_in_background()
        return jsonify({"status": "ok", "msg": "Başarıyla giriş yapıldı!"})
    except errors.SessionPasswordNeededError:
        add_log("2FA Şifresi gerekiyor...")
        return jsonify({"status": "password_required", "msg": "Şifre gerekli."})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

@app.route('/verify_password', methods=['POST'])
def verify_password():
    password = request.json.get('password')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(client.sign_in(password=password))
        start_bot_in_background()
        return jsonify({"status": "ok", "msg": "Şifre doğrulandı, bot aktif!"})
    except Exception as e:
        return jsonify({"status": "error", "msg": f"Şifre hatası: {str(e)}"})

def start_bot_in_background():
    def bot_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def run():
            add_log("Bot dinlemeye başladı...")
            @client.on(events.NewMessage(incoming=True))
            async def handler(event):
                if not event.is_private: return
                msg = event.message.text.lower()
                for t, r in rules.items():
                    if t in msg:
                        await event.reply(r)
                        add_log(f"Yanıtlandı: {t}")
            await client.run_until_disconnected()
        loop.run_until_complete(run())
    threading.Thread(target=bot_thread, daemon=True).start()

@app.route('/add_rule', methods=['POST'])
def add_rule():
    t = request.json.get('trigger').lower()
    r = request.json.get('reply')
    rules[t] = r
    return jsonify({"status": "ok"})

@app.route('/get_logs')
def get_logs():
    return jsonify(logs)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
