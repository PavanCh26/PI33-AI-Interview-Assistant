import io
import os
import uuid
import json
import requests
import webbrowser
from datetime import datetime
from dotenv import load_dotenv
from werkzeug.exceptions import HTTPException
# firebase_admin COMPLETELY REMOVED to save memory

# Removed firebase-admin SDK entirely. Using services/firebase_rest.py
from services.firebase_rest import FirebaseRest
_fb_rest = None

def get_db():
    global _fb_rest
    if _fb_rest is None:
        _fb_rest = FirebaseRest()
    return _fb_rest

from flask import Flask, render_template, request, jsonify, session, send_file, make_response
from flask_cors import CORS
from flask_bcrypt import Bcrypt

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

_llm = None
def get_llm():
    global _llm
    if _llm is None:
        from services.llm_engine import LLMEngine
        _llm = LLMEngine()
    return _llm

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
    db_conn = get_db()
    return jsonify({
        "status": "healthy",
        "database_connected": db_conn is not None
    })

# --- AUTH ENDPOINTS ---
@app.route('/api/register', methods=['POST'])
def register():
    db_conn = get_db()
    if not db_conn:
        return jsonify({'error': 'Database not initialized'}), 500
    try:
        data = request.get_json(silent=True)
        if not data: return jsonify({'error': 'Invalid JSON'}), 400
        email = data.get('email')
        password = data.get('password')
        if not email or not password: return jsonify({'error': 'Email and password required'}), 400
        
        existing = db_conn.get_document('users', email)
        if existing: return jsonify({'error': 'Email already exists'}), 400
        
        user_id = str(uuid.uuid4())
        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        user_data = {
            'user_id': user_id,
            'email': email,
            'password': hashed_pw,
            'name': 'User',
            'onboarded': 0,
            'profile': {},
            'created_at': datetime.now().isoformat()
        }
        db_conn.set_document('users', email, user_data)
        return jsonify({'message': 'User registered successfully', 'user_id': user_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/firebase', methods=['POST'])
def auth_firebase():
    db_conn = get_db()
    if not db_conn:
        return jsonify({'error': 'Database service unavailable'}), 500

    data = request.get_json(silent=True)
    if not data or 'idToken' not in data:
        return jsonify({'error': 'Missing idToken'}), 400
    
    id_token = data['idToken']
    # Verify via REST API
    try:
        decoded_token = db_conn.verify_id_token(id_token)
        if not decoded_token:
            return jsonify({'error': 'Invalid ID token'}), 401
        
        email = decoded_token.get('email')
        user_id = decoded_token.get('sub') # UID in tokeninfo
        
        if not email:
            return jsonify({'error': 'Email not found in token'}), 400

        print(f"DEBUG: Firebase Token Verified. Email: {email}", flush=True)

        # Persistence with Firestore REST
        user_data = db_conn.get_document('users', email)
        
        if not user_data:
            print(f"DEBUG: Creating new user record for {email}", flush=True)
            user_data = {
                'user_id': user_id,
                'email': email,
                'name': decoded_token.get('name', 'User'),
                'photo': decoded_token.get('picture', ''),
                'onboarded': 0,
                'profile': {},
                'created_at': datetime.now().isoformat()
            }
            db_conn.set_document('users', email, user_data)
        
        # Session management
        session['user_id'] = user_id
        session['user_email'] = email
        session.permanent = True
        
        # Flatten response for frontend
        profile = user_data.get('profile', {})
        response_data = {
            **user_data,
            **profile,
            'email': email
        }
        if 'profile' in response_data: del response_data['profile']
        if 'password' in response_data: del response_data['password']

        return jsonify(response_data)
    except Exception as e:
        print(f"DEBUG: Firebase auth exception: {type(e).__name__} - {e}", flush=True)
        return jsonify({'error': f'Firebase auth failed: {str(e)}'}), 500

@app.route('/api/login', methods=['POST'])
def login_api():
    db_conn = get_db()
    if not db_conn:
        return jsonify({'error': 'Database service unavailable'}), 500
    try:
        data = request.get_json(silent=True)
        email = data.get('email')
        password = data.get('password')
        
        user_data = db_conn.get_document('users', email)
        if not user_data or 'password' not in user_data:
            return jsonify({'error': 'Invalid email or password'}), 401
            
        if bcrypt.check_password_hash(user_data['password'], password):
            session['user_id'] = user_data['user_id']
            session['user_email'] = email
            session.permanent = True
            
            # Flatten response
            profile = user_data.get('profile', {})
            response_data = {**user_data, **profile, 'email': email}
            if 'profile' in response_data: del response_data['profile']
            if 'password' in response_data: del response_data['password']
            return jsonify(response_data)
        
        return jsonify({'error': 'Invalid email or password'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profile/save', methods=['POST'])
def save_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    db_conn = get_db()
    if not db_conn:
        return jsonify({'error': 'Database service unavailable'}), 500
        
    data = request.json
    email = session.get('user_email')
    
    current_user = db_conn.get_document('users', email)
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
        
    update_data = {
        'name': data.get('name', current_user.get('name')),
        'profile': data,
        'photo': data.get('photo', current_user.get('photo')),
        'onboarded': 1
    }
    
    # Root level fields
    for field in ['phone', 'college', 'year', 'skills']:
        if field in data: update_data[field] = data[field]
        
    db_conn.set_document('users', email, update_data)
    return jsonify({'message': 'Profile updated successfully'})

@app.route('/api/profile/get/<user_id>', methods=['GET'])
def get_profile(user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    db_conn = get_db()
    if not db_conn: return jsonify({'error': 'DB Error'}), 500
    email = session.get('user_email')
    user_data = db_conn.get_document('users', email)
    if not user_data: return jsonify({'error': 'Not found'}), 404
    profile = user_data.get('profile', {})
    response_data = {**user_data, **profile, 'email': email}
    if 'profile' in response_data: del response_data['profile']
    if 'password' in response_data: del response_data['password']
    return jsonify(response_data)

@app.route('/api/results/save', methods=['POST'])
def save_results():
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    db_conn = get_db()
    if not db_conn: return jsonify({'error': 'DB Error'}), 500
    data = request.json
    email = session.get('user_email')
    # Save as separate document in results collection indexed by email_timestamp
    doc_id = f"{email}_{int(datetime.now().timestamp())}"
    result_data = {
        'user_email': email,
        'timestamp': datetime.now().isoformat(),
        'scores': data.get('scores'),
        'responses': data.get('responses'),
        'feedback': data.get('feedback'),
        'date': datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    db_conn.set_document('results', doc_id, result_data)
    return jsonify({'message': 'Results saved successfully'})

@app.route('/api/results/get', methods=['GET'])
def get_results():
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 401
    db_conn = get_db()
    if not db_conn: return jsonify({'error': 'DB Error'}), 500
    email = session.get('user_email')
    # Custom filtering via REST requires more complex code, here we use simple list
    results = db_conn.get_collection('results', limit=20)
    user_results = [r for r in results if r.get('user_email') == email]
    return jsonify(user_results)

@app.route('/api/export/pdf', methods=['POST'])
def export_pdf():
    db_conn = get_db()
    if not db_conn:
        # Fallback for PDF if DB is down? Better to fail gracefully.
        return jsonify({'error': 'Database not initialized'}), 500
    data = request.json
    user_id = data.get('user_id')
    domain = data.get('domain', 'General')
    score_mcq = data.get('score_mcq', 0)
    score_int = data.get('score_interview', 0)
    feedback_list = data.get('feedback', [])
    
    from fpdf import FPDF
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
        user_data = db_conn.get_document('users', email)
        if user_data:
            user_name = user_data.get('name', 'Candidate')
    
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
            from services.pdf_processor import extract_text_from_pdf
            text = extract_text_from_pdf(file)
            if not text:
                 return jsonify({'error': 'Could not extract text from PDF'}), 400
                 
            skills = get_llm().extract_skills(text)
            score = get_llm().score_resume(text)
            
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
    question = get_llm().generate_question(data['skills'], data['history'], context_to_use)
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
    eval_data = get_llm().evaluate_answer(question, answer)
    feedback = eval_data.get('feedback', 'Good response.')
    rating = eval_data.get('rating', 7)
    
    data['history'].append({'q': question, 'a': answer, 'f': feedback, 'r': rating})
    
    context_to_use = data.get('context', 'Resume')
    print(f"DEBUG: submit_answer context={context_to_use}, history_len={len(data['history'])}", flush=True)
    next_question = get_llm().generate_question(data['skills'], data['history'], context_to_use)
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
