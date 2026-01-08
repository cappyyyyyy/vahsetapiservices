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
import concurrent.futures
from typing import Dict, List, Optional, Any

app = Flask(__name__)
CORS(app)

# ==================== CONFIG ====================
GITHUB_FILES = [
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part1.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part2.txt", 
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part3.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part4.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part5.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part6.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part7.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part8.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part9.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part10.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part11.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part12.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part13.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part14.txt",
    "https://raw.githubusercontent.com/cappyyyyyy/apikaynak/main/data_part15.txt" 
]

CACHE_FILE = "users_cache.json"
CACHE_TTL = 3600  # 1 saat
MAX_CACHE_SIZE = 1000000

# ==================== VahsetAPI CLASS ====================
class VahsetAPI:
    def __init__(self):
        self.users_data = OrderedDict()
        self.lock = threading.Lock()
        self.file_stats = {}  # Dosya istatistiklerini tut
        self.load_cache()
    
    def load_cache(self):
        """Cache dosyasını yükle ve terminalde göster"""
        try:
            if os.path.exists(CACHE_FILE):
                file_time = os.path.getmtime(CACHE_FILE)
                cache_age = time.time() - file_time
                
                if cache_age < CACHE_TTL:
                    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                        self.users_data = OrderedDict(json.load(f))
                    
                    print(f"\n{'='*60}")
                    print(f"📂 CACHE DOSYASI YÜKLENDİ")
                    print(f"{'='*60}")
                    print(f"📊 Toplam Kullanıcı: {len(self.users_data):,}")
                    print(f"⏰ Cache Yaşı: {cache_age:.0f} saniye")
                    
                    # Cache'den örnek kullanıcıları göster
                    if self.users_data:
                        print(f"\n🔍 Cache'den Örnek Kullanıcılar:")
                        count = 0
                        for user_id, data in list(self.users_data.items())[:5]:  # İlk 5 kullanıcı
                            count += 1
                            print(f"  {count}. ID: {user_id}")
                            print(f"     Email: {data['email'][:30]}..." if len(data['email']) > 30 else f"     Email: {data['email']}")
                            print(f"     IP: {data['ip']}")
                            print()
                    
                    print(f"{'='*60}")
                    return True
                else:
                    print(f"⚠️ Cache süresi doldu ({cache_age:.0f}s), GitHub'dan yeniden yükleniyor...")
                    return self.load_from_github()
            else:
                print("⚠️ Cache dosyası bulunamadı, GitHub'dan yükleniyor...")
                return self.load_from_github()
                
        except json.JSONDecodeError as e:
            print(f"❌ Cache dosyası bozuk: {e}")
            print("GitHub'dan yeniden yükleniyor...")
            return self.load_from_github()
        except Exception as e:
            print(f"❌ Cache yükleme hatası: {e}")
            return self.load_from_github()
    
    def load_from_github(self):
        """GitHub'dan tüm dosyaları teker teker yükle"""
        print(f"\n{'='*60}")
        print(f"🚀 GİTHUB'DAN VERİ YÜKLENİYOR")
        print(f"{'='*60}")
        
        all_users = OrderedDict()
        total_users_loaded = 0
        successful_files = 0
        
        # Her dosya için teker teker işlem
        for i, url in enumerate(GITHUB_FILES, 1):
            filename = url.split('/')[-1]
            
            print(f"\n📁 [{i}/{len(GITHUB_FILES)}] {filename} yükleniyor...")
            print(f"   🔗 URL: {url}")
            
            try:
                # Dosyayı indir
                start_time = time.time()
                response = requests.get(url, timeout=30)
                load_time = time.time() - start_time
                
                if response.status_code == 200:
                    content = response.text.strip()
                    file_size_kb = len(content) / 1024
                    
                    print(f"   ✅ Bağlantı başarılı")
                    print(f"   📏 Dosya Boyutu: {file_size_kb:.1f} KB")
                    print(f"   ⏱️  Yükleme Süresi: {load_time:.2f} saniye")
                    
                    # Satırları parse et
                    lines = content.split('\n')
                    print(f"   📄 Toplam Satır: {len(lines):,}")
                    
                    users_from_file = OrderedDict()
                    parsed_count = 0
                    error_count = 0
                    
                    for line_num, line in enumerate(lines, 1):
                        try:
                            data = self.parse_line(line)
                            if data:
                                user_id = data['user_id']
                                
                                # Sadece benzersiz kullanıcıları ekle
                                if user_id not in all_users and user_id not in users_from_file:
                                    users_from_file[user_id] = {
                                        'email': data['email'],
                                        'ip': data['ip'],
                                        'encoded': data.get('encoded', ''),
                                        'source_file': filename
                                    }
                                    parsed_count += 1
                                    
                                    # Her 1000 kullanıcıda bir progress göster
                                    if parsed_count % 1000 == 0:
                                        print(f"   ⚡ {parsed_count:,} kullanıcı parse edildi...")
                            else:
                                error_count += 1
                                
                        except Exception as e:
                            error_count += 1
                            # İlk 3 parse hatasını göster
                            if error_count <= 3:
                                print(f"   ⚠️ Satır {line_num} parse hatası: {str(e)[:50]}...")
                    
                    # Bu dosyadan yüklenen kullanıcıları ana listeye ekle
                    all_users.update(users_from_file)
                    total_users_loaded += parsed_count
                    successful_files += 1
                    
                    # Bu dosya için istatistikleri kaydet
                    self.file_stats[filename] = {
                        'status': 'success',
                        'users_loaded': parsed_count,
                        'errors': error_count,
                        'load_time': load_time,
                        'file_size_kb': file_size_kb
                    }
                    
                    # Terminalde bu dosya için özet
                    print(f"\n   📊 {filename} ÖZET:")
                    print(f"   ├─ Başarılı: {parsed_count:,} kullanıcı")
                    print(f"   ├─ Hatalı: {error_count:,} satır")
                    print(f"   ├─ Benzersiz: {len(users_from_file):,} kullanıcı")
                    print(f"   └─ Toplam: {len(all_users):,} kullanıcı (tüm dosyalar)")
                    
                    # Her dosyadan sonra cache'e kaydet
                    self.save_to_cache(all_users)
                    
                    # Bu dosyadan örnek kullanıcıları göster
                    if users_from_file:
                        sample_users = list(users_from_file.items())[:3]
                        print(f"\n   🔍 {filename}'den Örnek Kullanıcılar:")
                        for j, (user_id, data) in enumerate(sample_users, 1):
                            print(f"   {j}. ID: {user_id}")
                            email_preview = data['email'][:25] + "..." if len(data['email']) > 25 else data['email']
                            print(f"      Email: {email_preview}")
                            print(f"      IP: {data['ip']}")
                    
                else:
                    print(f"   ❌ HTTP Hatası: {response.status_code}")
                    self.file_stats[filename] = {
                        'status': 'failed',
                        'error_code': response.status_code
                    }
                    
            except requests.exceptions.Timeout:
                print(f"   ⏱️  Timeout - Dosya yüklenemedi")
                self.file_stats[filename] = {'status': 'timeout'}
            except requests.exceptions.ConnectionError:
                print(f"   🔌 Bağlantı Hatası - İnternet bağlantısını kontrol edin")
                self.file_stats[filename] = {'status': 'connection_error'}
            except Exception as e:
                print(f"   ❌ Beklenmeyen Hata: {type(e).__name__}: {str(e)[:50]}")
                self.file_stats[filename] = {'status': 'error', 'error': str(e)[:100]}
        
        # Tüm dosyalar yüklendikten sonra final cache kaydet
        with self.lock:
            self.users_data = all_users
        
        self.save_cache()
        
        # Final özet
        print(f"\n{'='*60}")
        print(f"🎉 VERİ YÜKLEME TAMAMLANDI")
        print(f"{'='*60}")
        print(f"📈 GENEL İSTATİSTİKLER:")
        print(f"   ├─ Başarılı Dosya: {successful_files}/{len(GITHUB_FILES)}")
        print(f"   ├─ Toplam Kullanıcı: {len(all_users):,}")
        print(f"   └─ Cache Dosyası: {CACHE_FILE}")
        
        # Dosya bazlı istatistikler
        print(f"\n📋 DOSYA BAZLI İSTATİSTİKLER:")
        for filename, stats in self.file_stats.items():
            if stats['status'] == 'success':
                print(f"   ✅ {filename}:")
                print(f"      ├─ Kullanıcı: {stats['users_loaded']:,}")
                print(f"      ├─ Hata: {stats['errors']:,}")
                print(f"      ├─ Boyut: {stats['file_size_kb']:.1f} KB")
                print(f"      └─ Süre: {stats['load_time']:.2f}s")
            else:
                print(f"   ❌ {filename}: {stats['status']}")
        
        # Örnek kullanıcıları göster
        if all_users:
            print(f"\n🔍 SİSTEMDEN ÖRNEK KULLANICILAR:")
            sample_users = list(all_users.items())[:10]
            for i, (user_id, data) in enumerate(sample_users, 1):
                print(f"   {i}. ID: {user_id}")
                email_preview = data['email'][:30] + "..." if len(data['email']) > 30 else data['email']
                print(f"      Email: {email_preview}")
                print(f"      IP: {data['ip']}")
                print(f"      Kaynak: {data.get('source_file', 'cache')}")
                print()
        
        print(f"{'='*60}")
        print(f"✅ API Hazır! http://localhost:5000/api adresinden erişebilirsiniz.")
        print(f"{'='*60}")
        
        return successful_files > 0
    
    def save_to_cache(self, users_data):
        """Ara cache kaydetme (her dosya yüklendikten sonra)"""
        try:
            temp_file = CACHE_FILE + ".temp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(dict(users_data), f, ensure_ascii=False, indent=2)
            
            # Başarılı olursa orijinal dosyayı güncelle
            os.replace(temp_file, CACHE_FILE)
            
            print(f"   💾 Ara cache kaydedildi: {len(users_data):,} kullanıcı")
            return True
            
        except Exception as e:
            print(f"   ⚠️ Ara cache kaydetme hatası: {e}")
            return False
    
    def save_cache(self):
        """Final cache kaydetme"""
        try:
            with self.lock:
                users_to_save = dict(self.users_data)
            
            temp_file = CACHE_FILE + ".final"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(users_to_save, f, ensure_ascii=False, indent=2)
            
            os.replace(temp_file, CACHE_FILE)
            
            print(f"✅ Final cache kaydedildi: {len(users_to_save):,} kullanıcı")
            return True
            
        except Exception as e:
            print(f"❌ Cache kaydetme hatası: {e}")
            return False
    
    def parse_line(self, line):
        """Satırı parse et"""
        line = line.strip()
        if not line or not line.startswith('('):
            return None
        
        try:
            # Sonunda varsa virgülü kaldır
            if line.endswith('),'):
                line = line[:-1]
            
            # Parantezleri kaldır
            if line.startswith('(') and line.endswith(')'):
                line = line[1:-1]
                
                # CSV parsing
                values = []
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
                        values.append(current.strip())
                        current = ""
                    else:
                        current += char
                
                if current:
                    values.append(current.strip())
                
                # En az 9 alan olmalı
                if len(values) >= 9:
                    user_id = values[0].strip("'\"")
                    email_encoded = values[1].strip("'\"")
                    email = "N/A"
                    
                    # Email decode
                    if email_encoded and email_encoded.lower() not in ['null', '']:
                        try:
                            decoded = base64.b64decode(email_encoded).decode('utf-8', errors='ignore')
                            email = decoded
                        except:
                            email = email_encoded
                    
                    # IP adresi (9. alan)
                    ip = values[8].strip("'\"") if len(values) > 8 else "N/A"
                    if ip.lower() in ['null', '']:
                        ip = "N/A"
                    
                    return {
                        'user_id': user_id,
                        'email': email,
                        'ip': ip,
                        'encoded': email_encoded
                    }
            
            return None
            
        except Exception as e:
            return None
    
    def get_user(self, user_id):
        """Kullanıcıyı bul"""
        user_id = str(user_id).strip()
        
        # Önce cache'de ara
        with self.lock:
            if user_id in self.users_data:
                data = self.users_data[user_id]
                return {
                    'success': True,
                    'user_id': user_id,
                    'email': data['email'],
                    'ip': data['ip'],
                    'encoded_email': data.get('encoded', ''),
                    'source': 'cache',
                    'source_file': data.get('source_file', 'cache'),
                    'timestamp': datetime.now().isoformat()
                }
        
        # Cache'de yoksa GitHub'dan canlı ara
        print(f"\n🔍 Canlı arama: {user_id}")
        
        for url in GITHUB_FILES:
            try:
                filename = url.split('/')[-1]
                print(f"  📁 {filename} kontrol ediliyor...")
                
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    lines = response.text.strip().split('\n')
                    
                    for line in lines:
                        data = self.parse_line(line)
                        if data and data['user_id'] == user_id:
                            # Bulunan kullanıcıyı cache'e ekle
                            with self.lock:
                                self.users_data[user_id] = {
                                    'email': data['email'],
                                    'ip': data['ip'],
                                    'encoded': data.get('encoded', ''),
                                    'source_file': filename
                                }
                            
                            # Cache boyut kontrolü
                            if len(self.users_data) > MAX_CACHE_SIZE:
                                oldest_key = next(iter(self.users_data))
                                del self.users_data[oldest_key]
                                print(f"  🗑️  Eski cache temizlendi: {oldest_key}")
                            
                            self.save_cache()
                            print(f"  ✅ Kullanıcı bulundu ve cache'e eklendi")
                            
                            return {
                                'success': True,
                                'user_id': user_id,
                                'email': data['email'],
                                'ip': data['ip'],
                                'encoded_email': data.get('encoded', ''),
                                'source': 'github_live',
                                'source_file': filename,
                                'timestamp': datetime.now().isoformat()
                            }
            except:
                continue
        
        print(f"  ❌ Kullanıcı bulunamadı")
        return {
            'success': False,
            'error': 'User ID not found',
            'user_id': user_id,
            'timestamp': datetime.now().isoformat()
        }
    
    def search(self, query):
        """Arama yap"""
        query = query.lower().strip()
        results = []
        
        with self.lock:
            for user_id, data in self.users_data.items():
                if (query in user_id.lower() or 
                    query in data['email'].lower() or 
                    query in data['ip'].lower()):
                    results.append({
                        'user_id': user_id,
                        'email': data['email'],
                        'ip': data['ip'],
                        'source_file': data.get('source_file', 'cache')
                    })
                    
                    if len(results) >= 50:
                        break
        
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
        
        # Dosya istatistiklerini hazırla
        file_stats_summary = {}
        for filename, stats in self.file_stats.items():
            if stats['status'] == 'success':
                file_stats_summary[filename] = {
                    'users': stats.get('users_loaded', 0),
                    'errors': stats.get('errors', 0),
                    'load_time': stats.get('load_time', 0)
                }
        
        return {
            'success': True,
            'total_users': total_users,
            'cache_file': CACHE_FILE,
            'file_stats': file_stats_summary,
            'github_files': len(GITHUB_FILES),
            'timestamp': datetime.now().isoformat()
        }
    
    def bulk_search(self, user_ids):
        """Toplu arama"""
        results = []
        not_found = []
        
        with self.lock:
            for user_id in user_ids:
                user_id = str(user_id).strip()
                if user_id in self.users_data:
                    data = self.users_data[user_id]
                    results.append({
                        'user_id': user_id,
                        'email': data['email'],
                        'ip': data['ip']
                    })
                else:
                    not_found.append(user_id)
        
        return {
            'success': True,
            'found_count': len(results),
            'not_found_count': len(not_found),
            'results': results,
            'not_found': not_found,
            'timestamp': datetime.now().isoformat()
        }

