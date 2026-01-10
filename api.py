from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import base64
import json
import os
from datetime import datetime
import threading
import time
from collections import OrderedDict

app = Flask(__name__)
CORS(app)

# ==================== CONFIG ====================
GITHUB_FILES = [
    f"https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part{i}.txt"
    for i in range(1, 16)
]

CACHE_FILE = "users_cache.json"
CACHE_TTL = 500000  # 1 saat
MAX_CACHE_SIZE = 1000000

# ==================== VahsetAPI CLASS ====================
class VahsetAPI:
    def __init__(self):
        self.users_data = OrderedDict()
        self.lock = threading.Lock()
        self.file_stats = {}
        self._clean_old_cache()  # Eski cache'i temizle
        self._initialize_api()
    
    def _clean_old_cache(self):
        """Eski yanlış formatlı cache'i temizle"""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    
                # Eski format kontrolü (sadece 3 kullanıcı olan cache)
                if content and content.startswith('{'):
                    data = json.loads(content)
                    # Eski format: {"users": {...}, "file_stats": {...}}
                    if isinstance(data, dict) and "users" in data and "file_stats" in data:
                        print("⚠️  Eski formatlı cache tespit edildi, temizleniyor...")
                        os.remove(CACHE_FILE)
                        print("✅ Eski cache temizlendi")
                        return True
            except:
                pass
        return False
    
    def _initialize_api(self):
        """API'yi başlat"""
        print(f"\n{'='*60}")
        print("🚀 VAHŞET OSINT API BAŞLATILIYOR")
        print('='*60)
        
        # Önce cache'i yükle
        cache_loaded = self._load_cache_safe()
        
        if not cache_loaded or len(self.users_data) == 0:
            print("🔄 GitHub'dan veri yükleniyor...")
            self.load_from_github()
        else:
            print(f"✅ Cache'den {len(self.users_data):,} kullanıcı yüklendi")
        
        print(f"\n📊 BAŞLANGIÇ İSTATİSTİKLERİ:")
        print(f"   • Toplam kullanıcı: {len(self.users_data):,}")
        print(f"   • Cache dosyası: {CACHE_FILE}")
        
        # İlk 3 gerçek kullanıcıyı göster
        if self.users_data:
            print(f"\n🔍 İLK 3 KULLANICI:")
            count = 0
            for user_id, data in self.users_data.items():
                if count >= 3:
                    break
                if isinstance(data, dict) and 'email' in data:
                    count += 1
                    email = data.get('email', 'N/A')
                    email_preview = email[:30] + "..." if len(email) > 30 else email
                    print(f"   {count}. ID: {user_id}")
                    print(f"      Email: {email_preview}")
                    print(f"      IP: {data.get('ip', 'N/A')}")
                    print()
        
        print('='*60)
        print("✅ API HAZIR!")
        print('='*60)
    
    def _load_cache_safe(self):
        """Güvenli cache yükleme"""
        try:
            if not os.path.exists(CACHE_FILE):
                return False
            
            file_time = os.path.getmtime(CACHE_FILE)
            cache_age = time.time() - file_time
            
            if cache_age > CACHE_TTL:
                print(f"⚠️  Cache süresi dolmuş ({cache_age:.0f}s)")
                return False
            
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Cache formatını kontrol et
            if not isinstance(cache_data, dict):
                print("❌ Cache: Geçersiz format (dict değil)")
                return False
            
            # Yeni format kontrolü: direkt kullanıcı dict'i
            total_items = len(cache_data)
            
            # İlk birkaç item'ı kontrol et
            sample_items = list(cache_data.items())[:5]
            
            valid_users = 0
            for key, value in sample_items:
                if isinstance(value, dict) and 'email' in value:
                    valid_users += 1
            
            if valid_users > 0:
                # Yeni format: {user_id: {email: ..., ip: ...}}
                with self.lock:
                    self.users_data = OrderedDict(cache_data)
                print(f"✅ Yeni format cache yüklendi: {total_items:,} kullanıcı")
                return True
            else:
                print("❌ Cache: Geçerli kullanıcı verisi yok")
                return False
                
        except json.JSONDecodeError as e:
            print(f"❌ Cache JSON hatası: {e}")
            return False
        except Exception as e:
            print(f"❌ Cache yükleme hatası: {e}")
            return False
    
    def load_from_github(self):
        """GitHub'dan veri yükle"""
        print(f"\n{'='*60}")
        print("📥 GITHUB'DAN VERİ YÜKLENİYOR")
        print('='*60)
        
        all_users = OrderedDict()
        successful_files = 0
        total_users_before = len(self.users_data)
        
        for i, url in enumerate(GITHUB_FILES, 1):
            filename = url.split('/')[-1]
            print(f"\n[{i:2d}/{len(GITHUB_FILES)}] 📁 {filename}")
            
            try:
                start_time = time.time()
                response = requests.get(url, timeout=30)
                load_time = time.time() - start_time
                
                if response.status_code != 200:
                    print(f"   ❌ HTTP {response.status_code}")
                    self.file_stats[filename] = {'status': 'failed', 'error': f'HTTP {response.status_code}'}
                    continue
                
                content = response.text.strip()
                if not content:
                    print(f"   ⚠️  Boş dosya")
                    self.file_stats[filename] = {'status': 'empty'}
                    continue
                
                lines = content.split('\n')
                print(f"   📄 {len(lines):,} satır")
                
                file_users = OrderedDict()
                parsed = 0
                errors = 0
                duplicates = 0
                
                for line_num, line in enumerate(lines, 1):
                    if not line.strip():
                        continue
                    
                    user_data = self.parse_line(line)
                    if user_data:
                        user_id = user_data['user_id']
                        
                        if not user_id or user_id.lower() == 'null':
                            errors += 1
                            continue
                        
                        # Benzersizlik kontrolü
                        if user_id in all_users:
                            duplicates += 1
                            continue
                        if user_id in file_users:
                            duplicates += 1
                            continue
                        
                        file_users[user_id] = {
                            'email': user_data['email'],
                            'ip': user_data['ip'],
                            'encoded': user_data.get('encoded', ''),
                            'source_file': filename,
                            'loaded_at': datetime.now().isoformat()
                        }
                        parsed += 1
                        
                        # Progress göstergesi
                        if parsed % 10000 == 0:
                            print(f"   ⚡ {parsed:,} kullanıcı")
                    else:
                        errors += 1
                
                # Bu dosyadan kullanıcıları ana listeye ekle
                all_users.update(file_users)
                successful_files += 1
                
                # İstatistik kaydet
                self.file_stats[filename] = {
                    'status': 'success',
                    'users': parsed,
                    'errors': errors,
                    'duplicates': duplicates,
                    'load_time': round(load_time, 2),
                    'file_size': len(content)
                }
                
                print(f"   ✅ {parsed:,} kullanıcı ({duplicates:,} duplicate, {errors:,} hata)")
                print(f"   ⏱️  {load_time:.2f}s")
                
                # Her dosyadan sonra cache'i güncelle (sadece yeni eklenenler)
                if file_users:
                    self._update_cache(file_users)
                
            except requests.exceptions.Timeout:
                print(f"   ⏱️  Timeout")
                self.file_stats[filename] = {'status': 'timeout'}
            except requests.exceptions.RequestException as e:
                print(f"   🔌 {e}")
                self.file_stats[filename] = {'status': 'connection_error', 'error': str(e)}
            except Exception as e:
                print(f"   ❌ {type(e).__name__}: {str(e)[:50]}")
                self.file_stats[filename] = {'status': 'error', 'error': str(e)}
        
        # Tüm dosyalar yüklendikten sonra
        if all_users:
            with self.lock:
                # Sadece yeni kullanıcıları ekle
                for user_id, data in all_users.items():
                    if user_id not in self.users_data:
                        self.users_data[user_id] = data
            
            self._save_cache_full()
            
            new_users = len(all_users)
            total_users = len(self.users_data)
            
            print(f"\n{'='*60}")
            print(f"🎉 YÜKLEME TAMAMLANDI")
            print(f"📊 İSTATİSTİKLER:")
            print(f"   • Başarılı dosya: {successful_files}/{len(GITHUB_FILES)}")
            print(f"   • Yeni kullanıcı: {new_users:,}")
            print(f"   • Toplam kullanıcı: {total_users:,}")
            print(f"   • Önceki: {total_users_before:,}")
            print(f"   • Artış: {total_users - total_users_before:,}")
            
            # Dosya bazlı özet
            print(f"\n📋 DOSYA BAZLI ÖZET:")
            for filename, stats in self.file_stats.items():
                if stats.get('status') == 'success':
                    print(f"   ✅ {filename}: {stats.get('users', 0):,} kullanıcı")
            
            print('='*60)
            return True
        else:
            print("\n❌ Hiç kullanıcı yüklenemedi!")
            return False
    
    def parse_line(self, line):
        """Satırı parse et"""
        line = line.strip()
        
        if not line or line == '()' or line == '(),':
            return None
        
        try:
            # Parantezleri temizle
            if line.startswith('(') and line.endswith(')'):
                line = line[1:-1]
            elif line.startswith('(') and line.endswith('),'):
                line = line[1:-2]
            
            # Basit parsing
            parts = []
            current = ""
            in_quotes = False
            quote_char = None
            
            for char in line:
                if char in ("'", '"') and not in_quotes:
                    in_quotes = True
                    quote_char = char
                    current += char
                elif char == quote_char and in_quotes:
                    in_quotes = False
                    current += char
                elif char == ',' and not in_quotes:
                    parts.append(current.strip())
                    current = ""
                else:
                    current += char
            
            if current:
                parts.append(current.strip())
            
            # En az 9 parça kontrolü
            if len(parts) < 9:
                return None
            
            # Değerleri al
            user_id = parts[0].strip("'\"")
            email_encoded = parts[1].strip("'\"")
            
            if not user_id or user_id.lower() == 'null':
                return None
            
            # Email decode
            email = "N/A"
            if email_encoded and email_encoded.lower() not in ['null', '']:
                try:
                    # Base64 decode
                    decoded_bytes = base64.b64decode(email_encoded)
                    email = decoded_bytes.decode('utf-8', errors='ignore')
                    if not email.strip():
                        email = email_encoded
                except:
                    email = email_encoded
            
            # IP adresi
            ip = parts[8].strip("'\"") if len(parts) > 8 else "N/A"
            if not ip or ip.lower() == 'null':
                ip = "N/A"
            
            return {
                'user_id': user_id,
                'email': email,
                'ip': ip,
                'encoded': email_encoded
            }
            
        except Exception as e:
            # Hata durumunda None döndür
            return None
    
    def _update_cache(self, new_users):
        """Cache'i kısmi güncelle"""
        try:
            if not new_users:
                return False
            
            # Önce mevcut cache'i oku
            existing_cache = OrderedDict()
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if isinstance(existing_data, dict):
                            existing_cache = OrderedDict(existing_data)
                except:
                    pass
            
            # Yeni kullanıcıları ekle
            existing_cache.update(new_users)
            
            # Boyut kontrolü
            if len(existing_cache) > MAX_CACHE_SIZE:
                # En eski %10'u sil
                remove_count = int(MAX_CACHE_SIZE * 0.1)
                for _ in range(remove_count):
                    if existing_cache:
                        existing_cache.popitem(last=False)
            
            # Geçici dosyaya yaz
            temp_file = CACHE_FILE + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(dict(existing_cache), f, ensure_ascii=False, indent=2)
            
            # Orjinal dosyayı güncelle
            os.replace(temp_file, CACHE_FILE)
            
            print(f"   💾 Cache güncellendi: {len(new_users):,} yeni kullanıcı")
            return True
            
        except Exception as e:
            print(f"   ⚠️  Cache güncelleme hatası: {e}")
            return False
    
    def _save_cache_full(self):
        """Tam cache kaydet"""
        try:
            with self.lock:
                if not self.users_data:
                    return False
                
                save_data = dict(self.users_data)
            
            # Geçici dosyaya yaz
            temp_file = CACHE_FILE + ".full"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            # Orjinal dosyayı güncelle
            os.replace(temp_file, CACHE_FILE)
            
            print(f"\n💾 Tam cache kaydedildi: {len(save_data):,} kullanıcı")
            return True
            
        except Exception as e:
            print(f"\n❌ Cache kaydetme hatası: {e}")
            return False
    
    def get_user(self, user_id):
        """Kullanıcıyı bul"""
        if not user_id:
            return {
                'success': False,
                'error': 'Geçersiz user_id',
                'timestamp': datetime.now().isoformat()
            }
        
        user_id = str(user_id).strip()
        
        # Cache'de ara
        with self.lock:
            if user_id in self.users_data:
                data = self.users_data[user_id]
                return {
                    'success': True,
                    'user_id': user_id,
                    'email': data.get('email', 'N/A'),
                    'ip': data.get('ip', 'N/A'),
                    'source_file': data.get('source_file', 'cache'),
                    'cache_hit': True,
                    'timestamp': datetime.now().isoformat()
                }
        
        return {
            'success': False,
            'error': 'Kullanıcı bulunamadı',
            'user_id': user_id,
            'timestamp': datetime.now().isoformat()
        }
    
    def search(self, query):
        """Arama yap"""
        query = query.strip().lower()
        
        if not query or len(query) < 2:
            return {
                'success': False,
                'error': 'En az 2 karakter girin',
                'timestamp': datetime.now().isoformat()
            }
        
        results = []
        
        with self.lock:
            for user_id, data in self.users_data.items():
                try:
                    email = data.get('email', '').lower()
                    ip = data.get('ip', '').lower()
                    
                    if (query in user_id.lower() or 
                        query in email or 
                        query in ip):
                        
                        results.append({
                            'user_id': user_id,
                            'email': data.get('email', 'N/A'),
                            'ip': data.get('ip', 'N/A'),
                            'source_file': data.get('source_file', 'cache')
                        })
                        
                        if len(results) >= 100:
                            break
                except:
                    continue
        
        return {
            'success': True,
            'query': query,
            'count': len(results),
            'results': results,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_stats(self):
        """İstatistikleri getir"""
        with self.lock:
            total_users = len(self.users_data)
        
        return {
            'success': True,
            'total_users': total_users,
            'cache_file': CACHE_FILE,
            'cache_size': os.path.getsize(CACHE_FILE) if os.path.exists(CACHE_FILE) else 0,
            'cache_exists': os.path.exists(CACHE_FILE),
            'github_files': len(GITHUB_FILES),
            'file_stats': self.file_stats,
            'timestamp': datetime.now().isoformat()
        }

# ==================== API INSTANCE ====================
api = VahsetAPI()

# ==================== API ROUTES ====================
@app.route('/api/user/<string:user_id>', methods=['GET'])
def get_user_route(user_id):
    """Kullanıcı ara"""
    result = api.get_user(user_id)
    return jsonify(result), 200 if result['success'] else 404

@app.route('/api/search', methods=['GET'])
def search_route():
    """Genel arama"""
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify({
            'success': False,
            'error': 'Arama sorgusu gerekli (q parametresi)',
            'timestamp': datetime.now().isoformat()
        }), 400
    
    result = api.search(query)
    return jsonify(result)

@app.route('/api/stats', methods=['GET'])
def stats_route():
    """İstatistikler"""
    result = api.get_stats()
    return jsonify(result)

@app.route('/api/refresh', methods=['POST'])
def refresh_route():
    """Cache'i yenile"""
    try:
        print("\n🔄 Cache yenileniyor...")
        success = api.load_from_github()
        
        return jsonify({
            'success': success,
            'message': 'Cache başarıyla yenilendi' if success else 'Cache yenileme başarısız',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/ping', methods=['GET'])
def ping_route():
    """Durum kontrol"""
    with api.lock:
        total_users = len(api.users_data)
    
    return jsonify({
        'success': True,
        'message': 'Vahset OSINT API',
        'version': '4.0',
        'status': 'active',
        'users': total_users,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/debug', methods=['GET'])
def debug_route():
    """Debug bilgisi"""
    with api.lock:
        sample_users = []
        real_user_count = 0
        
        for user_id, data in api.users_data.items():
            if isinstance(data, dict) and data.get('email') != 'N/A':
                real_user_count += 1
                if len(sample_users) < 10:
                    sample_users.append({
                        'id': user_id,
                        'email': data.get('email', 'N/A')[:50],
                        'ip': data.get('ip', 'N/A'),
                        'source': data.get('source_file', 'cache')
                    })
    
    return jsonify({
        'success': True,
        'total_users': len(api.users_data),
        'real_users': real_user_count,
        'sample_users': sample_users,
        'cache_file': CACHE_FILE,
        'cache_size_kb': round(os.path.getsize(CACHE_FILE) / 1024, 1) if os.path.exists(CACHE_FILE) else 0,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/test', methods=['GET'])
def test_route():
    """Test endpoint'i"""
    # Rastgele 5 kullanıcı göster
    import random
    
    with api.lock:
        if not api.users_data:
            return jsonify({
                'success': False,
                'error': 'Henüz kullanıcı yok',
                'timestamp': datetime.now().isoformat()
            })
        
        all_user_ids = list(api.users_data.keys())
        
        # Gerçek kullanıcıları filtrele
        real_users = []
        for user_id in all_user_ids:
            data = api.users_data[user_id]
            if isinstance(data, dict) and data.get('email') != 'N/A':
                real_users.append(user_id)
        
        if len(real_users) > 5:
            test_users = random.sample(real_users, 5)
        elif real_users:
            test_users = real_users[:5]
        else:
            test_users = all_user_ids[:5]
        
        results = []
        for user_id in test_users:
            data = api.users_data[user_id]
            results.append({
                'user_id': user_id,
                'email': data.get('email', 'N/A'),
                'ip': data.get('ip', 'N/A'),
                'source': data.get('source_file', 'cache')
            })
    
    return jsonify({
        'success': True,
        'message': 'Test kullanıcıları',
        'test_users': results,
        'total_users': len(api.users_data),
        'real_users': len(real_users),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/', methods=['GET'])
def index():
    """Ana sayfa"""
    return jsonify({
        'api': 'Vahset OSINT API',
        'version': '4.0',
        'status': 'active',
        'endpoints': {
            '/api/user/{id}': 'Kullanıcı ara',
            '/api/search?q={query}': 'Genel arama',
            '/api/stats': 'İstatistikler',
            '/api/ping': 'Durum kontrol',
            '/api/refresh': 'Cache yenile (POST)',
            '/api/debug': 'Debug bilgisi',
            '/api/test': 'Test kullanıcıları'
        },
        'github': 'cappyyyyyy/apikaynak',
        'timestamp': datetime.now().isoformat()
    })

# ==================== MAIN ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print(f"\n{'⭐'*30}")
    print("🚀 VAHŞET OSINT API v4.0")
    print('⭐'*30)
    print(f"📡 Port: {port}")
    print(f"🌐 URL: http://localhost:{port}")
    print(f"🔗 API: http://localhost:{port}/api")
    print(f"📊 Kullanıcı: {len(api.users_data):,}")
    print('⭐'*30)
    print("\n📋 KULLANIM:")
    print("  1. Önce /api/test ile test kullanıcıları al")
    print("  2. Alınan user_id'ler ile /api/user/{id} kullan")
    print("  3. /api/search ile genel arama yap")
    print("  4. /api/debug ile detaylı bilgi al")
    print('⭐'*30)
    
    app.run(host='0.0.0.0', port=port, debug=False)
