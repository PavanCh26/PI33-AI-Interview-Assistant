from flask import Flask, render_template, request, jsonify, session, send_file, make_response
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from services.pdf_processor import extract_text_from_pdf
from services.llm_engine import LLMEngine
from fpdf import FPDF
import io
import os
import uuid
import webbrowser
from datetime import datetime
from dotenv import load_dotenv
from werkzeug.exceptions import HTTPException
import firebase_admin
# firebase_admin imports moved inside functions to save memory

# Initialize Firebase Admin
db = None
def initialize_firebase():
    global db
    from firebase_admin import credentials, firestore
    if firebase_admin._apps:
        if db is None:
            try:
                db = firestore.client()
            except:
                pass
        return True
        
    print(f"DEBUG: Starting Firebase Admin initialization. Current directory: {os.getcwd()}", flush=True)
    
    try:
        # 1. Try Environment Variable string
        firebase_key_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if firebase_key_json:
            print(">>> SUCCESS: FIREBASE_SERVICE_ACCOUNT_JSON found in env.", flush=True)
            import json
            cred_dict = json.loads(firebase_key_json)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            return True

        # 2. Try Local File (Check multiple paths)
        key_filename = 'firebase-key.json'
        possible_paths = [
            key_filename,
            os.path.join(os.getcwd(), key_filename),
            os.path.join(os.path.dirname(__file__), key_filename)
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                print(f"DEBUG: Found key file at {path}", flush=True)
                cred = credentials.Certificate(path)
                firebase_admin.initialize_app(cred)
                db = firestore.client()
                return True
        
        return False
    except Exception as e:
        print(f"ERROR: Firebase initialization failed: {str(e)}", flush=True)
        return False

# Initial attempt at startup
initialize_firebase()

load_dotenv() 

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_secret_key_pi33") 
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=600,
)

# Enable CORS allowing local origins for preview.html
CORS(app, supports_credentials=True, origins=[
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:5501",
    "http://127.0.0.1:5501",
    "http://localhost:3000",
    "http://127.0.0.1:3000"
])
bcrypt = Bcrypt(app)

# --- IN-MEMORY STORAGE ---
# IN_MEMORY_USERS replaced by Firestore for persistence
IN_MEMORY_SESSIONS = {} # { session_id: {skills, score, history} }
IN_MEMORY_RESULTS = {} # { user_id: [results] }

llm = LLMEngine()

# --- GLOBAL JSON ERROR HANDLERS ---
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found", "message": str(e)}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed", "message": str(e)}), 405

@app.errorhandler(Exception)
def handle_exception(e):
    # Pass through HTTP errors if they occur
    if isinstance(e, HTTPException):
        print(f"DEBUG: HTTP Error {e.code}: {e.description}", flush=True)
        return jsonify({
            "error": getattr(e, 'name', 'HTTP Error'),
            "message": getattr(e, 'description', str(e))
        }), e.code

    # Handle all other code exceptions
    print(f"DEBUG: Unhandled Exception: {str(e)}", flush=True)
    import traceback
    traceback.print_exc()
    return jsonify({
        "error": "Internal Server Error",
        "message": str(e) or "An unexpected error occurred."
    }), 500

@app.route('/api/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "firebase_initialized": len(firebase_admin._apps) > 0,
        "database_connected": db is not None
    })

# --- AUTH ENDPOINTS ---
@app.route('/api/register', methods=['POST'])
def register():
    from firebase_admin import firestore
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    try:
        data = request.get_json(silent=True)
        if data is None:
            print("DEBUG: Register Request body is not valid JSON", flush=True)
            return jsonify({'error': 'Invalid JSON format'}), 400
            
        email = data.get('email')
        password = data.get('password')
        
        print(f"DEBUG: Register Request: {data}", flush=True)
        if not email or not password:
            print("DEBUG: Missing email or password", flush=True)
            return jsonify({'error': 'Email and password required'}), 400
    except Exception as e:
        print(f"DEBUG: Error in register: {str(e)}", flush=True)
        return jsonify({'error': 'Internal registration error'}), 500
        
    user_ref = db.collection('users').document(email)
    if user_ref.get().exists:
        print(f"DEBUG: Email {email} already exists", flush=True)
        return jsonify({'error': 'Email already exists'}), 400
        
    user_id = str(uuid.uuid4())
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    
    user_data = {
        'user_id': user_id,
        'email': email,
        'password': hashed_pw,
        'name': 'User',
        'onboarded': 0,
        'profile': {},
        'created_at': firestore.SERVER_TIMESTAMP
    }
    user_ref.set(user_data)
    
    return jsonify({'message': 'User registered successfully', 'user_id': user_id})