# ==================== API INSTANCE ====================
api = VahsetAPI()

# ==================== API ROUTES ====================
@app.route('/api/user/<string:user_id>', methods=['GET'])
def get_user_route(user_id):
    result = api.get_user(user_id)
    return jsonify(result)

@app.route('/api/search', methods=['GET'])
def search_route():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({
            'success': False,
            'error': 'Query parameter "q" required',
            'timestamp': datetime.now().isoformat()
        })
    
    result = api.search(query)
    return jsonify(result)

@app.route('/api/bulk', methods=['GET'])
def bulk_search_route():
    ids_param = request.args.get('ids', '').strip()
    if not ids_param:
        return jsonify({
            'success': False,
            'error': 'Query parameter "ids" required',
            'timestamp': datetime.now().isoformat()
        })
    
    user_ids = [id.strip() for id in ids_param.split(',')]
    result = api.bulk_search(user_ids)
    return jsonify(result)

@app.route('/api/stats', methods=['GET'])
def stats_route():
    result = api.get_stats()
    return jsonify(result)

@app.route('/api/refresh', methods=['POST'])
def refresh_route():
    """Cache'i yeniden yükle"""
    try:
        print(f"\n🔄 Cache yeniden yükleniyor...")
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
        })

@app.route('/api/ping', methods=['GET'])
def ping_route():
    return jsonify({
        'success': True,
        'message': 'Vahset OSINT API',
        'version': '3.0',
        'status': 'active',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/', methods=['GET'])
@app.route('/api', methods=['GET'])
def api_docs():
    return jsonify({
        'api': 'Vahset OSINT API',
        'version': '3.0',
        'status': 'active',
        'endpoints': [
            'GET /api/user/{id} - Kullanıcı ara',
            'GET /api/search?q={query} - Genel arama',
            'GET /api/bulk?ids={id1,id2,id3} - Toplu arama',
            'GET /api/stats - İstatistikler',
            'POST /api/refresh - Cache yenile',
            'GET /api/ping - Durum kontrol'
        ],
        'github_repo': 'cappyyyyyy/apikaynak',
        'total_files': len(GITHUB_FILES),
        'cache_file': CACHE_FILE
    })

# ==================== MAIN ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print(f"\n{'⭐'*30}")
    print(f"🚀 VAHŞET OSINT API v3.0")
    print(f"{'⭐'*30}")
    print(f"📡 Port: {port}")
    print(f"🌐 URL: http://localhost:{port}")
    print(f"🔗 API: http://localhost:{port}/api")
    print(f"📁 GitHub: cappyyyyyy/apikaynak")
    print(f"📊 Dosya Sayısı: {len(GITHUB_FILES)}")
    print(f"💾 Cache: {CACHE_FILE}")
    print(f"{'⭐'*30}")
    
    app.run(host='0.0.0.0', port=port, debug=False)
