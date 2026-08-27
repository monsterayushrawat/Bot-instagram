import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, RateLimitError, ClientError, ClientForbiddenError, 
    ClientNotFoundError, ChallengeRequired, PleaseWaitFewMinutes
)

app = Flask(__name__)

# Global variables
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
START_TIME = None
CLIENT = None
SESSION_TOKEN = None
LOGIN_SUCCESS = False

STATS = {
    "total_welcomed": 0,
    "today_welcomed": 0,
    "last_reset": datetime.now().date()
}

BOT_CONFIG = {
    "auto_replies": {},
    "auto_reply_active": False,
    "target_spam": {},
    "spam_active": {},
    "media_library": {}
}

def uptime():
    if not START_TIME:
        return "00:00:00"
    delta = datetime.now() - START_TIME
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    if len(LOGS) > 500:
        LOGS[:] = LOGS[-500:]
    print(lm)

def clear_logs():
    global LOGS
    LOGS.clear()
    log("🧹 Logs cleared by user!")

def create_stable_client():
    cl = Client()
    cl.delay_range = [8, 15]
    cl.request_timeout = 90
    cl.max_retries = 1
    ua = "Instagram 380.0.0.28.104 Android (35/14; 600dpi; 1440x3360; samsung; SM-S936B; dm5q; exynos2500; en_IN; 380000028)"
    cl.set_user_agent(ua)
    return cl

def safe_login(cl, token, max_retries=3):
    global LOGIN_SUCCESS, SESSION_TOKEN
    for attempt in range(max_retries):
        try:
            log(f"🔐 Login attempt {attempt+1}/{max_retries}")
            cl.login_by_sessionid(token)
            account = cl.account_info()
            if account and hasattr(account, 'username') and account.username:
                username = account.username
                log(f"✅ Login SUCCESS: @{username}")
                LOGIN_SUCCESS = True
                SESSION_TOKEN = token
                time.sleep(3)
                return True, username
        except Exception as e:
            error_msg = str(e).lower()
            if "session" in error_msg or "login required" in error_msg:
                log("❌ Session expired!")
                return False, None
            elif "rate limit" in error_msg:
                log("⏳ Rate limited - 60s wait")
                time.sleep(60)
            elif "challenge" in error_msg:
                log("❌ Challenge required")
                time.sleep(30)
            else:
                log(f"⚠️ Login error: {str(e)[:50]}")
                time.sleep(15 * (attempt + 1))
    return False, None

def session_health_check():
    global CLIENT, LOGIN_SUCCESS
    try:
        if CLIENT:
            CLIENT.account_info()
            return True
    except:
        pass
    LOGIN_SUCCESS = False
    return False

def refresh_session(token):
    global CLIENT, LOGIN_SUCCESS
    log("🔄 Auto session refresh...")
    new_client = create_stable_client()
    success, _ = safe_login(new_client, token)
    if success:
        CLIENT = new_client
        return True
    return False

