from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
import os, io, re, json, hashlib, secrets

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,      # Render serves over HTTPS
    SESSION_COOKIE_HTTPONLY=True,
)
CORS(app, supports_credentials=True)

# =============================================================
#  API CREDENTIALS
#  (Azure removed — now using Google Cloud TTS, see synthesize_google)
# =============================================================

# =============================================================
#  USER DATABASE
#  admin user "pal" has unlimited=True
#  any newly registered user gets unlimited=False, limit=10
# =============================================================
# On Render the app directory is read-only; use /tmp for writable storage
# Locally it stays in the app folder
_app_dir = os.path.dirname(__file__)
_local_users = os.path.join(_app_dir, "users.json")
USERS_FILE = _local_users if os.path.exists(_app_dir) and os.access(_app_dir, os.W_OK) else "/tmp/users.json"

def load_users():
    if not os.path.exists(USERS_FILE):
        admin_pw = os.environ.get("ADMIN_PASSWORD", "pal")
        default = {
            "pal": {
                "password": hashlib.sha256(admin_pw.encode()).hexdigest(),
                "unlimited": True,
                "generations": 0
            }
        }
        save_users(default)
        return default
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# =============================================================
#  VOICE DEFINITIONS — All verified Azure Neural Indian voices
#  Confirmed voice IDs from Microsoft Azure documentation
# =============================================================
VOICES = {
    # ── ENGLISH (Indian accent) — Female ──────────────────────
    "Neerja · Female (English)":   {"lang":"en-IN","name":"en-IN-NeerjaNeural",    "style":"newscast", "gender":"F"},
    "Ananya · Female (English)":   {"lang":"en-IN","name":"en-IN-AnanyaNeural",    "style":"",         "gender":"F"},
    "Kavya · Female (English)":    {"lang":"en-IN","name":"en-IN-KavyaNeural",     "style":"",         "gender":"F"},
    # ── ENGLISH (Indian accent) — Male ────────────────────────
    "Prabhat · Male (English)":    {"lang":"en-IN","name":"en-IN-PrabhatNeural",   "style":"",         "gender":"M"},
    "Rehaan · Male (English)":     {"lang":"en-IN","name":"en-IN-RehaanNeural",    "style":"",         "gender":"M"},
    "Aarav · Male (English)":      {"lang":"en-IN","name":"en-IN-AaravNeural",     "style":"",         "gender":"M"},

    # ── HINDI — Female ─────────────────────────────────────────
    "Swara · Female (Hindi)":      {"lang":"hi-IN","name":"hi-IN-SwaraNeural",     "style":"",         "gender":"F"},
    "Madhur · Female (Hindi)":     {"lang":"hi-IN","name":"hi-IN-MadhurNeural",    "style":"",         "gender":"F"},
    "Ananya · Female (Hindi)":     {"lang":"hi-IN","name":"hi-IN-AnanyaNeural",    "style":"",         "gender":"F"},
    # ── HINDI — Male ───────────────────────────────────────────
    "Aarav · Male (Hindi)":        {"lang":"hi-IN","name":"hi-IN-AaravNeural",     "style":"",         "gender":"M"},

    # ── BENGALI (India) — Female ───────────────────────────────
    "Tanishaa · Female (Bengali)": {"lang":"bn-IN","name":"bn-IN-TanishaaNeural",  "style":"",         "gender":"F"},
    # ── BENGALI (India) — Male ─────────────────────────────────
    "Bashkar · Male (Bengali)":    {"lang":"bn-IN","name":"bn-IN-BashkarNeural",   "style":"",         "gender":"M"},

    # ── MARATHI — Female ───────────────────────────────────────
    "Aarohi · Female (Marathi)":   {"lang":"mr-IN","name":"mr-IN-AarohiNeural",    "style":"",         "gender":"F"},
    # ── MARATHI — Male ─────────────────────────────────────────
    "Manohar · Male (Marathi)":    {"lang":"mr-IN","name":"mr-IN-ManoharNeural",   "style":"",         "gender":"M"},

    # ── TELUGU — Female ────────────────────────────────────────
    "Shruti · Female (Telugu)":    {"lang":"te-IN","name":"te-IN-ShrutiNeural",    "style":"",         "gender":"F"},
    # ── TELUGU — Male ──────────────────────────────────────────
    "Mohan · Male (Telugu)":       {"lang":"te-IN","name":"te-IN-MohanNeural",     "style":"",         "gender":"M"},

    # ── TAMIL — Female ─────────────────────────────────────────
    "Pallavi · Female (Tamil)":    {"lang":"ta-IN","name":"ta-IN-PallaviNeural",   "style":"",         "gender":"F"},
    # ── TAMIL — Male ───────────────────────────────────────────
    "Valluvar · Male (Tamil)":     {"lang":"ta-IN","name":"ta-IN-ValluvarNeural",  "style":"",         "gender":"M"},

    # ── GUJARATI — Female ──────────────────────────────────────
    "Dhwani · Female (Gujarati)":  {"lang":"gu-IN","name":"gu-IN-DhwaniNeural",    "style":"",         "gender":"F"},
    # ── GUJARATI — Male ────────────────────────────────────────
    "Niranjan · Male (Gujarati)":  {"lang":"gu-IN","name":"gu-IN-NiranjanNeural",  "style":"",         "gender":"M"},

    # ── KANNADA — Female ───────────────────────────────────────
    "Sapna · Female (Kannada)":    {"lang":"kn-IN","name":"kn-IN-SapnaNeural",     "style":"",         "gender":"F"},
    # ── KANNADA — Male ─────────────────────────────────────────
    "Gagan · Male (Kannada)":      {"lang":"kn-IN","name":"kn-IN-GaganNeural",     "style":"",         "gender":"M"},

    # ── MALAYALAM — Female ─────────────────────────────────────
    "Sobhana · Female (Malayalam)":{"lang":"ml-IN","name":"ml-IN-SobhanaNeural",   "style":"",         "gender":"F"},
    # ── MALAYALAM — Male ───────────────────────────────────────
    "Midhun · Male (Malayalam)":   {"lang":"ml-IN","name":"ml-IN-MidhunNeural",    "style":"",         "gender":"M"},

    # ── PUNJABI — Female ───────────────────────────────────────
    "Preet · Female (Punjabi)":    {"lang":"pa-IN","name":"pa-IN-Chirp3-HD-Aoede",   "style":"",         "gender":"F"},
    # ── PUNJABI — Male ─────────────────────────────────────────
    "Gurpreet · Male (Punjabi)":   {"lang":"pa-IN","name":"pa-IN-Chirp3-HD-Charon",  "style":"",         "gender":"M"},
}

