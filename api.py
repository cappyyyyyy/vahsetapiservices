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
import re

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
        self.user_id_variations = {}  # Farklı formatlar için
        self.lock = threading.Lock()
        self._initialize_api()

    # ---------------- INIT ----------------
    def _initialize_api(self):
        print("\n" + "=" * 60)
        print("🚀 VAHŞET OSINT API BAŞLATILIYOR")
        print("=" * 60)

        if os.path.exists(CACHE_FILE):
            age = time.time() - os.path.getmtime(CACHE_FILE)
            if age > CACHE_TTL:
                print(f"⚠️  Cache süresi dolmuş ({int(age)}s), yeniden yüklenecek")
                self._load_all_from_github()
            else:
                self._load_cache()
        else:
            print("🔄 Cache yok, GitHub'dan yükleniyor...")
            self._load_all_from_github()

        print(f"✅ API hazır: {len(self.users_data):,} kullanıcı")
        print("=" * 60)

    # ---------------- LOAD CACHE ----------------
    def _load_cache(self):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self.lock:
                self.users_data = OrderedDict(data)
                for uid, udata in self.users_data.items():
                    self._index_user(uid, udata)
                    # User ID varyasyonlarını kaydet
                    self._add_user_id_variations(uid, uid)

            print(f"✅ Cache yüklendi: {len(self.users_data):,} kullanıcı")
            # DEBUG: İlk 5 kullanıcıyı göster
            print("\n🔍 İLK 5 KULLANICI ÖRNEĞİ:")
            for i, (uid, data) in enumerate(list(self.users_data.items())[:5]):
                print(f"  {i+1}. ID: '{uid}' (tip: {type(uid)})")
                print(f"     Email: {data.get('email', 'N/A')[:30]}")
                print(f"     IP: {data.get('ip', 'N/A')}")
                print()
                
        except Exception as e:
            print(f"❌ Cache yükleme hatası: {e}")
            self._load_all_from_github()

    # ---------------- USER ID VARYASYONLARI ----------------
    def _add_user_id_variations(self, original_id, normalized_id):
        """User ID'nin farklı formatlarını kaydet"""
        variations = [
            original_id,
            str(original_id),
            original_id.strip(),
            original_id.lower(),
            original_id.upper(),
            re.sub(r'[^0-9]', '', original_id),  # Sadece sayılar
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
                
            # Parantezleri temizle
            if line.startswith('(') and line.endswith(')'):
                line = line[1:-1]
                
            # Tırnak işaretlerini dikkatli bir şekilde ayır
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

            # DEBUG için
            if len(self.users_data) < 5:
                print(f"DEBUG Parse: ID='{user_id}', Email='{email[:20]}...', IP='{ip}'")

            return {
                "user_id": user_id,
                "email": email if email else "N/A",
                "ip": ip,
                "encoded": encoded
            }
        except Exception as e:
            print(f"Parse hatası: {e}, Satır: {line[:100]}")
            return None

    # ---------------- LOAD ALL FROM GITHUB ----------------
    def _load_all_from_github(self):
        print("\n" + "=" * 60)
        print("📥 GITHUB'DAN TÜM VERİ YÜKLENİYOR")
        print("=" * 60)

        all_users = OrderedDict()
        total_lines = 0
        successful_parses = 0

        for i, url in enumerate(GITHUB_FILES, 1):
            filename = url.split("/")[-1]
            print(f"\n[{i:02}/{len(GITHUB_FILES)}] 📁 {filename}")

            try:
                start = time.time()
                r = requests.get(url, timeout=60)
                duration = time.time() - start

                if r.status_code != 200:
                    print(f"   ❌ HTTP {r.status_code}")
                    continue

                lines = r.text.splitlines()
                total_lines += len(lines)
                file_parsed = 0

                for line_num, line in enumerate(lines, 1):
                    data = self.parse_line(line)
                    if not data:
                        continue

                    uid = data["user_id"]
                    data["source_file"] = filename
                    data["loaded_at"] = datetime.now().isoformat()
                    data["line_number"] = line_num
                    
                    all_users[uid] = data
                    file_parsed += 1
                    successful_parses += 1

                    if file_parsed % 5000 == 0:
                        print(f"   ⚡ {file_parsed:,} kullanıcı")
                        
                    # DEBUG: İlk 3 kullanıcıyı göster
                    if successful_parses <= 3:
                        print(f"   DEBUG: ID='{uid}'")

                print(f"   ✅ {file_parsed:,} kullanıcı")
                print(f"   ⏱️  {duration:.2f}s")

            except Exception as e:
                print(f"   ❌ Hata: {e}")

        if not all_users:
            print("\n❌ Hiç kullanıcı bulunamadı")
            return False

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

        print("\n" + "=" * 60)
        print("🎉 TÜM VERİ YÜKLENDİ")
        print(f"   • Toplam satır: {total_lines:,}")
        print(f"   • Başarılı parse: {successful_parses:,}")
        print(f"   • Benzersiz kullanıcı: {len(self.users_data):,}")
        if total_lines > 0:
            print(f"   • Kayıp oranı: {((total_lines - successful_parses)/total_lines*100):.1f}%")
        
        # DEBUG: Örnek kullanıcıları göster
        print("\n🔍 ÖRNEK KULLANICILAR:")
        for i, (uid, data) in enumerate(list(self.users_data.items())[:3]):
            print(f"  {i+1}. ID: '{uid}'")
            print(f"     Email: {data.get('email', 'N/A')[:40]}")
            print(f"     IP: {data.get('ip', 'N/A')}")
            print(f"     File: {data.get('source_file')}")
            print()
            
        print("=" * 60)

        return True

    # ---------------- SAVE CACHE ----------------
    def _save_cache(self):
        with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(dict(self.users_data), f, ensure_ascii=False, indent=2)
        os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
        print(f"\n💾 Cache kaydedildi: {len(self.users_data):,} kullanıcı")

    # ---------------- GET USER ----------------
    def get_user(self, user_id):
        with self.lock:
            # 1. Direkt eşleşme
            if user_id in self.users_data:
                data = self.users_data[user_id]
                return self._format_user_response(user_id, data)
            
            # 2. Varyasyonlarda ara
            if user_id in self.user_id_variations:
                original_id = self.user_id_variations[user_id]
                data = self.users_data.get(original_id)
                if data:
                    return self._format_user_response(original_id, data)
            
            # 3. String varyasyonları dene
            search_variations = [
                user_id,
                str(user_id),
                user_id.strip(),
                user_id.lower(),
                user_id.upper(),
                re.sub(r'[^0-9]', '', user_id),
            ]
            
            for var in search_variations:
                if var in self.users_data:
                    data = self.users_data[var]
                    return self._format_user_response(var, data)
            
            # 4. Cache'i debug et
            print(f"\n🔍 USER ARAMA DEBUG: '{user_id}'")
            print(f"   Cache boyutu: {len(self.users_data):,}")
            print(f"   İlk 10 user_id: {list(self.users_data.keys())[:10]}")
            
            # 5. Partial match ara
            matching_ids = [uid for uid in self.users_data.keys() if user_id in str(uid)]
            if matching_ids:
                print(f"   Partial match bulundu: {matching_ids[:5]}")
                data = self.users_data[matching_ids[0]]
                return self._format_user_response(matching_ids[0], data)
            
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
            # User ID ile arama (tam ve partial)
            for uid in self.users_data.keys():
                if query in str(uid).lower():
                    result_ids.add(uid)
                if len(result_ids) >= 100:
                    break

            # Email'de arama
            for email, ids in self.email_index.items():
                if query in email:
                    result_ids.update(ids)
                if len(result_ids) >= 100:
                    break

            # IP'de arama
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
                    "source_file": data.get("source_file"),
                    "loaded_at": data.get("loaded_at")
                })

        return {
            "success": True,
            "count": len(results),
            "query": query,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }

    # ---------------- STATS ----------------
    def get_stats(self):
        cache_age = 0
        if os.path.exists(CACHE_FILE):
            cache_age = int(time.time() - os.path.getmtime(CACHE_FILE))
            
        return {
            "success": True,
            "total_users": len(self.users_data),
            "cache_age_seconds": cache_age,
            "cache_file": CACHE_FILE,
            "sample_ids": list(self.users_data.keys())[:5] if self.users_data else [],
            "timestamp": datetime.now().isoformat()
        }

    # ---------------- REFRESH ----------------
    def refresh_data(self):
        return self._load_all_from_github()

