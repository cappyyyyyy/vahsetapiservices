from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import base64
import json
import os
from datetime import datetime
import threading
import time
from collections import OrderedDict, defaultdict
import random

app = Flask(__name__)
CORS(app)

# ==================== CONFIG ====================
GITHUB_FILES = [
    f"https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part{i}.txt"
    for i in range(1, 16)
]

CACHE_FILE = "users_cache.json"
CACHE_TTL = 3600  # 1 saat (DÜZELTİLDİ)
MAX_CACHE_SIZE = 300000

API_KEY = os.environ.get("API_KEY", "vahset-secret")
ENABLE_DEBUG = False

# ==================== VahsetAPI ====================
class VahsetAPI:
    def __init__(self):
        self.users_data = OrderedDict()
        self.email_index = defaultdict(set)
        self.ip_index = defaultdict(set)
        self.lock = threading.Lock()
        self.file_stats = {}
        self._clean_old_cache()
        self._initialize_api()

    # ---------------- CACHE CLEAN ----------------
    def _clean_old_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content.startswith("{"):
                    data = json.loads(content)
                    if isinstance(data, dict) and "users" in data:
                        print("⚠️  Eski formatlı cache tespit edildi, siliniyor...")
                        os.remove(CACHE_FILE)
                        print("✅ Eski cache temizlendi")
            except:
                pass

    # ---------------- INIT ----------------
    def _initialize_api(self):
        print("\n" + "=" * 60)
        print("🚀 VAHŞET OSINT API BAŞLATILIYOR")
        print("=" * 60)

        if not self._load_cache_safe():
            print("🔄 Cache yok / süresi dolmuş, GitHub'dan yükleniyor...")
            self.load_from_github()
        else:
            print(f"✅ Cache yüklendi: {len(self.users_data):,} kullanıcı")

        print("\n📊 BAŞLANGIÇ İSTATİSTİKLERİ:")
        print(f"   • Toplam kullanıcı: {len(self.users_data):,}")
        print(f"   • Cache dosyası: {CACHE_FILE}")

        if self.users_data:
            print("\n🔍 İLK 3 KULLANICI:")
            for i, (uid, data) in enumerate(self.users_data.items()):
                if i >= 3:
                    break
                print(f"   {i+1}. ID: {uid}")
                print(f"      Email: {data.get('email', 'N/A')[:40]}")
                print(f"      IP: {data.get('ip', 'N/A')}")
                print()

        print("=" * 60)
        print("✅ API HAZIR!")
        print("=" * 60)

    # ---------------- INDEX ----------------
    def _index_user(self, user_id, data):
        email = data.get("email", "").lower()
        ip = data.get("ip", "").lower()
        if email and email != "n/a":
            self.email_index[email].add(user_id)
        if ip and ip != "n/a":
            self.ip_index[ip].add(user_id)

    # ---------------- LOAD CACHE ----------------
    def _load_cache_safe(self):
        if not os.path.exists(CACHE_FILE):
            return False

        age = time.time() - os.path.getmtime(CACHE_FILE)
        if age > CACHE_TTL:
            print(f"⚠️  Cache süresi dolmuş ({int(age)}s)")
            return False

        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return False

            with self.lock:
                self.users_data = OrderedDict(data)
                for uid, udata in self.users_data.items():
                    self._index_user(uid, udata)

            print(f"✅ Cache başarıyla yüklendi: {len(self.users_data):,} kullanıcı")
            return True
        except Exception as e:
            print(f"❌ Cache yükleme hatası: {e}")
            return False

    # ---------------- PARSE ----------------
    def parse_line(self, line):
        try:
            line = line.strip("(),")
            parts = [p.strip().strip("'\"") for p in line.split(",")]
            if len(parts) < 9:
                return None

            user_id = parts[0]
            encoded = parts[1]

            try:
                email = base64.b64decode(encoded + "===").decode("utf-8", "ignore")
            except:
                email = encoded

            ip = parts[8] if parts[8].lower() != "null" else "N/A"

            return {
                "user_id": user_id,
                "email": email if email else "N/A",
                "ip": ip,
                "encoded": encoded
            }
        except:
            return None

    # ---------------- GITHUB LOAD ----------------
    def load_from_github(self):
        print("\n" + "=" * 60)
        print("📥 GITHUB'DAN VERİ YÜKLENİYOR")
        print("=" * 60)

        new_users = OrderedDict()
        before = len(self.users_data)

        for i, url in enumerate(GITHUB_FILES, 1):
            filename = url.split("/")[-1]
            print(f"\n[{i:02}/{len(GITHUB_FILES)}] 📁 {filename}")

            try:
                start = time.time()
                r = requests.get(url, timeout=30)
                duration = time.time() - start

                if r.status_code != 200:
                    print(f"   ❌ HTTP {r.status_code}")
                    continue

                lines = r.text.splitlines()
                parsed = 0

                for line in lines:
                    data = self.parse_line(line)
                    if not data:
                        continue

                    uid = data["user_id"]
                    if uid in self.users_data or uid in new_users:
                        continue

                    data["source_file"] = filename
                    data["loaded_at"] = datetime.now().isoformat()
                    new_users[uid] = data
                    parsed += 1

                    if parsed % 10000 == 0:
                        print(f"   ⚡ {parsed:,} kullanıcı")

                print(f"   ✅ {parsed:,} kullanıcı")
                print(f"   ⏱️  {duration:.2f}s")

            except Exception as e:
                print(f"   ❌ Hata: {e}")

        if not new_users:
            print("\n❌ Yeni kullanıcı bulunamadı")
            return False

        with self.lock:
            for uid, data in new_users.items():
                self.users_data[uid] = data
                self._index_user(uid, data)

        self._save_cache()

        print("\n" + "=" * 60)
        print("🎉 YÜKLEME TAMAMLANDI")
        print(f"   • Yeni kullanıcı: {len(new_users):,}")
        print(f"   • Önceki: {before:,}")
        print(f"   • Toplam: {len(self.users_data):,}")
        print("=" * 60)

        return True

    # ---------------- SAVE CACHE ----------------
    def _save_cache(self):
        with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(dict(self.users_data), f, ensure_ascii=False)
        os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
        print(f"\n💾 Cache kaydedildi: {len(self.users_data):,} kullanıcı")

    # ---------------- GET USER ----------------
    def get_user(self, user_id):
        with self.lock:
            data = self.users_data.get(user_id)
            if not data:
                return {"success": False, "error": "Kullanıcı bulunamadı"}
            return {
                "success": True,
                "user_id": user_id,
                "email": data.get("email"),
                "ip": data.get("ip"),
                "source_file": data.get("source_file"),
                "timestamp": datetime.now().isoformat()
            }

    # ---------------- SEARCH ----------------
    def search(self, query):
        query = query.lower().strip()
        result_ids = set()

        with self.lock:
            if query in self.users_data:
                result_ids.add(query)

            for email, ids in self.email_index.items():
                if query in email:
                    result_ids.update(ids)
                if len(result_ids) >= 100:
                    break

            for ip, ids in self.ip_index.items():
                if query in ip:
                    result_ids.update(ids)
                if len(result_ids) >= 100:
                    break

        results = []
        for uid in list(result_ids)[:100]:
            data = self.users_data.get(uid)
            if data:
                results.append({
                    "user_id": uid,
                    "email": data.get("email"),
                    "ip": data.get("ip"),
                    "source_file": data.get("source_file")
                })

        return {
            "success": True,
            "count": len(results),
            "results": results,
            "timestamp": datetime.now().isoformat()
        }

    # ---------------- STATS ----------------
    def get_stats(self):
        return {
            "success": True,
            "total_users": len(self.users_data),
            "cache_exists": os.path.exists(CACHE_FILE),
            "timestamp": datetime.now().isoformat()
        }

