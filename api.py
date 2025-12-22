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
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part1.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part2.txt", 
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part3.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part4.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part5.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part6.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part7.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part8.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part9.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part10.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part11.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part12.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part13.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part14.txt",
        "https://raw.githubusercontent.com/cappyyyyyy/vahset/main/data_part15.txt" 
    
      
]

CACHE_FILE = "users_cache.json"
CACHE_TTL = 3600
MAX_CACHE_SIZE = 1000000

# ==================== VahsetAPI CLASS ====================
class VahsetAPI:
    def __init__(self):
        self.users_data = OrderedDict()
        self.lock = threading.Lock()
        self.load_cache()
    
    def load_cache(self):
        try:
            if os.path.exists(CACHE_FILE):
                file_time = os.path.getmtime(CACHE_FILE)
                if time.time() - file_time < CACHE_TTL:
                    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                        self.users_data = OrderedDict(json.load(f))
                    return
            
            self.load_from_github()
        except:
            self.load_from_github()
    
    def load_from_github(self):
        all_users = OrderedDict()
        
        for url in GITHUB_FILES:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    for line in response.text.strip().split('\n'):
                        data = self.parse_line(line)
                        if data:
                            all_users[data['user_id']] = {
                                'email': data['email'],
                                'ip': data['ip'],
                                'encoded': data.get('encoded', '')
                            }
            except:
                continue
        
        with self.lock:
            self.users_data = all_users
        
        self.save_cache()
    
    def parse_line(self, line):
        line = line.strip()
        if not line or not line.startswith('('):
            return None
        
        if line.endswith('),'):
            line = line[:-1]
        
        if line.startswith('(') and line.endswith(')'):
            line = line[1:-1]
            
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
            
            if len(values) >= 9:
                user_id = values[0].strip("'\"")
                email_encoded = values[1].strip("'\"")
                email = "N/A"
                
                if email_encoded and email_encoded.lower() not in ['null', '']:
                    try:
                        decoded = base64.b64decode(email_encoded).decode('utf-8', errors='ignore')
                        email = decoded
                    except:
                        email = email_encoded
                
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
    
    def save_cache(self):
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(dict(self.users_data), f, ensure_ascii=False)
        except:
            pass
    
    def get_user(self, user_id):
        user_id = str(user_id).strip()
        
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
                    'timestamp': datetime.now().isoformat()
                }
        
        for url in GITHUB_FILES:
            try:
                content = self.fetch_url(url)
                if content:
                    lines = content.strip().split('\n')
                    
                    for line in lines:
                        data = self.parse_line(line)
                        if data and data['user_id'] == user_id:
                            with self.lock:
                                self.users_data[user_id] = {
                                    'email': data['email'],
                                    'ip': data['ip'],
                                    'encoded': data.get('encoded', '')
                                }
                            
                            if len(self.users_data) > MAX_CACHE_SIZE:
                                oldest_key = next(iter(self.users_data))
                                del self.users_data[oldest_key]
                            
                            self.save_cache()
                            
                            return {
                                'success': True,
                                'user_id': user_id,
                                'email': data['email'],
                                'ip': data['ip'],
                                'encoded_email': data.get('encoded', ''),
                                'source': 'github_live',
                                'timestamp': datetime.now().isoformat()
                            }
            except:
                continue
        
        return {
            'success': False,
            'error': 'User ID not found',
            'user_id': user_id,
            'timestamp': datetime.now().isoformat()
        }
    
    def search(self, query):
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
                        'ip': data['ip']
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
        with self.lock:
            total_users = len(self.users_data)
        
        return {
            'success': True,
            'total_users': total_users,
            'timestamp': datetime.now().isoformat()
        }
    
    def bulk_search(self, user_ids):
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
    
    def fetch_url(self, url):
        try:
            response = requests.get(url, timeout=10)
            return response.text if response.status_code == 200 else None
        except:
            return None

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

@app.route('/api/ping', methods=['GET'])
def ping_route():
    return jsonify({
        'success': True,
        'message': 'Vahset OSINT API v1.0',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/', methods=['GET'])
@app.route('/api', methods=['GET'])
def api_docs():
    return jsonify({
        'api': 'Vahset OSINT API',
        'version': '1.0',
        'endpoints': [
            'GET /api/user/{id}',
            'GET /api/search?q={query}',
            'GET /api/bulk?ids={id1,id2,id3}',
            'GET /api/stats',
            'GET /api/ping'
        ]
    })

# ==================== MAIN ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
