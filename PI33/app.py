from flask import Flask, render_template, request, jsonify, session, send_file
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from services.pdf_processor import extract_text_from_pdf
from services.llm_engine import LLMEngine
from fpdf import FPDF
import io
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv

# -------------------------------------------------
# Load environment variables
# -------------------------------------------------
load_dotenv()

app = Flask(__name__)

# -------------------------------------------------
# App Configuration
# -------------------------------------------------
app.secret_key = os.getenv("SECRET_KEY", "fallback_secret_key_pi33")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=600,
)

# -------------------------------------------------
# Enable CORS (Allow all for demo / hackathon)
# -------------------------------------------------
CORS(app, supports_credentials=True)

bcrypt = Bcrypt(app)

# -------------------------------------------------
# In-memory storage (NO database)
# -------------------------------------------------
IN_MEMORY_USERS = {}      # email -> user data
IN_MEMORY_SESSIONS = {}   # session_id -> interview data
IN_MEMORY_RESULTS = {}    # user_id -> results list

llm = LLMEngine()

# -------------------------------------------------
# AUTH ROUTES
# -------------------------------------------------
@app.route("/api/register", methods=["POST"])
def register():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    if email in IN_MEMORY_USERS:
        return jsonify({"error": "Email already exists"}), 400

    user_id = str(uuid.uuid4())
    hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")

    IN_MEMORY_USERS[email] = {
        "user_id": user_id,
        "email": email,
        "password": hashed_pw,
        "name": "User",
        "onboarded": 0,
        "profile": {}
    }

    return jsonify({"message": "User registered successfully", "user_id": user_id})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    user = IN_MEMORY_USERS.get(email)
    if not user or not bcrypt.check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    session["user_id"] = user["user_id"]
    session["user_email"] = email
    session.permanent = True

    return jsonify({
        "message": "Login successful",
        "user_id": user["user_id"],
        "name": user["name"],
        "onboarded": user["onboarded"]
    })


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

# -------------------------------------------------
# PROFILE ROUTES
# -------------------------------------------------
@app.route("/api/profile/save", methods=["POST"])
def save_profile():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    email = session.get("user_email")

    IN_MEMORY_USERS[email]["name"] = data.get("name", "User")
    IN_MEMORY_USERS[email]["profile"] = data
    IN_MEMORY_USERS[email]["onboarded"] = 1

    return jsonify({"message": "Profile updated"})


@app.route("/api/profile/get/<user_id>")
def get_profile(user_id):
    if session.get("user_id") != user_id:
        return jsonify({"error": "Unauthorized"}), 401

    email = session.get("user_email")
    user = IN_MEMORY_USERS.get(email)

    if not user:
        return jsonify({"error": "Profile not found"}), 404

    profile = {
        **user["profile"],
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user["name"],
        "onboarded": user["onboarded"]
    }
    return jsonify(profile)

# -------------------------------------------------
# RESUME UPLOAD
# -------------------------------------------------
@app.route("/api/upload", methods=["POST"])
def upload_resume():
    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["resume"]

    try:
        text = extract_text_from_pdf(file)
        skills = llm.extract_skills(text)
        score = llm.score_resume(text)

        session_id = str(uuid.uuid4())
        IN_MEMORY_SESSIONS[session_id] = {
            "skills": skills,
            "score": score,
            "history": []
        }

        return jsonify({
            "session_id": session_id,
            "skills": skills,
            "score": score
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------------------------------
# INTERVIEW ROUTES
# -------------------------------------------------
@app.route("/api/interview/start", methods=["POST"])
def start_interview():
    data = request.json
    session_id = data.get("session_id")
    context = data.get("context", "General")

    if session_id not in IN_MEMORY_SESSIONS:
        session_id = str(uuid.uuid4())
        IN_MEMORY_SESSIONS[session_id] = {
            "skills": ["General"],
            "history": [],
            "context": context
        }

    data = IN_MEMORY_SESSIONS[session_id]
    question = llm.generate_question(
        data["skills"], data["history"], context
    )

    return jsonify({"question": question, "session_id": session_id})


@app.route("/api/interview/answer", methods=["POST"])
def submit_answer():
    data = request.json
    session_id = data.get("session_id")
    question = data.get("question")
    answer = data.get("answer")

    session_data = IN_MEMORY_SESSIONS.get(session_id)
    if not session_data:
        return jsonify({"error": "Session not found"}), 404

    eval_result = llm.evaluate_answer(question, answer)
    feedback = eval_result.get("feedback", "Good answer")
    rating = eval_result.get("rating", 7)

    session_data["history"].append({
        "question": question,
        "answer": answer,
        "feedback": feedback,
        "rating": rating
    })

    next_q = llm.generate_question(
        session_data["skills"],
        session_data["history"],
        session_data.get("context", "General")
    )

    return jsonify({
        "feedback": feedback,
        "rating": rating,
        "next_question": next_q
    })

# -------------------------------------------------
# PDF EXPORT
# -------------------------------------------------
@app.route("/api/export/pdf", methods=["POST"])
def export_pdf():
    data = request.json
    domain = data.get("domain", "General")
    score_mcq = data.get("score_mcq", 0)
    score_interview = data.get("score_interview", 0)
    feedback = data.get("feedback", [])

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Interview Performance Report", ln=True, align="C")

    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 8, f"Domain: {domain}", ln=True)
    pdf.cell(0, 8, f"MCQ Score: {score_mcq}", ln=True)
    pdf.cell(0, 8, f"Interview Score: {score_interview}/10", ln=True)

    pdf.ln(5)
    for item in feedback:
        pdf.multi_cell(0, 8, str(item))

    output = io.BytesIO(pdf.output(dest="S").encode("latin-1"))
    return send_file(
        output,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="Interview_Report.pdf"
    )

# -------------------------------------------------
# FRONTEND
# -------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# -------------------------------------------------
# ENTRY POINT (LOCAL + RENDER)
# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