@app.route('/api/auth/firebase', methods=['POST'])
def auth_firebase():
    from firebase_admin import auth, firestore
    # Attempt initialization again if it previously failed (failsafe)
    if not initialize_firebase():
        files = os.listdir('.')
        return jsonify({
            'error': 'Firebase server-side SDK not initialized.',
            'debug_info': {
                'cwd': os.getcwd(),
                'files_in_root': files,
                'key_exists': os.path.exists('firebase-key.json')
            }
        }), 500

    data = request.get_json(silent=True)
    if not data or 'idToken' not in data:
        return jsonify({'error': 'Missing idToken'}), 400
    
    id_token = data.get('idToken')
    print(f"DEBUG: Verifying Firebase token: {id_token[:20]}...", flush=True)
    try:
        # Verify the ID token
        # Adding check_revoked=True to be safe
        try:
            decoded_token = auth.verify_id_token(id_token, check_revoked=True)
        except Exception as e:
            print(f"DEBUG: Primary verification failed, retrying... {e}", flush=True)
            # Re-try without revocation check as a fallback for certain environments
            decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        email = decoded_token.get('email')
        name = decoded_token.get('name', 'Google User')
        
        print(f"DEBUG: Firebase UID: {uid}, Email: {email}", flush=True)

        # Persistence with Firestore
        user_ref = db.collection('users').document(email)
        doc = user_ref.get()
        
        if not doc.exists:
            user_id = str(uuid.uuid4())
            user_data = {
                'user_id': user_id,
                'email': email,
                'firebase_uid': uid,
                'name': name,
                'onboarded': 0,
                'profile': {},
                'created_at': firestore.SERVER_TIMESTAMP
            }
            user_ref.set(user_data)
        else:
            user_data = doc.to_dict()
        
        session['user_id'] = user_data['user_id']
        session['user_email'] = email
        session.permanent = True
        
        # Flatten for frontend
        profile = user_data.get('profile', {})
        response_data = {
            **user_data,
            **profile,
            'email': email # ensure correct email
        }
        # Remove 'profile' key to avoid confusion
        if 'profile' in response_data: del response_data['profile']
        if 'password' in response_data: del response_data['password']

        return jsonify(response_data)
        
    except ValueError as ve:
        print(f"DEBUG: Firebase ValueError: {ve}", flush=True)
        return jsonify({'error': f'Invalid ID token format: {ve}'}), 401
    except Exception as e:
        print(f"DEBUG: Firebase auth exception: {type(e).__name__} - {e}", flush=True)
        return jsonify({'error': f'Firebase auth failed: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def login_api():
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    try:
        data = request.get_json(silent=True)
        if data is None:
            print("DEBUG: Login Request body is not valid JSON", flush=True)
            return jsonify({'error': 'Invalid JSON format'}), 400
            
        email = data.get('email')
        password = data.get('password')
        
        user_ref = db.collection('users').document(email)
        doc = user_ref.get()
        user_data = doc.to_dict() if doc.exists else None
        
        print(f"DEBUG: Login Attempt for {email}. Found: {user_data is not None}", flush=True)
        if not user_data or 'password' not in user_data or not bcrypt.check_password_hash(user_data['password'], password):
            print("DEBUG: Invalid credentials", flush=True)
            return jsonify({'error': 'Invalid email or password'}), 401
    except Exception as e:
        print(f"DEBUG: Error in login: {str(e)}", flush=True)
        return jsonify({'error': 'Internal login error'}), 500
        
    session['user_id'] = user_data['user_id']
    session['user_email'] = email
    session.permanent = True
    
    # Flatten for frontend
    profile = user_data.get('profile', {})
    response_data = {
        **user_data,
        **profile,
        'email': email
    }
    if 'profile' in response_data: del response_data['profile']
    if 'password' in response_data: del response_data['password']

    return jsonify(response_data)

@app.route('/api/profile/save', methods=['POST'])
def save_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    data = request.json
    user_id = data.get('user_id')
    email = session.get('user_email')
    
    user_ref = db.collection('users').document(email)
    doc = user_ref.get()
    
    if not doc.exists:
        return jsonify({'error': 'User not found'}), 404
        
    user_ref.update({
        'name': data.get('name', doc.to_dict().get('name')),
        'profile': data,
        'photo': data.get('photo', doc.to_dict().get('photo')),
        'onboarded': 1
    })
    
    # Also update root-level fields if they exist in data for easier querying/access
    root_updates = {}
    if 'phone' in data: root_updates['phone'] = data['phone']
    if 'college' in data: root_updates['college'] = data['college']
    if 'year' in data: root_updates['year'] = data['year']
    if 'skills' in data: root_updates['skills'] = data['skills']
    
    if root_updates:
        user_ref.update(root_updates)
    
    return jsonify({'message': 'Profile updated successfully'})

@app.route('/api/profile/get/<user_id>', methods=['GET'])
def get_profile(user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    
    email = session.get('user_email')
    user_ref = db.collection('users').document(email)
    doc = user_ref.get()
    
    if not doc.exists:
        return jsonify({'error': 'Profile not found'}), 404
    
    user_data = doc.to_dict()
        
    # Flatten basic info with profile dict for frontend
    profile = user_data.get('profile', {})
    response_data = {
        **user_data,
        **profile,
        'email': user_data['email']
    }
    if 'profile' in response_data: del response_data['profile']
    if 'password' in response_data: del response_data['password']

    return jsonify(response_data)

@app.route('/api/results/save', methods=['POST'])
def save_results():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    data = request.json
    user_id = data.get('user_id')
    
    email = session.get('user_email')
    user_ref = db.collection('users').document(email)
    
    result_data = {
        'timestamp': datetime.now().isoformat(),
        'scores': data.get('scores'),
        'responses': data.get('responses'),
        'feedback': data.get('feedback'),
        'date': datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    # Save to sub-collection 'results' under the user
    user_ref.collection('results').add(result_data)
    
    return jsonify({'message': 'Results saved successfully'})

@app.route('/api/results/get', methods=['GET'])
def get_results():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if not db:
        return jsonify({'error': 'Database not initialized'}), 500
    
    email = session.get('user_email')
    user_ref = db.collection('users').document(email)
    
    results = []
    # Fetch all documents in the 'results' sub-collection
    docs = user_ref.collection('results').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10).get()
    
    for doc in docs:
        res = doc.to_dict()
        res['id'] = doc.id
        results.append(res)
        
    return jsonify(results)

@app.route('/api/export/pdf', methods=['POST'])
def export_pdf():
    if not db:
        # Fallback for PDF if DB is down? Better to fail gracefully.
        return jsonify({'error': 'Database not initialized'}), 500
    data = request.json
    user_id = data.get('user_id')
    domain = data.get('domain', 'General')
    score_mcq = data.get('score_mcq', 0)
    score_int = data.get('score_interview', 0)
    feedback_list = data.get('feedback', [])
    
    # Create PDF
    pdf = FPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(99, 102, 241) # Primary color
    pdf.cell(190, 15, "Interview Performance Report", ln=True, align='C')
    pdf.ln(10)
    
    # User Details (from Firestore)
    email = session.get('user_email')
    user_name = "Candidate"
    if email:
        user_ref = db.collection('users').document(email)
        doc = user_ref.get()
        if doc.exists:
            user_name = doc.to_dict().get('name', "Candidate")
    
    pdf.set_font("Arial", 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(190, 10, f"Candidate Name: {user_name}", ln=True)
    pdf.cell(190, 10, f"Domain: {domain}", ln=True)
    pdf.cell(190, 10, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(5)
    
    # Scores
    pdf.set_fill_color(243, 244, 246)
    pdf.cell(190, 10, "Summary Scores", ln=True, fill=True)
    pdf.set_font("Arial", '', 12)
    pdf.cell(95, 10, f"Technical/MCQ Score: {score_mcq}", border=1)
    pdf.cell(95, 10, f"AI Interview Score: {score_int}/10", border=1, ln=True)
    pdf.ln(10)
    
    # Feedback Section
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(190, 10, "Interview Questions & Feedback", ln=True)
    pdf.set_font("Arial", '', 10)
    
    for item in feedback_list:
        # feedback_list is often a list of strings "Q: ... | AI Feedback: ..."
        # Or a list of dicts. Based on preview.html, it's a list of strings.
        text = str(item).encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(190, 8, text, border='B')
        pdf.ln(2)
        
    # Footer
    pdf.set_y(-30)
    pdf.set_font("Arial", 'I', 8)
    pdf.set_text_color(156, 163, 175)
    pdf.cell(190, 10, "Generated by PI33 AI-Based Interview Preparation Assistant", align='C')

    # Output to bytes
    pdf_bytes = pdf.output()
    
    # Create response
    output = io.BytesIO(pdf_bytes)
    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Interview_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

# --- ORIGINAL ENDPOINTS ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/logout', methods=['POST'])
def logout_api():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/db/download', methods=['GET'])
def download_db():
    # This endpoint is removed as the database is no longer used.
    # Returning a 404 or similar to indicate it's gone.
    return jsonify({'error': 'Database download not available (using in-memory storage)'}), 404

@app.route('/api/upload', methods=['POST'])
def upload_resume():
    # ... existing upload logic remains same but could be linked to user
    # Simplified for now
    if 'resume' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['resume']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        try:
            text = extract_text_from_pdf(file)
            if not text:
                 return jsonify({'error': 'Could not extract text from PDF'}), 400
                 
            skills = llm.extract_skills(text)
            score = llm.score_resume(text)
            
            # Save to in-memory sessions
            session_id = str(uuid.uuid4())
            IN_MEMORY_SESSIONS[session_id] = {
                'skills': skills,
                'score': score,
                'history': []
            }
            
            return jsonify({'session_id': session_id, 'skills': skills, 'score': score})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/interview/start', methods=['POST'])
def start_interview():
    data_in = request.json
    session_id = data_in.get('session_id')
    context = data_in.get('context', 'Resume') # Resume, AI, ML, HR, etc.
    
    if not session_id or session_id not in IN_MEMORY_SESSIONS:
        session_id = str(uuid.uuid4())
        IN_MEMORY_SESSIONS[session_id] = {
            'skills': ["General"],
            'score': 70,
            'history': [],
            'context': context
        }
    else:
        IN_MEMORY_SESSIONS[session_id]['context'] = context
    
    data = IN_MEMORY_SESSIONS[session_id]
    context_to_use = data.get('context', 'Resume')
    question = llm.generate_question(data['skills'], data['history'], context_to_use)
    return jsonify({'question': question, 'session_id': session_id})

@app.route('/api/interview/answer', methods=['POST'])
def submit_answer():
    data_in = request.json
    session_id = data_in.get('session_id')
    question = data_in.get('question')
    answer = data_in.get('answer')
    
    if session_id not in IN_MEMORY_SESSIONS:
        return jsonify({'error': 'Session not found'}), 404
    
    data = IN_MEMORY_SESSIONS[session_id]
    eval_data = llm.evaluate_answer(question, answer)
    feedback = eval_data.get('feedback', 'Good response.')
    rating = eval_data.get('rating', 7)
    
    data['history'].append({'q': question, 'a': answer, 'f': feedback, 'r': rating})
    
    context_to_use = data.get('context', 'Resume')
    print(f"DEBUG: submit_answer context={context_to_use}, history_len={len(data['history'])}", flush=True)
    next_question = llm.generate_question(data['skills'], data['history'], context_to_use)
    print(f"DEBUG: Generated Question: {next_question}", flush=True)
    
    return jsonify({
        'feedback': feedback,
        'rating': rating,
        'next_question': next_question
    })

if __name__ == '__main__':
    import threading

    def open_browser():
        url = "http://127.0.0.1:5000"
        
        # Try finding registered Chrome browser
        try:
            # Try 'chrome' or 'google-chrome'
            chrome_found = False
            for browser_name in ['google-chrome', 'chrome']:
                try:
                    b = webbrowser.get(browser_name)
                    b.open(url)
                    chrome_found = True
                    break
                except webbrowser.Error:
                    continue
            
            if not chrome_found:
                # Direct executable path fallback for Windows
                chrome_paths = [
                    "C:/Program Files/Google/Chrome/Application/chrome.exe",
                    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google/Chrome/Application/chrome.exe')
                ]
                for path in chrome_paths:
                    if os.path.exists(path):
                        webbrowser.get(f'"{path}" %s').open(url)
                        chrome_found = True
                        break
            
            if not chrome_found:
                # Final fallback to default browser
                webbrowser.open(url)
        except Exception as e:
            print(f"Error opening browser: {e}")

    # Only open browser on the main process startup
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        threading.Timer(2.5, open_browser).start()
            
    app.run(debug=True, port=5000)
