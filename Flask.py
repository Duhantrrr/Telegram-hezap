import threading
import asyncio
from flask import Flask, render_template_string, request, jsonify
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
import webbrowser

# --- AYARLAR ---
# https://my.telegram.org adresinden aldığınız bilgileri buraya girin
API_ID = 27861882  # Burayı sayı olarak değiştirin
API_HASH = 'd1c630d699c775e846bf64aadd18aefd'

app = Flask(__name__)
client = None
phone_code_hash = None
target_phone = None

# Kurallar ve Loglar
rules = {} 
logs = []

def add_log(text):
    print(f"[LOG] {text}")
    logs.append(text)

# --- HTML/CSS ARAYÜZÜ ---
HTML_PAGE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>Telegram Bot Panel</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f0f2f5; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .main-card { border: none; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); background: white; }
        .header-box { background: #0088cc; color: white; border-radius: 15px 15px 0 0; padding: 20px; }
        .log-area { background: #1e1e1e; color: #00ff00; height: 250px; overflow-y: auto; font-family: 'Courier New', monospace; padding: 15px; border-radius: 8px; font-size: 13px; }
        .btn-telegram { background: #0088cc; color: white; border: none; }
        .btn-telegram:hover { background: #0077b5; color: white; }
        .rule-item { border-left: 5px solid #0088cc; margin-bottom: 10px; background: #f8f9fa; }
    </style>
</head>
<body>
    <div class="container py-5">
        <div class="row justify-content-center">
            <div class="col-lg-8">
                <div class="card main-card">
                    <div class="header-box text-center">
                        <h2 class="mb-0">Telegram Otomatik Yanıt Sistemi</h2>
                        <small>Hesabınızı yönetin ve kurallar ekleyin</small>
                    </div>
                    
                    <div class="card-body p-4">
                        <!-- Login Bölümü -->
                        <div id="auth-section" class="mb-4 p-3 border rounded">
                            <h5>1. Adım: Hesaba Bağlan</h5>
                            <div class="input-group mb-2">
                                <input type="text" id="phone" class="form-control" placeholder="+905xxxxxxxxx">
                                <button onclick="sendCode()" class="btn btn-telegram">Kod Gönder</button>
                            </div>
                            <div id="otp-area" style="display:none;">
                                <div class="input-group mb-2">
                                    <input type="text" id="otp" class="form-control" placeholder="Telegram'dan gelen kod">
                                    <button onclick="verifyCode()" class="btn btn-success">Giriş Yap</button>
                                </div>
                            </div>
                        </div>

                        <!-- Kural Ekleme -->
                        <div class="mb-4">
                            <h5>2. Adım: Otomatik Yanıt Kuralları</h5>
                            <div class="row g-2">
                                <div class="col-md-5">
                                    <input type="text" id="trigger" class="form-control" placeholder="Eğer mesaj bunu içerirse...">
                                </div>
                                <div class="col-md-5">
                                    <input type="text" id="reply" class="form-control" placeholder="Şu cevabı gönder...">
                                </div>
                                <div class="col-md-2">
                                    <button onclick="addRule()" class="btn btn-dark w-100">Ekle</button>
                                </div>
                            </div>
                        </div>

                        <!-- Canlı Loglar -->
                        <div class="mb-4">
                            <h5>İşlem Kayıtları</h5>
                            <div id="log-box" class="log-area"></div>
                        </div>

                        <!-- Aktif Kurallar Listesi -->
                        <div>
                            <h5>Aktif Kurallar</h5>
                            <div id="rule-list"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function sendCode() {
            const phone = document.getElementById('phone').value;
            fetch('/send_code', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({phone: phone})
            })
            .then(r => r.json())
            .then(data => {
                if(data.status === "ok") {
                    document.getElementById('otp-area').style.display = 'block';
                    alert("Onay kodu gönderildi!");
                } else {
                    alert("Hata: " + data.message);
                }
            });
        }

        function verifyCode() {
            const otp = document.getElementById('otp').value;
            fetch('/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({otp: otp})
            })
            .then(r => r.json())
            .then(data => {
                alert(data.message);
            });
        }

        function addRule() {
            const t = document.getElementById('trigger').value;
            const r = document.getElementById('reply').value;
            fetch('/add_rule', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({trigger: t, reply: r})
            })
            .then(() => {
                const list = document.getElementById('rule-list');
                list.innerHTML += `<div class="p-2 rule-item"><strong>${t}</strong> yazana <strong>${r}</strong> denecek.</div>`;
            });
        }

        setInterval(() => {
            fetch('/get_logs').then(r => r.json()).then(data => {
                const box = document.getElementById('log-box');
                box.innerHTML = data.join('<br>');
                box.scrollTop = box.scrollHeight;
            });
        }, 2000);
    </script>
</body>
</html>
"""

# --- BACKEND İŞLEMLERİ ---

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/send_code', methods=['POST'])
def send_code():
    global client, phone_code_hash, target_phone
    target_phone = request.json['phone']
    
    # Yeni bir loop oluşturarak client'ı başlat
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    client = TelegramClient(f"session_{target_phone}", API_ID, API_HASH)
    
    async def connect_and_send():
        await client.connect()
        result = await client.send_code_request(target_phone)
        return result.phone_code_hash

    try:
        phone_code_hash = loop.run_until_complete(connect_and_send())
        add_log(f"Kod {target_phone} numarasına gönderildi.")
        return jsonify({"status": "ok"})
    except Exception as e:
        add_log(f"Hata oluştu: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/verify', methods=['POST'])
def verify():
    global client, phone_code_hash, target_phone
    otp = request.json['otp']
    
    def start_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def main():
            await client.sign_in(target_phone, otp, phone_code_hash=phone_code_hash)
            add_log("Giriş başarılı! Bot mesajları dinliyor...")

            @client.on(events.NewMessage(incoming=True))
            async def handler(event):
                if not event.is_private: return
                msg = event.message.text.lower()
                
                for trigger, reply in rules.items():
                    if trigger in msg:
                        add_log(f"Tetikleyici yakalandı: {trigger}")
                        await event.reply(reply)
            
            await client.run_until_disconnected()

        loop.run_until_complete(main())

    threading.Thread(target=start_bot, daemon=True).start()
    return jsonify({"message": "Giriş işlemi tamamlandı, bot arka planda başlatıldı."})

@app.route('/add_rule', methods=['POST'])
def add_rule():
    trigger = request.json['trigger'].lower()
    reply = request.json['reply']
    rules[trigger] = reply
    add_log(f"Yeni kural eklendi: {trigger}")
    return jsonify({"status": "ok"})

@app.route('/get_logs')
def get_logs():
    return jsonify(logs)

if __name__ == '__main__':
    add_log("Sunucu başlatılıyor... Lütfen tarayıcıyı kontrol edin.")
    webbrowser.open("http://127.0.0.1:5000")
    app.run(port=5000, debug=False, threaded=True)
