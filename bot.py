import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import TwoFactorRequired, ChallengeRequired, BadPassword

app = Flask(__name__)

BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_TOKEN = ""
start_time = 0
total_welcomes = 0

def log(msg):
    timestamp = datetime.now().strftime('%H:%M:%S')
    full_msg = f"[{timestamp}] {msg}"
    LOGS.append(full_msg)
    print(full_msg)

def login_client_token(token):
    cl = Client()
    try:
        if token:
            cl.login_by_sessionid(token)
            log("✅ Token login successful!")
            user = cl.account_info()
            log(f"👤 @{user.username} ready!")
            return cl
    except Exception as e:
        log(f"⚠️ Token error: {e}")
        return None

def login_client_username_pass(username, password):
    cl = Client()
    try:
        cl.login(username, password)
        cl.dump_settings("session.json")
        log("✅ Username/Password login successful!")
        return cl
    except Exception as e:
        log(f"⚠️ Login error: {e}")
        return None

def run_bot(token, username, password, welcome_messages, group_ids, delay, poll_interval, use_custom_name):
    global total_welcomes
    cl = login_client_token(token)
    if not cl:
        cl = login_client_username_pass(username, password)
    
    if not cl:
        log("🛑 Login failed!")
        return

    log("🤖 ULTRA AUTO WELCOME BOT ACTIVATED!")
    known_members = {}
    for gid in group_ids:
        try:
            group = cl.direct_thread(gid)
            known_members[gid] = {user.pk for user in group.users}
            log(f"📊 Group {gid}: {len(known_members[gid])} tracked")
        except Exception as e:
            log(f"⚠️ Group {gid}: {e}")
            known_members[gid] = set()

    while not STOP_EVENT.is_set():
        try:
            for gid in group_ids:
                if STOP_EVENT.is_set(): break
                try:
                    group = cl.direct_thread(gid)
                    current_members = {user.pk for user in group.users}
                    new_members = current_members - known_members[gid]

                    if new_members:
                        for user in group.users:
                            if user.pk in new_members and user.username != cl.account_info().username:
                                if STOP_EVENT.is_set(): break
                                for msg in welcome_messages:
                                    if STOP_EVENT.is_set(): break
                                    final_msg = f"@{user.username} {msg}" if use_custom_name else msg
                                    cl.direct_send(final_msg, thread_ids=[gid])
                                    total_welcomes += 1
                                    log(f"🎉 [{total_welcomes}] @{user.username} → {gid}")
                                    log(f"📤 '{final_msg[:50]}...'")
                                    for _ in range(delay):
                                        if STOP_EVENT.is_set(): break
                                        time.sleep(1)
                                known_members[gid].add(user.pk)
                    known_members[gid] = current_members
                except Exception as e:
                    log(f"⚠️ Group {gid}: {e}")
            if STOP_EVENT.is_set(): break
            log(f"⏳ Scanning... {poll_interval}s")
            for _ in range(poll_interval):
                if STOP_EVENT.is_set(): break
                time.sleep(1)
        except Exception as e:
            log(f"⚠️ Loop error: {e}")
            time.sleep(10)
    log(f"🛑 Stopped. Total welcomes: {total_welcomes}")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/set_token", methods=["POST"])