MAX_FREE_GENS = 10
MAX_CHARS     = 500

# =============================================================
#  PAGES
# =============================================================
@app.route("/")
def index():
    if "username" not in session:
        with open(os.path.join(os.path.dirname(__file__), "login.html"), encoding="utf-8") as f:
            return f.read()
    with open(os.path.join(os.path.dirname(__file__), "index.html"), encoding="utf-8") as f:
        return f.read()

# =============================================================
#  AUTH ROUTES
# =============================================================
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username","").strip().lower()
    password = data.get("password","")

    # Normalize phone numbers (same logic as register)
    import re as _re
    if not _re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', username):
        phone_clean = _re.sub(r'[\s\-]', '', username)
        if phone_clean.startswith('+91'): phone_clean = phone_clean[3:]
        elif phone_clean.startswith('0'): phone_clean = phone_clean[1:]
        if _re.match(r'^[6-9]\d{9}$', phone_clean):
            username = phone_clean

    users = load_users()
    if username not in users:
        return jsonify({"error": "Account not found"}), 401
    if users[username]["password"] != hash_pw(password):
        return jsonify({"error": "Wrong password"}), 401
    session["username"] = username
    session.permanent = True
    u = users[username]
    return jsonify({
        "success": True,
        "username": username,
        "unlimited": u["unlimited"],
        "generations": u["generations"]
    })

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username","").strip().lower()
    password = data.get("password","")
    if not username or not password:
        return jsonify({"error": "Email/phone and password required"}), 400

    # Normalize phone: strip spaces, hyphens, +91 prefix
    import re as _re
    phone_clean = _re.sub(r'[\s\-]', '', username)
    if phone_clean.startswith('+91'): phone_clean = phone_clean[3:]
    elif phone_clean.startswith('0'): phone_clean = phone_clean[1:]

    # Validate as email OR Indian mobile (10 digits starting 6-9)
    is_email = bool(_re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', username))
    is_phone = bool(_re.match(r'^[6-9]\d{9}$', phone_clean))

    if not (is_email or is_phone):
        return jsonify({"error": "Please enter a valid email or 10-digit Indian phone number"}), 400

    # Use normalized phone as the key if phone, else email
    if is_phone:
        username = phone_clean

    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400
    users = load_users()
    if username in users:
        return jsonify({"error": "This email/phone is already registered"}), 409
    users[username] = {
        "password":    hash_pw(password),
        "unlimited":   False,
        "generations": 0,
        "joined":      __import__('datetime').datetime.now().strftime("%d-%m-%Y %H:%M"),
        "last_active": __import__('datetime').datetime.now().strftime("%d-%m-%Y %H:%M"),
    }
    save_users(users)
    session["username"] = username
    session.permanent = True
    return jsonify({
        "success": True,
        "username": username,
        "unlimited": False,
        "generations": 0
    })

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

# =============================================================
#  ADMIN ROUTES — only accessible by "pal"
# =============================================================
def admin_required():
    if "username" not in session or session["username"] != "pal":
        return False
    return True

@app.route("/admin")
def admin_page():
    if not admin_required():
        return "Access denied", 403
    with open(os.path.join(os.path.dirname(__file__), "admin.html"), encoding="utf-8") as f:
        return f.read()

@app.route("/admin/stats")
def admin_stats():
    if not admin_required():
        return jsonify({"error": "Access denied"}), 403
    users = load_users()
    total_users = len(users)
    total_gens  = sum(u.get("generations", 0) for u in users.values())
    unlimited   = sum(1 for u in users.values() if u.get("unlimited"))
    free_users  = total_users - unlimited
    near_limit  = sum(1 for u in users.values() if not u.get("unlimited") and u.get("generations",0) >= 8)
    hit_limit   = sum(1 for u in users.values() if not u.get("unlimited") and u.get("generations",0) >= 10)
    user_list   = [
        {
            "username":    uname,
            "unlimited":   u.get("unlimited", False),
            "generations": u.get("generations", 0),
            "joined":      u.get("joined", "—"),
            "last_active": u.get("last_active", "—"),
        }
        for uname, u in users.items()
    ]
    user_list.sort(key=lambda x: x["generations"], reverse=True)
    return jsonify({
        "total_users":   total_users,
        "total_gens":    total_gens,
        "unlimited":     unlimited,
        "free_users":    free_users,
        "near_limit":    near_limit,
        "hit_limit":     hit_limit,
        "users":         user_list,
    })

@app.route("/admin/upgrade", methods=["POST"])
def admin_upgrade():
    if not admin_required():
        return jsonify({"error": "Access denied"}), 403
    data     = request.json
    username = data.get("username","").strip().lower()
    users    = load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    users[username]["unlimited"] = True
    users[username]["generations"] = 0
    save_users(users)
    return jsonify({"success": True, "message": f"{username} upgraded to unlimited"})

@app.route("/admin/downgrade", methods=["POST"])
def admin_downgrade():
    if not admin_required():
        return jsonify({"error": "Access denied"}), 403
    data     = request.json
    username = data.get("username","").strip().lower()
    users    = load_users()
    if username not in users or username == "pal":
        return jsonify({"error": "Cannot downgrade this user"}), 400
    users[username]["unlimited"] = False
    save_users(users)
    return jsonify({"success": True})

@app.route("/admin/reset_gens", methods=["POST"])
def admin_reset_gens():
    if not admin_required():
        return jsonify({"error": "Access denied"}), 403
    data     = request.json
    username = data.get("username","").strip().lower()
    users    = load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    users[username]["generations"] = 0
    save_users(users)
    return jsonify({"success": True})

@app.route("/admin/delete_user", methods=["POST"])
def admin_delete_user():
    if not admin_required():
        return jsonify({"error": "Access denied"}), 403
    data     = request.json
    username = data.get("username","").strip().lower()
    if username == "pal":
        return jsonify({"error": "Cannot delete admin"}), 400
    users = load_users()
    if username not in users:
        return jsonify({"error": "User not found"}), 404
    del users[username]
    save_users(users)
    return jsonify({"success": True})

@app.route("/me")
def me():
    if "username" not in session:
        return jsonify({"error": "Not logged in"}), 401
    users = load_users()
    u = users.get(session["username"], {})
    return jsonify({
        "username": session["username"],
        "unlimited": u.get("unlimited", False),
        "generations": u.get("generations", 0)
    })

# =============================================================
@app.route("/voices")
def get_voices():
    if "username" not in session:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify(list(VOICES.keys()))

# =============================================================
#  TRANSLATE ROUTE — Uses Google Translate free endpoint
# =============================================================
@app.route("/translate", methods=["POST"])
def translate():
    if "username" not in session:
        return jsonify({"error": "Not logged in"}), 401
    import urllib.request, urllib.parse

    data     = request.json
    text     = data.get("text","").strip()
    target   = data.get("target","hi")   # BCP-47 language code

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if len(text) > 500:
        return jsonify({"error": "Text too long"}), 400

    try:
        params  = urllib.parse.urlencode({
            "client": "gtx",
            "sl":     "auto",
            "tl":     target,
            "dt":     "t",
            "q":      text
        })
        url = f"https://translate.googleapis.com/translate_a/single?{params}"
        req = urllib.request.Request(url)
        req.add_header("User-Agent","Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=8) as r:
            import json as _json
            result = _json.loads(r.read().decode("utf-8"))
        # Google returns nested list — extract translated text
        translated = "".join(part[0] for part in result[0] if part[0])
        return jsonify({"translated": translated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =============================================================
#  GOOGLE CLOUD TTS — 1 million free characters/month forever
#  Credentials: set GOOGLE_APPLICATION_CREDENTIALS env variable
#  pointing to your rail-vani-818f97b8d62d.json file
# =============================================================

# Voice name mapping: our friendly names → confirmed Google TTS voice IDs
# All IDs verified from Google Cloud TTS official documentation
GOOGLE_VOICE_MAP = {
    # ── ENGLISH (Indian accent) ──────────────────────────────
    # en-IN WaveNet: A(F), B(M), C(M), D(F)
    "Neerja · Female (English)":   {"language_code":"en-IN","name":"en-IN-Wavenet-D","gender":"FEMALE"},
    "Ananya · Female (English)":   {"language_code":"en-IN","name":"en-IN-Wavenet-A","gender":"FEMALE"},
    "Kavya · Female (English)":    {"language_code":"en-IN","name":"en-IN-Standard-D","gender":"FEMALE"},
    "Prabhat · Male (English)":    {"language_code":"en-IN","name":"en-IN-Wavenet-B","gender":"MALE"},
    "Rehaan · Male (English)":     {"language_code":"en-IN","name":"en-IN-Wavenet-C","gender":"MALE"},
    "Aarav · Male (English)":      {"language_code":"en-IN","name":"en-IN-Standard-B","gender":"MALE"},

    # ── HINDI ─────────────────────────────────────────────────
    # hi-IN WaveNet: A(F), B(M), C(M), D(F)
    "Swara · Female (Hindi)":      {"language_code":"hi-IN","name":"hi-IN-Wavenet-A","gender":"FEMALE"},
    "Madhur · Female (Hindi)":     {"language_code":"hi-IN","name":"hi-IN-Wavenet-D","gender":"FEMALE"},
    "Ananya · Female (Hindi)":     {"language_code":"hi-IN","name":"hi-IN-Standard-A","gender":"FEMALE"},
    "Aarav · Male (Hindi)":        {"language_code":"hi-IN","name":"hi-IN-Wavenet-B","gender":"MALE"},

    # ── BENGALI ───────────────────────────────────────────────
    # bn-IN WaveNet: A(F), B(M)
    "Tanishaa · Female (Bengali)": {"language_code":"bn-IN","name":"bn-IN-Wavenet-A","gender":"FEMALE"},
    "Bashkar · Male (Bengali)":    {"language_code":"bn-IN","name":"bn-IN-Wavenet-B","gender":"MALE"},

    # ── MARATHI ───────────────────────────────────────────────
    # mr-IN WaveNet: A(F), B(M) — only 2 voices available from Google
    "Aarohi · Female (Marathi)":   {"language_code":"mr-IN","name":"mr-IN-Wavenet-A","gender":"FEMALE"},
    "Manohar · Male (Marathi)":    {"language_code":"mr-IN","name":"mr-IN-Wavenet-B","gender":"MALE"},

    # ── TELUGU ────────────────────────────────────────────────
    # te-IN: Standard only (no WaveNet available)
    "Shruti · Female (Telugu)":    {"language_code":"te-IN","name":"te-IN-Standard-A","gender":"FEMALE"},
    "Mohan · Male (Telugu)":       {"language_code":"te-IN","name":"te-IN-Standard-B","gender":"MALE"},

    # ── TAMIL ─────────────────────────────────────────────────
    # ta-IN WaveNet: A(F), B(M), C(F), D(M)
    "Pallavi · Female (Tamil)":    {"language_code":"ta-IN","name":"ta-IN-Wavenet-A","gender":"FEMALE"},
    "Valluvar · Male (Tamil)":     {"language_code":"ta-IN","name":"ta-IN-Wavenet-B","gender":"MALE"},

    # ── GUJARATI ──────────────────────────────────────────────
    # gu-IN WaveNet: A(F), B(M)
    "Dhwani · Female (Gujarati)":  {"language_code":"gu-IN","name":"gu-IN-Wavenet-A","gender":"FEMALE"},
    "Niranjan · Male (Gujarati)":  {"language_code":"gu-IN","name":"gu-IN-Wavenet-B","gender":"MALE"},

    # ── KANNADA ───────────────────────────────────────────────
    # kn-IN WaveNet: A(F), B(M)
    "Sapna · Female (Kannada)":    {"language_code":"kn-IN","name":"kn-IN-Wavenet-A","gender":"FEMALE"},
    "Gagan · Male (Kannada)":      {"language_code":"kn-IN","name":"kn-IN-Wavenet-B","gender":"MALE"},

    # ── MALAYALAM ─────────────────────────────────────────────
    # ml-IN WaveNet: A(F), B(M)
    "Sobhana · Female (Malayalam)":{"language_code":"ml-IN","name":"ml-IN-Wavenet-A","gender":"FEMALE"},
    "Midhun · Male (Malayalam)":   {"language_code":"ml-IN","name":"ml-IN-Wavenet-B","gender":"MALE"},

    # ── PUNJABI ───────────────────────────────────────────────
    # pa-IN: Chirp 3 HD (Preview) — uses different voice name format
    "Preet · Female (Punjabi)":    {"language_code":"pa-IN","name":"pa-IN-Chirp3-HD-Aoede",  "gender":"FEMALE","chirp3":True},
    "Gurpreet · Male (Punjabi)":   {"language_code":"pa-IN","name":"pa-IN-Chirp3-HD-Charon", "gender":"MALE",  "chirp3":True},
}

def synthesize_google(voice_key, text, speed, pitch, volume, pause_style, sample_rate, voice_style=""):
    from google.cloud import texttospeech

    # On Render: load credentials from environment variable
    import json as _json
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        import tempfile
        creds_dict = _json.loads(creds_json)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            _json.dump(creds_dict, tmp)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name

    gv = GOOGLE_VOICE_MAP.get(voice_key)
    if not gv:
        # Fallback to first English voice
        gv = {"language_code":"en-IN","name":"en-IN-Wavenet-D","gender":"FEMALE"}

    # ── MOOD — prosody via SSML (works on all Google voices) ──
    effective_style = voice_style or ""

    # Base prosody from sliders
    speed_rate = speed          # Google uses float multiplier
    pitch_st   = pitch          # semitones
    vol_db     = volume         # dB

    # Mood overrides
    MOOD_MAP = {
        "":                       (speed,      pitch,      volume),
        "cheerful":               (speed+0.15, pitch+2.0,  volume+2.0),
        "sad":                    (speed-0.15, pitch-2.0,  volume-1.5),
        "excited":                (speed+0.20, pitch+3.0,  volume+3.0),
        "friendly":               (speed+0.05, pitch+1.5,  volume+1.0),
        "hopeful":                (speed+0.05, pitch+2.0,  volume+1.0),
        "shouting":               (speed+0.10, pitch+1.5,  volume+4.0),
        "whispering":             (speed-0.10, pitch-1.0,  volume-4.0),
        "terrified":              (speed+0.25, pitch+4.0,  volume+2.0),
        "unfriendly":             (speed-0.05, pitch-1.5,  volume+1.0),
        "newscast":               (speed+0.05, pitch+0.0,  volume+2.0),
        "customerservice":        (speed+0.08, pitch+1.5,  volume+1.0),
        "narration-professional": (speed-0.08, pitch-0.5,  volume+0.0),
        "sports-commentary":      (speed+0.30, pitch+3.0,  volume+4.0),
    }
    sp, pt, vl = MOOD_MAP.get(effective_style, MOOD_MAP[""])
    sp = max(0.25, min(4.0, sp))
    pt = max(-20.0, min(20.0, pt))
    vl = max(-96.0, min(16.0, vl))

    # Build SSML with pause breaks
    pause_ms  = {1:"100ms", 2:"300ms", 3:"600ms"}[pause_style]
    sentences = re.split(r'(?<=[।\.?!।])\s*', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    # Add extra dramatic pauses for certain moods
    if effective_style in ("terrified", "sad", "narration-professional"):
        body = f'<break time="400ms"/>'.join(sentences)
    else:
        body = f'<break time="{pause_ms}"/>'.join(sentences) if len(sentences)>1 else text

    ssml_text = f"<speak>{body}</speak>"

    client = texttospeech.TextToSpeechClient()

    gender_map = {"FEMALE": texttospeech.SsmlVoiceGender.FEMALE,
                  "MALE":   texttospeech.SsmlVoiceGender.MALE}

    voice = texttospeech.VoiceSelectionParams(
        language_code=gv["language_code"],
        name=gv["name"],
        ssml_gender=gender_map.get(gv["gender"], texttospeech.SsmlVoiceGender.FEMALE),
    )

    # Chirp 3 HD voices do NOT support SSML or prosody params
    if gv.get("chirp3"):
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
        )
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=voice,
            audio_config=audio_config,
        )
    else:
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            speaking_rate=sp,
            pitch=pt,
            volume_gain_db=vl,
            sample_rate_hertz=sample_rate,
        )
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml_text),
            voice=voice,
            audio_config=audio_config,
        )
    return io.BytesIO(response.audio_content)

