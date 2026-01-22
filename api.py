from flask import Flask, request, jsonify
from flask_cors import CORS
import requests, base64, json, os, threading, time, re
from collections import OrderedDict, defaultdict
from datetime import datetime
from vercel_wsgi import handle_request

app = Flask(__name__)
CORS(app)

# ==================== CONFIG ====================
GITHUB_FILES = [
    f"https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part{i}.txt"
    for i in range(1, 40)
]

CACHE_FILE = "users_cache.json"
CACHE_TTL = 3600
API_KEY = os.environ.get("API_KEY", "vahset-secret")

# ==================== VahsetAPI ====================
class VahsetAPI:
    def __init__(self):
        self.users_data = OrderedDict()
        self.email_index = defaultdict(set)
        self.ip_index = defaultdict(set)
        self.user_id_variations = {}
        self.lock = threading.Lock()
        self._initialize_api()

    # ---------------- INIT ----------------
    def _initialize_api(self):
        if os.path.exists(CACHE_FILE):
            age = time.time() - os.path.getmtime(CACHE_FILE)
            if age > CACHE_TTL:
                self._load_all_from_github()
            else:
                self._load_cache()
        else:
            self._load_all_from_github()

    # ---------------- LOAD CACHE ----------------
    def _load_cache(self):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        with self.lock:
            self.users_data = OrderedDict(data)
            for uid, udata in self.users_data.items():
                self._index_user(uid, udata)
                self._add_user_id_variations(uid, uid)

    # ---------------- USER ID VARYASYONLARI ----------------
    def _add_user_id_variations(self, original_id, normalized_id):
        variations = [
            original_id, str(original_id),
            original_id.strip(), original_id.lower(),
            original_id.upper(),
            re.sub(r'[^0-9]', '', original_id)
        ]
        for var in variations:
            if var and var != original_id:
                self.user_id_variations[var] = original_id

    # ---------------- INDEX ----------------
    def _index_user(self, user_id, data):
        email = data.get("email", "").lower()
        ip = data.get("ip", "").lower()
        if email and email != "n/a":
            self.email_index[email].add(user_id)
        if ip and ip != "n/a":
            self.ip_index[ip].add(user_id)

    # ---------------- PARSE ----------------
    def parse_line(self, line):
        try:
            line = line.strip()
            if not line:
                return None
            if line.startswith('(') and line.endswith(')'):
                line = line[1:-1]

            parts = []
            current = ""
            in_quotes = False
            quote_char = None
            for char in line:
                if char in ("'", '"') and (not in_quotes or char == quote_char):
                    if not in_quotes:
                        quote_char = char
                        in_quotes = True
                    else:
                        in_quotes = False
                    continue
                elif char == ',' and not in_quotes:
                    parts.append(current.strip())
                    current = ""
                else:
                    current += char
            if current:
                parts.append(current.strip())
            if len(parts) < 9:
                return None

            user_id = parts[0].strip("'\"")
            encoded = parts[1].strip("'\"")
            try:
                email = base64.b64decode(encoded + "===").decode("utf-8", "ignore")
            except:
                email = encoded
            ip = parts[8].strip("'\"") if len(parts) > 8 else "N/A"
            if ip.lower() == "null":
                ip = "N/A"
            return {"user_id": user_id, "email": email, "ip": ip, "encoded": encoded}
        except:
            return None

    # ---------------- LOAD ALL FROM GITHUB ----------------
    def _load_all_from_github(self):
        all_users = OrderedDict()
        for url in GITHUB_FILES:
            try:
                r = requests.get(url, timeout=60)
                if r.status_code != 200:
                    continue
                lines = r.text.splitlines()
                for line in lines:
                    data = self.parse_line(line)
                    if not data:
                        continue
                    uid = data["user_id"]
                    data["source_file"] = url.split("/")[-1]
                    data["loaded_at"] = datetime.now().isoformat()
                    all_users[uid] = data
            except:
                continue

        with self.lock:
            self.users_data = OrderedDict()
            self.email_index = defaultdict(set)
            self.ip_index = defaultdict(set)
            self.user_id_variations = {}
            for uid, data in all_users.items():
                self.users_data[uid] = data
                self._index_user(uid, data)
                self._add_user_id_variations(uid, uid)
        self._save_cache()

    # ---------------- SAVE CACHE ----------------
    def _save_cache(self):
        with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(dict(self.users_data), f, ensure_ascii=False, indent=2)
        os.replace(CACHE_FILE + ".tmp", CACHE_FILE)

    # ---------------- GET USER ----------------
    def get_user(self, user_id):
        with self.lock:
            if user_id in self.users_data:
                return self._format_user_response(user_id, self.users_data[user_id])
            if user_id in self.user_id_variations:
                orig = self.user_id_variations[user_id]
                return self._format_user_response(orig, self.users_data[orig])
            return {"success": False, "error": "Kullanıcı bulunamadı"}

    def _format_user_response(self, user_id, data):
        return {
            "success": True,
            "user_id": user_id,
            "email": data.get("email"),
            "ip": data.get("ip"),
            "source_file": data.get("source_file"),
            "loaded_at": data.get("loaded_at"),
            "timestamp": datetime.now().isoformat()
        }

    # ---------------- SEARCH ----------------
    def search(self, query):
        query = query.lower().strip()
        result_ids = set()
        with self.lock:
            for uid in self.users_data.keys():
                if query in str(uid).lower():
                    result_ids.add(uid)
            for email, ids in self.email_index.items():
                if query in email:
                    result_ids.update(ids)
            for ip, ids in self.ip_index.items():
                if query in ip:
                    result_ids.update(ids)
        results = []
        for uid in list(result_ids)[:100]:
            data = self.users_data.get(uid)
            if data:
                results.append({
                    "user_id": uid,
                    "email": data.get("email"),
                    "ip": data.get("ip"),
                    "source_file": data.get("source_file"),
                    "loaded_at": data.get("loaded_at")
                })
        return {"success": True, "count": len(results), "results": results, "timestamp": datetime.now().isoformat()}

    # ---------------- STATS ----------------
    def get_stats(self):
        cache_age = 0
        if os.path.exists(CACHE_FILE):
            cache_age = int(time.time() - os.path.getmtime(CACHE_FILE))
        return {"success": True, "total_users": len(self.users_data), "cache_age_seconds": cache_age, "timestamp": datetime.now().isoformat()}

    # ---------------- REFRESH ----------------
    def refresh_data(self):
        return self._load_all_from_github()

# ==================== API INSTANCE ====================
api = VahsetAPI()

# ==================== ROUTES ====================
@app.route("/api/user/<user_id>")
def user_route(user_id):
    return jsonify(api.get_user(user_id))

@app.route("/api/search")
def search_route():
    q = request.args.get("q", "")
    return jsonify(api.search(q))

@app.route("/api/stats")
def stats_route():
    return jsonify(api.get_stats())

@app.route("/api/ping")
def ping_route():
    return jsonify({"success": True, "status": "active", "users": len(api.users_data), "timestamp": datetime.now().isoformat()})

@app.route("/api/refresh", methods=["POST"])
def refresh_route():
    if request.headers.get("X-API-KEY") != API_KEY:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    threading.Thread(target=api.refresh_data, daemon=True).start()
    return jsonify({"success": True, "message": "Veri yenileme arka planda başlatıldı"})

# ==================== SERVERLESS ENTRY ====================
def main(request):
    return handle_request(app, request)