def set_token():
    global SESSION_TOKEN
    token = request.form.get("token", "").strip()
    if token:
        SESSION_TOKEN = token
        log(f"🔑 Token activated: {token[:20]}...")
        return jsonify({"message": "✅ Token ready!"})
    return jsonify({"error": "Empty token!"})

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT, start_time
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "⚙️ Bot running!"})
    
    token = SESSION_TOKEN
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    welcome_raw = request.form.get("welcome", "")
    welcome_messages = [m.strip() for m in welcome_raw.splitlines() if m.strip()]
    group_ids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    delay = int(request.form.get("delay", 3))
    poll_interval = int(request.form.get("poll", 10))
    use_custom_name = request.form.get("use_custom_name") == "yes"

    if not welcome_messages or not group_ids:
        return jsonify({"message": "⚠️ Messages & Groups required!"})
    if not token and not (username and password):
        return jsonify({"message": "❌ Token OR credentials required!"})

    STOP_EVENT.clear()
    start_time = time.time()
    BOT_THREAD = threading.Thread(target=run_bot, args=(token, username, password, welcome_messages, group_ids, delay, poll_interval, use_custom_name), daemon=True)
    BOT_THREAD.start()
    log("🚀 ULTRA BOT LIVE!")
    return jsonify({"message": "✅ Monitoring new members..."})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD, STOP_EVENT
    STOP_EVENT.set()
    log("🛑 Emergency stop!")
    if BOT_THREAD:
        BOT_THREAD.join(timeout=10)
    log("✅ Bot terminated!")
    return jsonify({"message": "✅ Bot stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-50:], "token_set": bool(SESSION_TOKEN), "welcomes": total_welcomes})

@app.route("/status")
def status():
    uptime = 0
    if start_time:
        uptime = int(time.time() - start_time)
    return jsonify({
        "token_ready": bool(SESSION_TOKEN),
        "bot_running": BOT_THREAD and BOT_THREAD.is_alive() if BOT_THREAD else False,
        "log_count": len(LOGS),
        "uptime": uptime,
        "welcomes": total_welcomes
    })

PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>🚀 ULTRA WELCOME BOT</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

:root{
    --violet:#8b2dff;
    --violet-glow:rgba(139,45,255,0.55);
    --violet-dim:rgba(139,45,255,0.25);
    --cyan:#22d3ee;
    --mint:#00ff9d;
}

html,body{height:100%;}
body {
    font-family: 'Poppins', sans-serif;
    background: #05030a;
    color: #fff;
    min-height: 100vh;
    overflow-x: hidden;
    position:relative;
}

/* ===== CINEMATIC ALIEN-OVERLORD BACKDROP ===== */
.backdrop{position:fixed;inset:0;z-index:0;overflow:hidden;background:
    radial-gradient(ellipse at 50% 115%,rgba(139,45,255,0.35) 0%,rgba(40,10,80,0.14) 35%,transparent 60%),
    radial-gradient(ellipse at 15% -10%,rgba(34,211,238,0.18) 0%,transparent 45%),
    linear-gradient(180deg,#07040d 0%,#0a0614 40%,#12081f 75%,#05020a 100%);
}
.backdrop svg{position:absolute;bottom:-2%;left:50%;transform:translateX(-50%);width:140%;max-width:1600px;opacity:0.5;filter:drop-shadow(0 0 60px rgba(139,45,255,0.35));}
.skyline{position:absolute;bottom:0;left:0;width:100%;height:20%;display:flex;align-items:flex-end;gap:2px;opacity:0.5;z-index:1;}
.skyline span{display:block;background:linear-gradient(180deg,#160a24,#02000100);flex:1;box-shadow:inset 0 0 20px rgba(139,45,255,0.18);}
.mist{position:absolute;border-radius:50%;background:radial-gradient(circle,rgba(60,15,110,0.5),transparent 70%);filter:blur(18px);animation:drift 24s linear infinite;}
.mist.m1{width:420px;height:420px;top:5%;left:-10%;animation-duration:32s;}
.mist.m2{width:520px;height:520px;top:18%;right:-15%;animation-duration:27s;animation-delay:-8s;}
.mist.m3{width:340px;height:340px;bottom:5%;left:20%;animation-duration:35s;animation-delay:-14s;}
@keyframes drift{0%{transform:translate(0,0) scale(1);}50%{transform:translate(40px,-30px) scale(1.15);}100%{transform:translate(0,0) scale(1);}}
.sparks{position:absolute;inset:0;pointer-events:none;}
.sparks i{position:absolute;bottom:-5%;width:3px;height:3px;background:#22d3ee;border-radius:50%;box-shadow:0 0 8px 2px rgba(34,211,238,0.85);animation:rise linear infinite;}
@keyframes rise{0%{transform:translateY(0) translateX(0);opacity:0;}10%{opacity:1;}100%{transform:translateY(-110vh) translateX(20px);opacity:0;}}
.pulse-flash{position:fixed;inset:0;background:rgba(139,45,255,0.3);opacity:0;pointer-events:none;z-index:2;animation:flash 9s infinite;}
@keyframes flash{0%,93%,100%{opacity:0;}93.3%{opacity:0.5;}93.6%{opacity:0;}94%{opacity:0.3;}94.3%{opacity:0;}}

.container {
    position:relative;z-index:3;
    max-width: 780px;
    margin: 0 auto;
    padding: 22px 16px 40px;
}

h1 {
    text-align: center;
    font-family: 'Orbitron', monospace;
    font-size: 2.5rem;
    font-weight: 700;
    background: linear-gradient(45deg, var(--cyan), var(--violet), var(--mint));
    background-size:200% 200%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 6px;
    text-shadow: 0 0 30px rgba(139, 45, 255, 0.35);
    animation: hueflow 6s ease infinite;
}
@keyframes hueflow{0%,100%{background-position:0% 50%;}50%{background-position:100% 50%;}}
h1 i{-webkit-text-fill-color:var(--violet);filter:drop-shadow(0 0 10px var(--violet-glow));}

.subtag{text-align:center;color:#c3a8e0;font-size:0.82rem;letter-spacing:1px;text-transform:uppercase;margin-bottom:16px;}

.pagedots{display:flex;justify-content:center;gap:9px;margin:6px 0 18px;}
.pagedots span{width:9px;height:9px;border-radius:50%;background:rgba(255,255,255,0.15);border:1px solid rgba(139,45,255,0.45);transition:all .3s;cursor:pointer;}
.pagedots span.on{background:var(--violet);box-shadow:0 0 10px var(--violet-glow);transform:scale(1.2);}

/* ===== BOOK / PAGE FLIP ===== */
.book{position:relative;perspective:2400px;}
.page{
    position:relative;
    transform-origin:center;
    transition:transform .55s cubic-bezier(.4,.2,.2,1), opacity .45s ease;
    display:none;
    backface-visibility:hidden;
}
.page.active{display:block;transform:rotateY(0deg);opacity:1;}
.page.leave-next{transform:rotateY(-100deg);opacity:0;}
.page.leave-prev{transform:rotateY(100deg);opacity:0;}
.page.enter-from-next{transform:rotateY(100deg);opacity:0;}
.page.enter-from-prev{transform:rotateY(-100deg);opacity:0;}

.pagehead{display:flex;align-items:center;gap:10px;margin-bottom:14px;}
.pagehead .num{
    font-family:'Orbitron',monospace;font-size:1rem;color:var(--violet);
    border:1px solid var(--violet-dim);border-radius:8px;padding:2px 10px;box-shadow:0 0 10px var(--violet-dim) inset;
}
.pagehead h2{font-size:1rem;letter-spacing:1.5px;text-transform:uppercase;color:#e6d6ff;font-weight:700;}

/* ===== GLASS CARD ===== */
.glass-card {
    background: rgba(20, 10, 35, 0.55);
    backdrop-filter: blur(18px) saturate(140%);
    -webkit-backdrop-filter: blur(18px) saturate(140%);
    border-radius: 20px;
    padding: 22px;
    border: 1px solid rgba(139, 45, 255, 0.35);
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5), 0 0 24px rgba(139,45,255,0.1);
    position: relative;
    overflow: hidden;
    margin-bottom: 18px;
}

.glass-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--cyan), var(--violet), var(--mint));
    background-size: 300% 100%;
    animation: shimmer 3s infinite;
}

@keyframes shimmer {
    0% { background-position: 0% 0; }
    50% { background-position: 100% 0; }
    100% { background-position: 0% 0; }
}

.status-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 14px;
    margin-bottom: 4px;
}

.status-card {
    background: rgba(255, 255, 255, 0.06);
    border-radius: 16px;
    padding: 20px 10px;
    text-align: center;
    border: 2px solid rgba(34, 211, 238, 0.3);
    transition: all 0.3s ease;
}

.status-card.ready {
    border-color: #00ff9d;
    background: rgba(0, 255, 157, 0.15);
}

.status-card.running {
    border-color: #00ff9d;
    background: rgba(0, 255, 157, 0.22);
    animation: statuspulse 2s infinite;
}

@keyframes statuspulse {
    0% { box-shadow: 0 0 0 0 rgba(0, 255, 157, 0.6); }
    70% { box-shadow: 0 0 0 16px rgba(0, 255, 157, 0); }
    100% { box-shadow: 0 0 0 0 rgba(0, 255, 157, 0); }
}

.status-card.error {
    border-color: #ff4757;
    background: rgba(255, 71, 87, 0.18);
}

.status-icon {
    font-size: 2rem;
    margin-bottom: 10px;
    display: block;
    color: var(--cyan);
}

.token-box {
    background: rgba(0, 255, 157, 0.1);
    border: 2px solid #00ff9d;
    border-radius: 18px;
    padding: 24px;
    margin-bottom: 4px;
    text-align: center;
}
.token-box h3{color:#7cffce;margin-bottom:14px;font-size:1rem;}

.form-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 18px;
}

.input-group { position: relative; }

.input-group label {
    display: block;
    margin-bottom: 10px;
    color: var(--cyan);
    font-weight: 600;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 1px;
}

input, textarea, select {
    width: 100%;
    padding: 15px 16px;
    background: rgba(255, 255, 255, 0.06);
    border: 2px solid rgba(139, 45, 255, 0.35);
    border-radius: 14px;
    color: #fff;
    font-size: 15px;
    font-family: 'Poppins', sans-serif;
    transition: all 0.3s ease;
    box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.25);
}

input:focus, textarea:focus, select:focus {
    outline: none;
    border-color: var(--cyan);
    background: rgba(255, 255, 255, 0.1);
    box-shadow: 0 0 20px rgba(34, 211, 238, 0.3);
}

textarea { resize: vertical; min-height: 130px; }

select {
    cursor: pointer;
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%2322d3ee' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 15px center;
    background-size: 18px;
    padding-right: 45px;
}

.full-width { grid-column: 1 / -1; }

.btn {
    border: none;
    padding: 16px 30px;
    font-size: 15px;
    font-weight: 700;
    border-radius: 14px;
    color: white;
    cursor: pointer;
    transition: all 0.25s ease;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.35);
    font-family: 'Orbitron', monospace;
    flex:1;min-width:130px;
}

.btn:hover { transform: translateY(-3px); filter:brightness(1.1); }
.btn:active { transform: translateY(-1px); }

.btn-success { background: linear-gradient(135deg, #00ff9d, #00b36b); box-shadow:0 0 20px rgba(0,255,157,0.45),0 8px 20px rgba(0,0,0,0.4); }
.btn-primary { background: linear-gradient(135deg, var(--cyan), #6d28d9); font-size: 16px; box-shadow:0 0 20px rgba(139,45,255,0.5),0 8px 20px rgba(0,0,0,0.4); }
.btn-danger { background: linear-gradient(135deg, #ff4757, #b8001f); box-shadow:0 0 20px rgba(255,71,87,0.5),0 8px 20px rgba(0,0,0,0.4); }
.btn-sample { background: linear-gradient(135deg, #3a3f47, #181b1f); border:1px solid #55595f; }

.buttons {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 14px;
}

.log-section {
    background: rgba(0, 0, 0, 0.4);
    border-radius: 18px;
    padding: 22px;
    border: 2px solid rgba(34, 211, 238, 0.3);
}

.log-section h3 {
    text-align: center;
    margin-bottom: 16px;
    color: var(--cyan);
    font-size: 1.15rem;
    font-weight: 600;
}

.log-box {
    background: rgba(0, 0, 0, 0.8);
    border-radius: 14px;
    padding: 18px;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
    height: min(50vh, 350px);
    overflow-y: auto;
    border: 1px solid rgba(139, 45, 255, 0.4);
    box-shadow: inset 0 0 15px rgba(0, 0, 0, 0.5), 0 0 18px rgba(139,45,255,0.12);
    color:#c9a8ff;
    text-shadow:0 0 6px rgba(139,45,255,0.3);
}

.log-box::-webkit-scrollbar { width: 8px; }
.log-box::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.4); border-radius: 4px; }
.log-box::-webkit-scrollbar-thumb { background: var(--violet); border-radius: 4px; }
.log-box::-webkit-scrollbar-thumb:hover { background: var(--cyan); }

/* ===== NAV ===== */
.navrow{display:flex;justify-content:space-between;gap:12px;margin-top:16px;}
.navbtn{
    flex:1;padding:15px 18px;border-radius:14px;border:1px solid var(--violet);
    background:linear-gradient(135deg,rgba(139,45,255,0.25),rgba(30,5,60,0.35));
    color:#e6d6ff;font-weight:700;letter-spacing:0.5px;cursor:pointer;
    display:flex;align-items:center;justify-content:center;gap:8px;
    box-shadow:0 0 16px rgba(139,45,255,0.35);transition:all .25s;
    font-family:'Orbitron',monospace;font-size:0.8rem;text-transform:uppercase;
}
.navbtn:hover{box-shadow:0 0 26px rgba(139,45,255,0.6);transform:translateY(-2px);}
.navbtn:disabled{opacity:0.25;cursor:not-allowed;box-shadow:none;transform:none;}

@media (max-width: 480px) {
    .status-grid { grid-template-columns: 1fr 1fr; }
    .btn{width:100%;}
}
</style>
</head>
<body>
<div class="backdrop">
    <div class="mist m1"></div>
    <div class="mist m2"></div>
    <div class="mist m3"></div>
    <svg viewBox="0 0 800 420" xmlns="http://www.w3.org/2000/svg">
        <path fill="#170a26" d="M60,420 C40,300 90,260 70,190 C55,140 110,120 130,150 C145,100 190,95 205,140 C230,90 280,95 290,150 C310,110 360,120 365,170 C400,120 450,130 455,180 C480,140 530,150 530,200 C560,160 610,175 605,225 C640,200 690,215 680,260 C710,250 745,275 730,320 C750,340 745,390 720,420 Z"/>
        <circle cx="205" cy="150" r="7" fill="#22d3ee" opacity="0.85"/>
        <circle cx="290" cy="160" r="6" fill="#22d3ee" opacity="0.7"/>
    </svg>
    <div class="skyline">
        <span style="height:40%"></span><span style="height:65%"></span><span style="height:30%"></span>
        <span style="height:80%"></span><span style="height:45%"></span><span style="height:70%"></span>
        <span style="height:35%"></span><span style="height:90%"></span><span style="height:50%"></span>
        <span style="height:60%"></span><span style="height:25%"></span><span style="height:75%"></span>
        <span style="height:40%"></span><span style="height:55%"></span><span style="height:85%"></span>
    </div>
    <div class="sparks" id="sparks"></div>
</div>
<div class="pulse-flash"></div>

<div class="container">
    <h1><i class="fas fa-robot"></i> AUTO WELCOME BOT</h1>
    <div class="subtag">🚀 ULTRA WELCOME BOT</div>

    <div class="pagedots">
        <span class="dot on" data-i="1"></span>
        <span class="dot" data-i="2"></span>
        <span class="dot" data-i="3"></span>
        <span class="dot" data-i="4"></span>
    </div>

    <div class="book" id="book">

        <!-- PAGE 1: STATUS + TOKEN -->
        <section class="page active" data-page="1">
            <div class="glass-card">
                <div class="status-grid" id="statusGrid">
                    <div class="status-card error" id="tokenCard">
                        <i class="fas fa-key status-icon"></i>
                        <strong>Token</strong><br>
                        <span id="tokenStatus">❌ Missing</span>
                    </div>
                    <div class="status-card error" id="botCard">
                        <i class="fas fa-play status-icon"></i>
                        <strong>Bot</strong><br>
                        <span id="botStatus">🔴 Stopped</span>
                    </div>
                    <div class="status-card">
                        <i class="fas fa-users status-icon"></i>
                        <strong>Welcomes</strong><br>
                        <span id="welcomeCount">0</span>
                    </div>
                    <div class="status-card">
                        <i class="fas fa-clock status-icon"></i>
                        <strong>Uptime</strong><br>
                        <span id="uptime">00:00:00</span>
                    </div>
                </div>
            </div>

            <div class="glass-card token-box">
                <h3><i class="fas fa-paste"></i> Paste Token Here</h3>
                <form id="tokenForm">
                    <div class="input-group full-width">
                        <label>Session Token</label>
                        <input type="text" id="tokenInput" name="token" placeholder="56748960230%3AF8ELTyGZTkSadW...">
                    </div>
                    <button type="button" class="btn btn-success" onclick="setToken()">
                        <i class="fas fa-check"></i> SET TOKEN
                    </button>
                </form>
                <div id="tokenStatusText" style="margin-top: 10px; color: #00ff9d;"></div>
            </div>

            <div class="navrow">
                <button type="button" class="navbtn" disabled><i class="fas fa-chevron-left"></i> Previous</button>
                <button type="button" class="navbtn" onclick="goPage(2)">Next <i class="fas fa-chevron-right"></i></button>
            </div>
        </section>

        <!-- PAGE 2: CONFIG -->
        <section class="page" data-page="2">
            <div class="pagehead"><span class="num">02</span><h2>Bot Configuration</h2></div>

            <form id="botForm">
                <div class="glass-card">
                    <div class="form-grid">
                        <div class="input-group">
                            <label><i class="fas fa-user"></i> Username (Optional)</label>
                            <input type="text" name="username" placeholder="@username">
                        </div>

                        <div class="input-group">
                            <label><i class="fas fa-lock"></i> Password (Optional)</label>
                            <input type="password" name="password" placeholder="••••••••">
                        </div>

                        <div class="input-group full-width">
                            <label><i class="fas fa-comment-dots"></i> Welcome Messages</label>
                            <textarea name="welcome" placeholder="Welcome @username!&#10;Glad you're here!&#10;Say hello everyone!"></textarea>
                        </div>

                        <div class="input-group full-width">
                            <label><i class="fas fa-users"></i> Group IDs</label>
                            <input type="text" name="group_ids" placeholder="24632887389663044, 123456789">
                        </div>

                        <div class="input-group">
                            <label><i class="fas fa-user-tag"></i> Mention Username?</label>
                            <select name="use_custom_name">
                                <option value="yes">✅ Yes (@username)</option>
                                <option value="no">❌ No</option>
                            </select>
                        </div>

                        <div class="input-group">
                            <label><i class="fas fa-stopwatch"></i> Delay (seconds)</label>
                            <input type="number" name="delay" value="3" min="1">
                        </div>

                        <div class="input-group">
                            <label><i class="fas fa-sync"></i> Check Interval</label>
                            <input type="number" name="poll" value="10" min="5">
                        </div>
                    </div>
                </div>
            </form>

            <div class="navrow">
                <button type="button" class="navbtn" onclick="goPage(1)"><i class="fas fa-chevron-left"></i> Previous</button>
                <button type="button" class="navbtn" onclick="goPage(3)">Next <i class="fas fa-chevron-right"></i></button>
            </div>
        </section>

        <!-- PAGE 3: CONTROLS -->
        <section class="page" data-page="3">
            <div class="pagehead"><span class="num">03</span><h2>Controls</h2></div>

            <div class="glass-card">
                <div class="buttons">
                    <button type="button" class="btn btn-primary" onclick="startBot()" id="startBtn" disabled>
                        <i class="fas fa-rocket"></i> START BOT
                    </button>
                    <button type="button" class="btn btn-danger" onclick="stopBot()">
                        <i class="fas fa-stop"></i> STOP BOT
                    </button>
                    <button type="button" class="btn btn-sample" onclick="downloadSample()">
                        <i class="fas fa-download"></i> SAMPLE
                    </button>
                </div>
            </div>

            <div class="navrow">
                <button type="button" class="navbtn" onclick="goPage(2)"><i class="fas fa-chevron-left"></i> Previous</button>
                <button type="button" class="navbtn" onclick="goPage(4)">Next <i class="fas fa-chevron-right"></i></button>
            </div>
        </section>

        <!-- PAGE 4: LOGS -->
        <section class="page" data-page="4">
            <div class="pagehead"><span class="num">04</span><h2>Live Logs</h2></div>

            <div class="glass-card log-section">
                <h3><i class="fas fa-terminal"></i> Live Logs</h3>
                <div class="log-box" id="logs">Bot ready! Paste token and start monitoring...</div>
            </div>

            <div class="navrow">
                <button type="button" class="navbtn" onclick="goPage(3)"><i class="fas fa-chevron-left"></i> Previous</button>
                <button type="button" class="navbtn" disabled>Next <i class="fas fa-chevron-right"></i></button>
            </div>
        </section>

    </div>
</div>

<script>
let tokenSet = false;
let startTime = 0;

// ---- decorative floating sparks ----
(function(){
    const box = document.getElementById('sparks');
    for(let i=0;i<24;i++){
        const e = document.createElement('i');
        e.style.left = (Math.random()*100)+'%';
        e.style.animationDuration = (6+Math.random()*8)+'s';
        e.style.animationDelay = (Math.random()*8)+'s';
        box.appendChild(e);
    }
})();

// ---- book page navigation ----
let currentPage = 1;
function goPage(target){
    if(target === currentPage) return;
    const dir = target > currentPage ? 'next' : 'prev';
    const curEl = document.querySelector('.page[data-page="'+currentPage+'"]');
    const nextEl = document.querySelector('.page[data-page="'+target+'"]');

    curEl.classList.add(dir === 'next' ? 'leave-next' : 'leave-prev');
    nextEl.style.display = 'block';
    nextEl.classList.add(dir === 'next' ? 'enter-from-next' : 'enter-from-prev');
    void nextEl.offsetWidth;

    requestAnimationFrame(() => {
        nextEl.classList.add('active');
        nextEl.classList.remove('enter-from-next','enter-from-prev');
    });

    setTimeout(() => {
        curEl.classList.remove('active','leave-next','leave-prev');
        curEl.style.display = 'none';
        currentPage = target;
        document.querySelectorAll('.pagedots .dot').forEach(d => {
            d.classList.toggle('on', parseInt(d.dataset.i) === currentPage);
        });
        window.scrollTo({top:0, behavior:'smooth'});
    }, 560);
}
document.querySelectorAll('.pagedots .dot').forEach(d => {
    d.addEventListener('click', () => goPage(parseInt(d.dataset.i)));
});

function setToken() {
    const token = document.getElementById('tokenInput').value.trim();
    if(!token) return alert('❌ Token paste करें!');
    
    const form = new FormData();
    form.append('token', token);
    
    fetch('/set_token', {method: 'POST', body: form})
    .then(res => res.json())
    .then(data => {
        if(data.message) {
            document.getElementById('tokenStatusText').innerHTML = '✅ Token set!';
            tokenSet = true;
            document.getElementById('startBtn').disabled = false;
            document.getElementById('tokenCard').className = 'status-card ready';
            document.getElementById('tokenStatus').innerHTML = '✅ Ready';
            alert('✅ Token activated!');
        } else {
            alert('❌ ' + (data.error || 'Token error'));
        }
    }).catch(e => alert('❌ Error: ' + e.message));
}

function startBot() {
    if(!tokenSet) return alert('❌ पहले Token set करें!');
    const form = new FormData(document.getElementById('botForm'));
    
    fetch('/start', {method: 'POST', body: form})
    .then(res => res.json())
    .then(data => {
        alert(data.message);
        if(data.message.includes('✅')) {
            document.getElementById('botCard').className = 'status-card running';
            document.getElementById('botStatus').innerHTML = '🟢 Running';
            startTime = Date.now();
        }
    }).catch(e => alert('❌ ' + e.message));
}

function stopBot() {
    fetch('/stop', {method: 'POST'})
    .then(res => res.json())
    .then(data => {
        alert(data.message);
        document.getElementById('botCard').className = 'status-card error';
        document.getElementById('botStatus').innerHTML = '🔴 Stopped';
    }).catch(e => alert('❌ Error'));
}

function fetchLogs() {
    fetch('/logs')
    .then(res => res.json())
    .then(data => {
        const box = document.getElementById('logs');
        box.innerHTML = data.logs.join('<br>');
        box.scrollTop = box.scrollHeight;
        document.getElementById('welcomeCount').textContent = data.welcomes || 0;
    });
}

function updateStatus() {
    fetch('/status')
    .then(res => res.json())
    .then(data => {
        document.getElementById('tokenStatus').textContent = data.token_ready ? '✅ Ready' : '❌ Missing';
        document.getElementById('botStatus').textContent = data.bot_running ? '🟢 Live' : '🔴 Stopped';
        
        if(data.uptime > 0) {
            const total = Math.floor(data.uptime);
            const h = Math.floor(total / 3600);
            const m = Math.floor((total % 3600) / 60);
            const s = total % 60;
            document.getElementById('uptime').textContent = 
                `${h.toString().padStart(2,'0')}:${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
        }
    });
}

function downloadSample() {
    const text = "Welcome @username! 🎉\
Glad you're here! 👋\
Introduce yourself! 💬\
Stay active 24x7! 🔥";
    const blob = new Blob([text], {type: 'text/plain'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'welcome.txt';
    link.click();
}

setInterval(fetchLogs, 2000);
setInterval(updateStatus, 3000);
updateStatus();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🚀 SMOOTH WELCOME BOT - No lag, perfect scroll!")
    app.run(host="0.0.0.0", port=port, debug=False)