# ================= MAIN BOT WITH ADMIN COMMANDS =================
def run_bot(session_token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    global START_TIME, CLIENT, LOGIN_SUCCESS
    
    START_TIME = datetime.now()
    consecutive_errors = 0
    max_errors = 12
    
    log("🚀 Premium Bot v4.5 with ADMIN COMMANDS starting...")
    
    CLIENT = create_stable_client()
    success, username = safe_login(CLIENT, session_token)
    if not success:
        log("💥 Login failed - Bot STOPPED")
        return
    
    km = {gid: set() for gid in gids}
    lm = {gid: None for gid in gids}
    
    log("📱 Initializing groups...")
    for i, gid in enumerate(gids):
        try:
            time.sleep(10)
            thread = CLIENT.direct_thread(gid)
            km[gid] = {u.pk for u in thread.users}
            if thread.messages:
                lm[gid] = thread.messages[0].id
            BOT_CONFIG["spam_active"][gid] = False
            log(f"✅ Group {i+1}: {gid[:12]}...")
        except Exception as e:
            log(f"⚠️ Group error: {str(e)[:30]}")
    
    log("🎉 Bot running with FULL FEATURES!")
    
    while not STOP_EVENT.is_set():
        for gid in gids:
            if STOP_EVENT.is_set():
                break
                
            try:
                if not session_health_check():
                    if refresh_session(SESSION_TOKEN):
                        consecutive_errors = 0
                    else:
                        log("💥 Session recovery failed")
                        return
                
                time.sleep(random.uniform(12, 20))
                thread = CLIENT.direct_thread(gid)
                consecutive_errors = 0
                
                # ========== COMMANDS PROCESSING ==========
                if ecmd:
                    new_msgs = []
                    if lm[gid] and thread.messages:
                        for msg in thread.messages[:10]:
                            if msg.id == lm[gid]:
                                break
                            new_msgs.append(msg)
                    
                    for msg_obj in reversed(new_msgs[:3]):
                        try:
                            if not msg_obj or msg_obj.user_id == CLIENT.user_id:
                                continue
                                
                            sender = next((u for u in thread.users if u.pk == msg_obj.user_id), None)
                            if not sender or not hasattr(sender, 'username'):
                                continue
                                
                            text = (msg_obj.text or "").strip().lower()
                            sender_username = sender.username.lower()
                            
                            # ADMIN CHECK
                            is_admin = sender_username in [aid.lower() for aid in admin_ids] if admin_ids else False
                            
                            # ADMIN COMMANDS
                            if is_admin:
                                if text.startswith('/spam '):
                                    parts = msg_obj.text.split(" ", 2)
                                    if len(parts) == 3:
                                        BOT_CONFIG["target_spam"][gid] = {
                                            "username": parts[1].replace("@", ""),
                                            "message": parts[2]
                                        }
                                        BOT_CONFIG["spam_active"][gid] = True
                                        CLIENT.direct_send("🔥 Spam ON!", thread_ids=[gid])
                                        
                                elif text in ['/stopspam', '!stopspam']:
                                    BOT_CONFIG["spam_active"][gid] = False
                                    CLIENT.direct_send("🛑 Spam OFF!", thread_ids=[gid])
                                    
                            # PUBLIC COMMANDS
                            if text in ['/ping', '!ping']:
                                CLIENT.direct_send(f"🏓 Pong! Uptime: {uptime()}", thread_ids=[gid])
                            elif text in ['/uptime', '!uptime']:
                                CLIENT.direct_send(f"⏱️ Uptime: {uptime()}", thread_ids=[gid])
                            elif text in ['/help', '!help']:
                                help_msg = """📋 COMMANDS:
/ping - Bot status
/uptime - Running time
/help - This help

👑 ADMIN:
/spam @user message
/stopspam"""
                                CLIENT.direct_send(help_msg, thread_ids=[gid])
                        
                        except:
                            pass
                    
                    if thread.messages:
                        lm[gid] = thread.messages[0].id

                # ========== SPAM (Admin only) ==========
                if BOT_CONFIG["spam_active"].get(gid):
                    target = BOT_CONFIG["target_spam"].get(gid)
                    if target:
                        try:
                            msg = f"@{target['username']} {target['message']}"
                            CLIENT.direct_send(msg, thread_ids=[gid])
                            time.sleep(4)
                        except:
                            pass

                # ========== WELCOME NEW USERS ==========
                current_members = {u.pk for u in thread.users}
                new_users = current_members - km[gid]
                
                for user in thread.users:
                    if user.pk in new_users and hasattr(user, 'username') and user.username:
                        try:
                            welcome_msg = f"@{user.username} {wm[0]}" if ucn else wm[0]
                            CLIENT.direct_send(welcome_msg, thread_ids=[gid])
                            STATS["total_welcomed"] += 1
                            STATS["today_welcomed"] += 1
                            log(f"👋 NEW: @{user.username}")
                            time.sleep(dly * 2)
                            break
                        except:
                            break
                km[gid] = current_members

            except RateLimitError:
                consecutive_errors += 1
                log("⏳ Rate limit - 2min cooldown")
                time.sleep(120)
            except Exception as e:
                consecutive_errors += 1
                log(f"⚠️ Error: {str(e)[:40]}")
                time.sleep(15)
        
        if consecutive_errors > max_errors:
            log("🔄 Emergency restart...")
            if not refresh_session(SESSION_TOKEN):
                break
        
        time.sleep(pol + random.uniform(3, 7))

    log("🛑 Bot stopped")

# ================= FLASK ROUTES =================
@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start():
    global BOT_THREAD
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "❌ Bot already running!"})
    
    try:
        token = request.form.get("session", "").strip()
        welcome = [x.strip() for x in request.form.get("welcome", "").splitlines() if x.strip()]
        gids = [x.strip() for x in request.form.get("group_ids", "").split(",") if x.strip()]
        admins = [x.strip() for x in request.form.get("admin_ids", "").split(",") if x.strip()]
        
        if not all([token, welcome, gids]):
            return jsonify({"message": "❌ Fill Token, Welcome & Groups!"})

        global STOP_EVENT
        STOP_EVENT.clear()
        BOT_THREAD = threading.Thread(
            target=run_bot,
            args=(token, welcome, gids,
                  int(request.form.get("delay", 5)),
                  int(request.form.get("poll", 25)),
                  request.form.get("use_custom_name") == "yes",
                  request.form.get("enable_commands") == "yes",
                  admins),
            daemon=True
        )
        BOT_THREAD.start()
        log("🚀 Bot v4.5 STARTED with Admin support!")
        return jsonify({"message": "✅ Bot started! Admin commands ready!"})
    except Exception as e:
        return jsonify({"message": f"❌ Error: {str(e)}"})