# ==================== API INSTANCE ====================
api = VahsetAPI()

# ==================== ROUTES ====================
@app.route("/api/user/<user_id>")
def user_route(user_id):
    res = api.get_user(user_id)
    return jsonify(res), 200 if res["success"] else 404

@app.route("/api/search")
def search_route():
    return jsonify(api.search(request.args.get("q", "")))

@app.route("/api/stats")
def stats_route():
    return jsonify(api.get_stats())

@app.route("/api/refresh", methods=["POST"])
def refresh_route():
    if request.headers.get("X-API-KEY") != API_KEY:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    print("\n🔄 Cache yenileme ARKA PLANDA başlatıldı")
    threading.Thread(target=api.load_from_github, daemon=True).start()
    return jsonify({"success": True})

@app.route("/api/ping")
def ping():
    return jsonify({"success": True, "status": "active"})

@app.route("/")
def index():
    return jsonify({"api": "Vahset OSINT API", "version": "4.1"})

# ==================== MAIN ====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print("\n" + "⭐" * 30)
    print("🚀 VAHŞET OSINT API v4.1")
    print("⭐" * 30)
    print(f"📡 Port: {port}")
    print(f"🌐 URL: http://localhost:{port}")
    print(f"📊 Kullanıcı: {len(api.users_data):,}")
    print("⭐" * 30)

    app.run(host="0.0.0.0", port=port, debug=False)