# =============================================================
#  PREVIEW ROUTE — does NOT count against generation limit
# =============================================================

# Fixed short sample sentences per language
PREVIEW_TEXTS = {
    "en-IN": "Hello! This is how I sound. I hope you like my voice.",
    "hi-IN": "नमस्ते! मेरी आवाज़ ऐसी है। मुझे उम्मीद है आपको पसंद आएगी।",
    "bn-IN": "নমস্কার! এটি আমার কণ্ঠস্বর। আশা করি আপনার ভালো লাগবে।",
    "mr-IN": "नमस्कार! माझा आवाज असा आहे। मला आशा आहे की तुम्हाला आवडेल।",
    "te-IN": "నమస్కారం! ఇది నా గొంతు. మీకు నచ్చుతుందని ఆశిస్తున్నాను.",
    "ta-IN": "வணக்கம்! இது என் குரல். உங்களுக்கு பிடிக்கும் என்று நம்புகிறேன்।",
    "gu-IN": "નમસ્તે! આ મારો અવાજ છે। મને આશા છે કે તમને ગમશે।",
    "kn-IN": "ನಮಸ್ಕಾರ! ಇದು ನನ್ನ ಧ್ವನಿ. ನಿಮಗೆ ಇಷ್ಟವಾಗುತ್ತದೆ ಎಂದು ಆಶಿಸುತ್ತೇನೆ।",
    "pa-IN": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਇਹ ਮੇਰੀ ਆਵਾਜ਼ ਹੈ। ਮੈਨੂੰ ਉਮੀਦ ਹੈ ਕਿ ਤੁਹਾਨੂੰ ਪਸੰਦ ਆਵੇਗੀ।",
    "ml-IN": "നമസ്കാരം! ഇത് എന്റെ ശബ്ദമാണ്. നിങ്ങൾക്ക് ഇഷ്ടപ്പെടുമെന്ന് പ്രതീക്ഷിക്കുന്നു.",
    
}