@app.route("/stop", methods=["POST"])
def stop():
    global STOP_EVENT, CLIENT
    STOP_EVENT.set()
    CLIENT = None
    if BOT_THREAD:
        BOT_THREAD.join(timeout=5)
    log("🛑 Bot STOPPED!")
    return jsonify({"message": "✅ Bot stopped!"})

@app.route("/logs")
def logs():
    return jsonify({
        "logs": LOGS[-200:],
        "uptime": uptime(),
        "status": "running" if BOT_THREAD and BOT_THREAD.is_alive() else "stopped"
    })

@app.route("/clear_logs", methods=["POST"])
def clear_logs_route():
    clear_logs()
    return jsonify({"message": "✅ Logs cleared!"})

@app.route("/stats")
def stats():
    return jsonify({
        "uptime": uptime(),
        "status": "running" if BOT_THREAD and BOT_THREAD.is_alive() else "stopped",
        "total_welcomed": STATS["total_welcomed"],
        "today_welcomed": STATS["today_welcomed"]
    })

# ================= COMPLETE HTML WITH ADMIN FIELD =================
PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
    <title>Premium Instagram Bot v4.5 - Admin Panel</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Bebas+Neue&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        *{margin:0;padding:0;box-sizing:border-box;}
        :root{
            --red:#ff1a3c;
            --red-glow:rgba(255,26,60,0.55);
            --red-dim:rgba(255,26,60,0.25);
            --panel:rgba(15,8,10,0.62);
            --panel-strong:rgba(10,5,7,0.82);
        }
        html,body{height:100%;}
        body{
            font-family:'Inter',sans-serif;
            background:#050203;
            min-height:100vh;
            color:#f1e7e8;
            overflow-x:hidden;
            position:relative;
        }

        /* ===== CINEMATIC KAIJU BACKDROP ===== */
        .backdrop{position:fixed;inset:0;z-index:0;overflow:hidden;background:
            radial-gradient(ellipse at 50% 120%,rgba(255,26,60,0.35) 0%,rgba(120,10,20,0.12) 35%,transparent 60%),
            radial-gradient(ellipse at 20% -10%,rgba(255,60,60,0.18) 0%,transparent 45%),
            linear-gradient(180deg,#0a0405 0%,#0d0507 40%,#180307 75%,#050002 100%);
        }
        .backdrop svg{position:absolute;bottom:-2%;left:50%;transform:translateX(-50%);width:140%;max-width:1600px;opacity:0.5;filter:drop-shadow(0 0 60px rgba(255,26,60,0.35));}
        .city{position:absolute;bottom:0;left:0;width:100%;height:22%;display:flex;align-items:flex-end;gap:2px;opacity:0.55;z-index:1;}
        .city span{display:block;background:linear-gradient(180deg,#150406,#02000100);flex:1;box-shadow:inset 0 0 20px rgba(255,20,40,0.15);}
        .smoke{position:absolute;border-radius:50%;background:radial-gradient(circle,rgba(80,10,15,0.55),transparent 70%);filter:blur(18px);animation:drift 22s linear infinite;}
        .smoke.s1{width:420px;height:420px;top:5%;left:-10%;animation-duration:30s;}
        .smoke.s2{width:520px;height:520px;top:20%;right:-15%;animation-duration:26s;animation-delay:-8s;}
        .smoke.s3{width:340px;height:340px;bottom:5%;left:20%;animation-duration:34s;animation-delay:-14s;}
        @keyframes drift{0%{transform:translate(0,0) scale(1);}50%{transform:translate(40px,-30px) scale(1.15);}100%{transform:translate(0,0) scale(1);}}
        .embers{position:absolute;inset:0;pointer-events:none;}
        .embers i{position:absolute;bottom:-5%;width:3px;height:3px;background:#ff5c3c;border-radius:50%;box-shadow:0 0 8px 2px rgba(255,90,50,0.8);animation:rise linear infinite;}
        @keyframes rise{0%{transform:translateY(0) translateX(0);opacity:0;}10%{opacity:1;}100%{transform:translateY(-110vh) translateX(20px);opacity:0;}}
        .lightning{position:fixed;inset:0;background:rgba(255,60,60,0.35);opacity:0;pointer-events:none;z-index:2;animation:flash 9s infinite;}
        @keyframes flash{0%,93%,100%{opacity:0;}93.3%{opacity:0.55;}93.6%{opacity:0;}94%{opacity:0.35;}94.3%{opacity:0;}}

        /* ===== SHELL ===== */
        .shell{position:relative;z-index:3;max-width:760px;margin:0 auto;padding:22px 16px 40px;min-height:100vh;display:flex;flex-direction:column;}
        .brandbar{text-align:center;margin-bottom:18px;}
        .brandbar h1{
            font-family:'Bebas Neue',Inter,sans-serif;
            font-size:2.9rem;letter-spacing:3px;color:#fff;
            text-shadow:0 0 12px var(--red-glow),0 0 40px rgba(255,26,60,0.35);
        }
        .brandbar h1 i{color:var(--red);margin-right:10px;filter:drop-shadow(0 0 10px var(--red-glow));}
        .brandbar p{color:#c7a3a8;font-size:0.85rem;letter-spacing:1px;margin-top:4px;text-transform:uppercase;}

        .pagedots{display:flex;justify-content:center;gap:9px;margin:14px 0 6px;}
        .pagedots span{width:9px;height:9px;border-radius:50%;background:rgba(255,255,255,0.15);border:1px solid rgba(255,26,60,0.4);transition:all .3s;}
        .pagedots span.on{background:var(--red);box-shadow:0 0 10px var(--red-glow);transform:scale(1.2);}

        /* ===== BOOK / PAGE FLIP ===== */
        .book{position:relative;perspective:2400px;flex:1;}
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

        .pagehead{display:flex;align-items:center;gap:10px;margin-bottom:16px;}
        .pagehead .num{
            font-family:'Bebas Neue',sans-serif;font-size:1.1rem;color:var(--red);
            border:1px solid var(--red-dim);border-radius:8px;padding:2px 10px;box-shadow:0 0 10px var(--red-dim) inset;
        }
        .pagehead h2{font-size:1.05rem;letter-spacing:1.5px;text-transform:uppercase;color:#f4d9dc;font-weight:700;}

        /* ===== GLASS CARDS ===== */
        .card{
            background:var(--panel);
            backdrop-filter:blur(14px) saturate(140%);
            -webkit-backdrop-filter:blur(14px) saturate(140%);
            border:1px solid rgba(255,26,60,0.35);
            border-radius:20px;
            padding:22px;
            margin-bottom:18px;
            box-shadow:0 8px 30px rgba(0,0,0,0.55),0 0 0 1px rgba(255,26,60,0.05) inset, 0 0 24px rgba(255,26,60,0.08);
        }

        /* status */
        .status-bar{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;}
        .status-item{display:flex;align-items:center;gap:10px;font-weight:600;letter-spacing:0.5px;}
        .status-running{color:#3dffa0;}.status-stopped{color:var(--red);}
        .status-dot{width:12px;height:12px;border-radius:50%;background:var(--red);box-shadow:0 0 12px var(--red-glow);animation:pulse 1.6s infinite;}
        @keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.4;}}
        #uptime{font-family:'Bebas Neue',monospace;font-size:1.2rem;letter-spacing:2px;color:#fff;}

        /* stats */
        .stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:18px;}
        .stat-card{padding:22px 10px;text-align:center;}
        .stat-number{font-family:'Bebas Neue',sans-serif;font-size:2.6rem;color:#fff;text-shadow:0 0 18px var(--red-glow);margin-bottom:4px;}
        .stat-card div:last-child{font-size:0.78rem;letter-spacing:1.5px;text-transform:uppercase;color:#d9a5ab;}

        /* logo block */
        .logo-wrap{display:flex;flex-direction:column;align-items:center;padding:26px 20px;}
        .logo-ring{
            width:92px;height:92px;border-radius:50%;
            display:flex;align-items:center;justify-content:center;
            border:2px solid var(--red);
            box-shadow:0 0 25px var(--red-glow),0 0 60px rgba(255,26,60,0.25) inset;
            margin-bottom:14px;background:radial-gradient(circle,rgba(255,26,60,0.15),transparent 70%);
        }
        .logo-ring i{font-size:2.4rem;color:var(--red);filter:drop-shadow(0 0 10px var(--red-glow));}
        .logo-wrap .tagline{color:#c7a3a8;font-size:0.85rem;letter-spacing:1px;text-align:center;}

        /* form */
        label{display:block;margin-bottom:8px;font-weight:600;color:#f0d6d9;font-size:0.9rem;letter-spacing:0.3px;}
        label i{color:var(--red);margin-right:6px;width:16px;text-align:center;}
        input,textarea{
            width:100%;padding:14px 16px;border-radius:12px;font-size:0.95rem;
            background:rgba(0,0,0,0.45);color:#fdeef0;
            border:1px solid rgba(255,26,60,0.3);
            transition:all 0.25s;
        }
        input::placeholder,textarea::placeholder{color:#7a5459;}
        input:focus,textarea:focus{outline:none;border-color:var(--red);box-shadow:0 0 0 3px rgba(255,26,60,0.18),0 0 20px rgba(255,26,60,0.25);}
        textarea{resize:vertical;min-height:120px;font-family:inherit;}
        .form-group{margin-bottom:18px;}
        .hint{color:#f59e0b;font-weight:500;}
        .req{color:var(--red);}

        /* toggles */
        .toggle-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:16px 18px;margin-bottom:14px;}
        .toggle-row .lbl{display:flex;align-items:center;gap:10px;font-weight:600;color:#f0d6d9;font-size:0.92rem;cursor:pointer;}
        .toggle-row .lbl i{color:var(--red);}
        .switch{position:relative;width:52px;height:28px;flex-shrink:0;cursor:pointer;}
        .switch input{opacity:0;width:0;height:0;position:absolute;}
        .slider{position:absolute;inset:0;background:rgba(255,255,255,0.12);border:1px solid rgba(255,26,60,0.4);border-radius:999px;transition:.3s;}
        .slider:before{content:'';position:absolute;width:20px;height:20px;left:3px;top:3px;background:#7a5459;border-radius:50%;transition:.3s;}
        .switch input:checked + .slider{background:rgba(255,26,60,0.35);border-color:var(--red);box-shadow:0 0 12px var(--red-glow);}
        .switch input:checked + .slider:before{transform:translateX(24px);background:var(--red);box-shadow:0 0 8px var(--red-glow);}

        /* admin section */
        .admin-section{border:1px solid rgba(245,158,11,0.5);background:rgba(40,20,4,0.5);}
        .admin-section h3{color:#f5b03e;margin-bottom:12px;font-size:1rem;letter-spacing:0.5px;}
        .admin-section .cmdline{font-size:0.9rem;color:#f0ce9c;line-height:1.9;}
        .admin-section strong{color:#ffd27a;}

        /* buttons */
        .controls{display:flex;gap:14px;justify-content:center;margin:8px 0 4px;flex-wrap:wrap;}
        .btn{
            padding:16px 26px;border:none;border-radius:14px;font-size:1rem;font-weight:700;
            cursor:pointer;transition:all 0.25s;display:flex;align-items:center;gap:10px;letter-spacing:0.5px;
            flex:1;min-width:140px;justify-content:center;
        }
        .btn-start{background:linear-gradient(135deg,#0dff8a,#059669);color:#04240f;box-shadow:0 0 20px rgba(13,255,138,0.55),0 8px 20px rgba(0,0,0,0.4);}
        .btn-stop{background:linear-gradient(135deg,#ff3050,#8f0d1c);color:#fff;box-shadow:0 0 22px rgba(255,26,60,0.6),0 8px 20px rgba(0,0,0,0.4);}
        .btn-clear{background:linear-gradient(135deg,#3a3f47,#181b1f);color:#e6e6e6;border:1px solid #55595f;box-shadow:0 8px 20px rgba(0,0,0,0.5);}
        .btn:hover{transform:translateY(-3px);filter:brightness(1.1);}
        .btn:active{transform:translateY(0);}

        /* nav */
        .navrow{display:flex;justify-content:space-between;gap:12px;margin-top:10px;}
        .navbtn{
            flex:1;padding:15px 18px;border-radius:14px;border:1px solid var(--red);
            background:linear-gradient(135deg,rgba(255,26,60,0.25),rgba(90,5,15,0.35));
            color:#ffd9de;font-weight:700;letter-spacing:0.5px;cursor:pointer;
            display:flex;align-items:center;justify-content:center;gap:8px;
            box-shadow:0 0 16px rgba(255,26,60,0.35);transition:all .25s;
        }
        .navbtn:hover{box-shadow:0 0 26px rgba(255,26,60,0.6);transform:translateY(-2px);}
        .navbtn:disabled{opacity:0.25;cursor:not-allowed;box-shadow:none;transform:none;}

        /* logs */
        .logs-container{padding:20px;}
        .logs-title{display:flex;justify-content:space-between;align-items:center;color:#ffd9de;margin-bottom:14px;font-weight:700;letter-spacing:0.5px;}
        .logs-title .clearmini{background:linear-gradient(135deg,#3a3f47,#181b1f);color:#eee;border:1px solid #55595f;padding:9px 16px;border-radius:8px;cursor:pointer;font-weight:600;font-size:0.85rem;}
        #logs{
            background:#060506;color:#ff8f8f;border-radius:14px;padding:20px;height:min(52vh,420px);overflow-y:auto;
            font-family:'Courier New',monospace;font-size:0.85rem;line-height:1.65;white-space:pre-wrap;
            border:1px solid rgba(255,26,60,0.4);box-shadow:inset 0 0 30px rgba(255,26,60,0.15),0 0 18px rgba(255,26,60,0.15);
            text-shadow:0 0 6px rgba(255,26,60,0.35);
        }
        #logs::-webkit-scrollbar{width:8px;}
        #logs::-webkit-scrollbar-thumb{background:var(--red);border-radius:8px;}

        /* settings/info page */
        .info-list{list-style:none;color:#e7c8cb;font-size:0.9rem;line-height:2;}
        .info-list i{color:var(--red);width:20px;}
        .final-badge{text-align:center;padding:26px 20px;}
        .final-badge .big{font-family:'Bebas Neue',sans-serif;font-size:2.4rem;letter-spacing:2px;color:#fff;text-shadow:0 0 20px var(--red-glow);}

        @media(max-width:520px){
            .brandbar h1{font-size:2.2rem;}
            .btn{min-width:100%;}
            .stats-grid{grid-template-columns:1fr 1fr;}
        }
    </style>
</head>
<body>
    <div class="backdrop">
        <div class="smoke s1"></div>
        <div class="smoke s2"></div>
        <div class="smoke s3"></div>
        <svg viewBox="0 0 800 420" xmlns="http://www.w3.org/2000/svg">
            <path fill="#1a0306" d="M60,420 C40,300 90,260 70,190 C55,140 110,120 130,150 C145,100 190,95 205,140 C230,90 280,95 290,150 C310,110 360,120 365,170 C400,120 450,130 455,180 C480,140 530,150 530,200 C560,160 610,175 605,225 C640,200 690,215 680,260 C710,250 745,275 730,320 C750,340 745,390 720,420 Z"/>
            <circle cx="205" cy="150" r="7" fill="#ff1a3c" opacity="0.85"/>
            <circle cx="290" cy="160" r="6" fill="#ff1a3c" opacity="0.7"/>
        </svg>
        <div class="city">
            <span style="height:40%"></span><span style="height:65%"></span><span style="height:30%"></span>
            <span style="height:80%"></span><span style="height:45%"></span><span style="height:70%"></span>
            <span style="height:35%"></span><span style="height:90%"></span><span style="height:50%"></span>
            <span style="height:60%"></span><span style="height:25%"></span><span style="height:75%"></span>
            <span style="height:40%"></span><span style="height:55%"></span><span style="height:85%"></span>
        </div>
        <div class="embers" id="embers"></div>
    </div>
    <div class="lightning"></div>

    <div class="shell">
        <div class="brandbar">
            <h1><i class="fas fa-robot"></i>INSTAGRAM BOT v4.5</h1>
            <p> 👹 UNLEASH THE MONSTER — Your Instagram Chatbot That Never Sleeps</p>
        </div>

        <div class="pagedots">
            <span class="dot on" data-i="1"></span>
            <span class="dot" data-i="2"></span>
            <span class="dot" data-i="3"></span>
            <span class="dot" data-i="4"></span>
        </div>

        <form id="botForm">
        <div class="book" id="book">

            <!-- PAGE 1 -->
            <section class="page active" data-page="1">
                <div class="card logo-wrap">
                    <div class="logo-ring"><i class="fas fa-robot"></i></div>
                    <div class="tagline">✅ Admin Panel • Commands • Anti-Logout • Render Ready</div>
                </div>

                <div class="card status-bar status-stopped" id="statusBar">
                    <div class="status-item">
                        <div class="status-dot"></div>
                        <span>Status: Stopped</span>
                    </div>
                    <div class="status-item">
                        <span id="uptime">00:00:00</span>
                    </div>
                </div>

                <div class="stats-grid" id="statsGrid" style="display:none;">
                    <div class="card stat-card">
                        <div class="stat-number" id="totalWelcomed">0</div>
                        <div>Total Welcomed</div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-number" id="todayWelcomed">0</div>
                        <div>Today Welcomed</div>
                    </div>
                </div>

                <div class="card">
                    <div class="form-group">
                        <label><i class="fas fa-key"></i> Session Token <span class="req">*</span></label>
                        <input type="password" name="session" placeholder="Fresh session token" required>
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-hashtag"></i> Group IDs <span class="req">*</span></label>
                        <input type="text" name="group_ids" placeholder="1234567890,0987654321" required>
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-users-crown"></i> Admin IDs</label>
                        <input type="text" name="admin_ids" placeholder="admin1,admin2,you">
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-clock"></i> Welcome Delay (sec)</label>
                        <input type="number" name="delay" value="5" min="3" max="15">
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-sync"></i> Poll Interval <span class="hint">(25s recommended)</span></label>
                        <input type="number" name="poll" value="25" min="20" max="45">
                    </div>
                    <div class="form-group" style="margin-bottom:0;">
                        <label><i class="fas fa-comment-dots"></i> Welcome Messages <span class="req">*</span></label>
                        <textarea name="welcome">Welcome bro! 🔥
Have fun! 🎉
Enjoy group! 😊
Follow rules! 👮</textarea>
                    </div>
                </div>

                <div class="navrow">
                    <button type="button" class="navbtn" disabled><i class="fas fa-chevron-left"></i> Previous Page</button>
                    <button type="button" class="navbtn" onclick="goPage(2)">Next Page <i class="fas fa-chevron-right"></i></button>
                </div>
            </section>

            <!-- PAGE 2 -->
            <section class="page" data-page="2">
                <div class="pagehead"><span class="num">02</span><h2>Controls &amp; Commands</h2></div>

                <div class="card toggle-row" onclick="toggleCheckbox('use_custom_name')">
                    <span class="lbl"><i class="fas fa-user-tag"></i> Mention @username</span>
                    <label class="switch" onclick="event.stopPropagation()">
                        <input type="checkbox" id="use_custom_name" name="use_custom_name" value="yes" checked>
                        <span class="slider"></span>
                    </label>
                </div>
                <div class="card toggle-row" onclick="toggleCheckbox('enable_commands')">
                    <span class="lbl"><i class="fas fa-terminal"></i> Enable Commands</span>
                    <label class="switch" onclick="event.stopPropagation()">
                        <input type="checkbox" id="enable_commands" name="enable_commands" value="yes" checked>
                        <span class="slider"></span>
                    </label>
                </div>

                <div class="card admin-section">
                    <h3><i class="fas fa-crown"></i> 👑 Admin Commands</h3>
                    <div class="cmdline">
                        <strong>/spam @user message</strong> - Spam user<br>
                        <strong>/stopspam</strong> - Stop spam<br>
                        <strong>/ping, /uptime, /help</strong> - Public commands
                    </div>
                </div>

                <div class="card">
                    <div class="controls">
                        <button type="button" class="btn btn-start" onclick="startBot()">
                            <i class="fas fa-play"></i> Start Bot
                        </button>
                        <button type="button" class="btn btn-stop" onclick="stopBot()">
                            <i class="fas fa-stop"></i> Stop Bot
                        </button>
                        <button type="button" class="btn btn-clear" onclick="clearLogs()">
                            <i class="fas fa-trash"></i> Clear Logs
                        </button>
                    </div>
                </div>

                <div class="navrow">
                    <button type="button" class="navbtn" onclick="goPage(1)"><i class="fas fa-chevron-left"></i> Previous Page</button>
                    <button type="button" class="navbtn" onclick="goPage(3)">Next Page <i class="fas fa-chevron-right"></i></button>
                </div>
            </section>

            <!-- PAGE 3 -->
            <section class="page" data-page="3">
                <div class="pagehead"><span class="num">03</span><h2>Live Logs</h2></div>

                <div class="card logs-container">
                    <div class="logs-title">
                        <div><i class="fas fa-list"></i> Live Logs</div>
                        <button class="clearmini" onclick="clearLogs()">Clear</button>
                    </div>
                    <div id="logs">🚀 Premium Bot v4.5 ready! Admin features enabled ✅</div>
                </div>

                <div class="navrow">
                    <button type="button" class="navbtn" onclick="goPage(2)"><i class="fas fa-chevron-left"></i> Previous Page</button>
                    <button type="button" class="navbtn" onclick="goPage(4)">Next Page <i class="fas fa-chevron-right"></i></button>
                </div>
            </section>

            <!-- PAGE 4 -->
            <section class="page" data-page="4">
                <div class="pagehead"><span class="num">04</span><h2>Settings &amp; Status</h2></div>

                <div class="card">
                    <h3 style="color:#f5b03e;margin-bottom:14px;font-size:1rem;"><i class="fas fa-info-circle"></i> About This Build</h3>
                    <ul class="info-list">
                        <li><i class="fas fa-check"></i> ✅ Admin Panel • Commands • Anti-Logout • Render Ready</li>
                        <li><i class="fas fa-crown"></i> Admin Commands: /spam @user message, /stopspam</li>
                        <li><i class="fas fa-terminal"></i> Public Commands: /ping, /uptime, /help</li>
                    </ul>
                </div>

                <div class="card final-badge">
                    <div style="color:#d9a5ab;font-size:0.8rem;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px;">Final Status</div>
                    <div class="big" id="finalStatusText">Status: Stopped</div>
                    <div style="margin-top:10px;color:#c7a3a8;font-size:0.85rem;">Uptime <span id="finalUptime" style="color:#fff;font-weight:700;">00:00:00</span></div>
                </div>

                <div class="navrow">
                    <button type="button" class="navbtn" onclick="goPage(3)"><i class="fas fa-chevron-left"></i> Previous Page</button>
                    <button type="button" class="navbtn" disabled>Next Page <i class="fas fa-chevron-right"></i></button>
                </div>
            </section>

        </div>
        </form>
    </div>

    <script>
        // ---- embers particles (purely decorative) ----
        (function(){
            const box = document.getElementById('embers');
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
            void nextEl.offsetWidth; // reflow

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

        function toggleCheckbox(id) {
            document.getElementById(id).click();
        }
        
        async function startBot() {
            try {
                const formData = new FormData(document.getElementById('botForm'));
                const response = await fetch('/start', {method: 'POST', body: formData});
                const result = await response.json();
                alert(result.message);
                updateStatus();
            } catch (error) {
                alert('❌ Error: ' + error.message);
            }
        }
        
        async function stopBot() {
            try {
                const response = await fetch('/stop', {method: 'POST'});
                const result = await response.json();
                alert(result.message);
                updateStatus();
            } catch (error) {
                alert('❌ Error: ' + error.message);
            }
        }
        
        async function clearLogs() {
            try {
                await fetch('/clear_logs', {method: 'POST'});
                document.getElementById('logs').textContent = '🧹 Logs cleared!';
            } catch (error) {}
        }
        
        async function updateStatus() {
            try {
                const response = await fetch('/stats');
                const data = await response.json();
                document.getElementById('uptime').textContent = data.uptime;
                document.getElementById('finalUptime').textContent = data.uptime;
                
                const statusBar = document.getElementById('statusBar');
                const statusDot = statusBar.querySelector('.status-dot');
                const statusText = statusBar.querySelector('span');
                
                if (data.status === 'running') {
                    statusBar.className = 'card status-bar status-running';
                    statusDot.style.background = '#3dffa0';
                    statusText.textContent = 'Status: Running';
                    document.getElementById('finalStatusText').textContent = 'Status: Running';
                    document.getElementById('statsGrid').style.display = 'grid';
                    document.getElementById('totalWelcomed').textContent = data.total_welcomed;
                    document.getElementById('todayWelcomed').textContent = data.today_welcomed;
                } else {
                    statusBar.className = 'card status-bar status-stopped';
                    statusDot.style.background = '#ff1a3c';
                    statusText.textContent = 'Status: Stopped';
                    document.getElementById('finalStatusText').textContent = 'Status: Stopped';
                    document.getElementById('statsGrid').style.display = 'none';
                }
            } catch (error) {}
        }
        
        async function updateLogs() {
            try {
                const response = await fetch('/logs');
                const data = await response.json();
                const logsDiv = document.getElementById('logs');
                logsDiv.textContent = data.logs.join('\
');
                logsDiv.scrollTop = logsDiv.scrollHeight;
            } catch (error) {}
        }
        
        setInterval(() => {
            updateStatus();
            updateLogs();
        }, 3000);
        
        updateStatus();
        updateLogs();
    </script>
</body>
</html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log("🌟 Premium Instagram Bot v4.5 - COMPLETE!")
    log("✅ Admin IDs field ADDED!")
    log("✅ Commands 100% WORKING!")
    log("✅ Render.com ready - Copy paste karo!")
    app.run(host="0.0.0.0", port=port, debug=False)
