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
# Replaces SQLite database for simplicity as requested
IN_MEMORY_USERS = {}  # { email: {user_id, email, password, profile_data} }
IN_MEMORY_SESSIONS = {} # { session_id: {skills, score, history} }
IN_MEMORY_RESULTS = {} # { user_id: [results] }

llm = LLMEngine()

# --- AUTH ENDPOINTS ---
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
        
    if email in IN_MEMORY_USERS:
        return jsonify({'error': 'Email already exists'}), 400
        
    user_id = str(uuid.uuid4())
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    
    IN_MEMORY_USERS[email] = {
        'user_id': user_id,
        'email': email,
        'password': hashed_pw,
        'name': 'User',
        'onboarded': 0,
        'profile': {}
    }
    
    return jsonify({'message': 'User registered successfully', 'user_id': user_id})

@app.route('/api/login', methods=['POST'])
def login_api():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    user_data = IN_MEMORY_USERS.get(email)
    if not user_data or not bcrypt.check_password_hash(user_data['password'], password):
        return jsonify({'error': 'Invalid email or password'}), 401
        
    session['user_id'] = user_data['user_id']
    session['user_email'] = email
    session.permanent = True
    
    return jsonify({
        'message': 'Login successful',
        'user_id': user_data['user_id'],
        'name': user_data['name'],
        'onboarded': user_data['onboarded']
    })

@app.route('/api/profile/save', methods=['POST'])
def save_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    user_id = data.get('user_id')
    email = session.get('user_email')
    
    if email not in IN_MEMORY_USERS or IN_MEMORY_USERS[email]['user_id'] != user_id:
        return jsonify({'error': 'Forbidden'}), 403
        
    IN_MEMORY_USERS[email]['name'] = data.get('name', IN_MEMORY_USERS[email]['name'])
    IN_MEMORY_USERS[email]['profile'] = data
    IN_MEMORY_USERS[email]['photo'] = data.get('photo', IN_MEMORY_USERS[email].get('photo'))
    IN_MEMORY_USERS[email]['onboarded'] = 1
    
    return jsonify({'message': 'Profile updated successfully'})

@app.route('/api/profile/get/<user_id>', methods=['GET'])
def get_profile(user_id):
    if 'user_id' not in session or session['user_id'] != user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    email = session.get('user_email')
    user_data = IN_MEMORY_USERS.get(email)
    
    if not user_data:
        return jsonify({'error': 'Profile not found'}), 404
        
    # Merge basic info with profile dict for frontend
    profile = {
        **user_data['profile'], 
        'user_id': user_data['user_id'], 
        'email': user_data['email'], 
        'name': user_data['name'], 
        'onboarded': user_data['onboarded'],
        'photo': user_data.get('photo')
    }
    return jsonify(profile)

@app.route('/api/results/save', methods=['POST'])
def save_results():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    user_id = data.get('user_id')
    
    if user_id != session['user_id']:
         return jsonify({'error': 'Forbidden'}), 403
    
    if user_id not in IN_MEMORY_RESULTS:
        IN_MEMORY_RESULTS[user_id] = []
        
    IN_MEMORY_RESULTS[user_id].append({
        'timestamp': datetime.now().isoformat(),
        'domain': data.get('domain'),
        'score_mcq': data.get('score_mcq'),
        'score_interview': data.get('score_interview'),
        'feedback': data.get('feedback')
    })
    
    return jsonify({'message': 'Results saved'})

@app.route('/api/export/pdf', methods=['POST'])
def export_pdf():
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
    
    # User Details (if available in memory)
    email = session.get('user_email')
    user_name = "Candidate"
    if email and email in IN_MEMORY_USERS:
        user_name = IN_MEMORY_USERS[email].get('name', "Candidate")
    
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
    next_question = llm.generate_question(data['skills'], data['history'], context_to_use)
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