@app.route("/preview", methods=["POST"])
def preview():
    if "username" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data       = request.json
    voice_name = data.get("voice","")
    voice_cfg  = VOICES.get(voice_name)
    if not voice_cfg:
        return jsonify({"error": "Invalid voice"}), 400

    # Pick sample text based on voice language
    sample_text = PREVIEW_TEXTS.get(voice_cfg["lang"], PREVIEW_TEXTS["en-IN"])

    try:
        wav_buf = synthesize_google(voice_name, sample_text, 1.0, 0.0, 0.0, 2, 24000)
        wav_buf.seek(0)
        return send_file(wav_buf, mimetype="audio/wav", as_attachment=False, download_name="preview.wav")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =============================================================
@app.route("/synthesize", methods=["POST"])
def synthesize():
    # Auth check
    if "username" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data        = request.json
    text        = data.get("text","").strip()
    voice_name  = data.get("voice", list(VOICES.keys())[0])
    speed       = float(data.get("speed",     1.0))
    pitch       = float(data.get("pitch",     0.0))
    volume      = float(data.get("volume",    0.0))
    pause_style = int(data.get("pauseStyle",  2))
    sample_rate = int(data.get("sampleRate",  24000))
    fmt         = data.get("format","wav").lower()
    voice_style = data.get("voiceStyle","")   # e.g. "cheerful", "sad", "excited"

    if not text:
        return jsonify({"error": "No text provided"}), 400
    if len(text) > MAX_CHARS:
        return jsonify({"error": f"Text too long. Max {MAX_CHARS} characters."}), 400

    voice_cfg = VOICES.get(voice_name)
    if not voice_cfg:
        return jsonify({"error": "Invalid voice"}), 400

    # Generation limit check
    users    = load_users()
    username = session["username"]
    user     = users[username]

    if not user["unlimited"] and user["generations"] >= MAX_FREE_GENS:
        return jsonify({"error": "limit_reached", "message": "Free limit reached. Upgrade to continue."}), 403

    try:
        wav_buf = synthesize_google(voice_name, text, speed, pitch, volume, pause_style, sample_rate, voice_style)

        # Increment counter after success
        users[username]["generations"] += 1
        users[username]["last_active"] = __import__('datetime').datetime.now().strftime("%d-%m-%Y %H:%M")
        save_users(users)

        if fmt == "mp3":
            from pydub import AudioSegment
            wav_buf.seek(0)
            audio  = AudioSegment.from_wav(wav_buf)
            mp3buf = io.BytesIO()
            audio.export(mp3buf, format="mp3", bitrate="192k")
            mp3buf.seek(0)
            return send_file(mp3buf, mimetype="audio/mpeg", as_attachment=True, download_name="output.mp3")
        else:
            wav_buf.seek(0)
            return send_file(wav_buf, mimetype="audio/wav", as_attachment=True, download_name="output.wav")

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    load_users()  # ensure users.json exists on startup
    print("\n✅  textTOvoice — http://127.0.0.1:5000")
    print("🎙️  Engine: Google Cloud TTS (1M free chars/month)")
    print("🔑  Admin login: username=pal  password=pal  (unlimited)")
    print("👥  New signups: 10 free generations then upgrade wall\n")
    app.run(debug=True, port=5000)
