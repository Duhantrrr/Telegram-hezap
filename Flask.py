import os
import threading
import asyncio
from flask import Flask, render_template_string, request, jsonify
from telethon import TelegramClient, events

# --- SENİN BİLGİLERİN ---
API_ID = 27861882
API_HASH = 'd1c630d699c775e846bf64aadd18aefd'

app = Flask(__name__)

# Global Değişkenler
client = None
rules = {}  # Kelime: Cevap
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
    <title>Telegram Otomatik Bot</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #f0f2f5; padding: 20px; font-family: sans-serif; }
        .card { border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); border: none; margin-bottom: 20px; }
        .log-box { background: #222; color: #0f0; height: 200px; overflow-y: auto; padding: 15px; font-family: monospace; border-radius: 10px; font-size: 12px; }
        .btn-primary { background: #0088cc; border: none; }
    </style>
</head>
<body>
<div class="container" style="max-width: 700px;">
    <div class="card p-4 text-center">
        <h2 style="color: #0088cc;">Telegram Bot Paneli</h2>
        <p class="text-muted">Hesabınızı buradan bağlayın ve kuralları yönetin.</p>
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
                <input type="text" id="otp" class="form-control" placeholder="Gelen Kodu Girin">
                <button onclick="verifyCode()" class="btn btn-success">Girişi Tamamla</button>
            </div>
        </div>
    </div>

    <div class="card p-4">
        <h5>2. Adım: Otomatik Yanıt Kuralları</h5>
        <div class="row g-2">
            <div class="col-5"><input type="text" id="trigger" class="form-control" placeholder="Eğer mesaj buysa..."></div>
            <div class="col-5"><input type="text" id="reply" class="form-control" placeholder="Şu cevabı ver..."></div>
            <div class="col-2"><button onclick="addRule()" class="btn btn-dark w-100">Ekle</button></div>
        </div>
        <div id="rule-list" class="mt-3"></div>
    </div>

    <div class="card p-4">
        <h5>Sistem Kayıtları</h5>
        <div id="logs" class="log-box"></div>
    </div>
</div>

<script>
    function sendCode() {
        const p = document.getElementById('phone').value;
        fetch('/send_code', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({phone:p}) })
        .then(res => res.json()).then(data => {
            alert(data.msg);
            if(data.status==='ok') document.getElementById('step2').style.display='block';
        });
    }

    function verifyCode() {
        const c = document.getElementById('otp').value;
        fetch('/verify', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({otp:c}) })
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
        add_log(f"Kod istendi: {phone_number}")
        return jsonify({"status": "ok", "msg": "Kod gönderildi, lütfen Telegram'ı kontrol edin."})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

@app.route('/verify', methods=['POST'])
def verify():
    otp = request.json.get('otp')
    
    def bot_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def run():
            await client.sign_in(phone_number, otp)
            add_log("Giriş başarılı! Mesajlar dinleniyor...")
            
            @client.on(events.NewMessage(incoming=True))
            async def handler(event):
                if not event.is_private: return
                msg_text = event.message.text.lower()
                
                for trig, rep in rules.items():
                    if trig in msg_text:
                        add_log(f"Tetiklendi: {trig} -> Yanıt gönderildi.")
                        await event.reply(rep)
            
            await client.run_until_disconnected()
            
        loop.run_until_complete(run())

    threading.Thread(target=bot_thread, daemon=True).start()
    return jsonify({"status": "ok", "msg": "Bot başarıyla başlatıldı!"})

@app.route('/add_rule', methods=['POST'])
def add_rule():
    t = request.json.get('trigger').lower()
    r = request.json.get('reply')
    rules[t] = r
    add_log(f"Kural eklendi: {t}")
    return jsonify({"status": "ok"})

@app.route('/get_logs')
def get_logs():
    return jsonify(logs)

if __name__ == '__main__':
    # Render için hayati önem taşıyan ayarlar
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