# ==================== API INSTANCE ====================
api = VahsetAPI()

# ==================== ROUTES ====================
@app.route("/api/user/<user_id>")
def user_route(user_id):
    print(f"\n📥 /api/user/{user_id} isteği geldi")
    res = api.get_user(user_id)
    print(f"📤 Yanıt: {res['success']}")
    return jsonify(res), 200 if res["success"] else 404

@app.route("/api/search")
def search_route():
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return jsonify({"success": False, "error": "En az 2 karakter girin"}), 400
    return jsonify(api.search(query))

@app.route("/api/stats")
def stats_route():
    return jsonify(api.get_stats())

@app.route("/api/refresh", methods=["POST"])
def refresh_route():
    if request.headers.get("X-API-KEY") != API_KEY:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    print("\n🔄 Tüm veri yenileme başlatıldı")
    threading.Thread(target=api.refresh_data, daemon=True).start()
    return jsonify({"success": True, "message": "Veri yenileme arka planda başlatıldı"})

@app.route("/api/debug")
def debug_route():
    """Debug endpoint: Cache içeriğini göster"""
    return jsonify({
        "success": True,
        "total_users": len(api.users_data),
        "first_10_users": list(api.users_data.keys())[:10],
        "sample_data": {k: api.users_data[k] for k in list(api.users_data.keys())[:3]} if api.users_data else {}
    })

@app.route("/api/ping")
def ping():
    return jsonify({
        "success": True, 
        "status": "active", 
        "users": len(api.users_data),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/")
def index():
    return jsonify({
        "api": "Vahset OSINT API", 
        "version": "4.3",
        "total_users": len(api.users_data),
        "endpoints": [
            "/api/user/<user_id>",
            "/api/search?q=<query>",
            "/api/stats",
            "/api/debug",
            "/api/ping",
            "/api/refresh (POST)"
        ]
    })

# ==================== MAIN ====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print("\n" + "⭐" * 30)
    print("🚀 VAHŞET OSINT API v4.3")
    print(f"📡 Port: {port}")
    print(f"🌐 URL: http://localhost:{port}")
    print(f"📊 Kullanıcı: {len(api.users_data):,}")
    print("⭐" * 30)
    print("⚠️  DEBUG MOD: Ayrıntılı loglama aktif")
    print("⭐" * 30)

    app.run(host="0.0.0.0", port=port, debug=False)
