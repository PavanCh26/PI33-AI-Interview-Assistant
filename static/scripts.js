// --- CONFIG ---
const API_BASE = window.location.port === '5000'
    ? "/api"
    : "http://127.0.0.1:5000/api";

// --- STATE ---
let isLoginMode = true;
let user = null;
let currentStep = 1;
let mcqType = 'tech';
let mcqIdx = 0;
let scores = { tech: 0, apt: 0, domain: 0 };
let interviewPhase = 'tech';
let intIdx = 0;
let interviewRatings = [];
let recognition;
let synth = window.speechSynthesis;
let currentDomain = null;
let activeMCQQuestions = [];
let activeInterviewQuestions = { tech: [], hr: [] };
let currentSessionId = null;
let currentQuestion = "";
let interviewLimit = 5;
const feedbackLog = [];

// --- DATA POOLS ---
const questionsPool = {
    tech: [
        { q: "What is a Decorator in Python?", opts: ["A design pattern", "A function modifying another function", "A database trigger"], a: 1 },
        { q: "Difference between LIST and TUPLE?", opts: ["Mutable vs Immutable", "No difference", "List is slower"], a: 0 },
        { q: "What does SQL injection target?", opts: ["The database", "The frontend", "The network"], a: 0 },
        { q: "What is the complexity of Binary Search?", opts: ["O(n)", "O(log n)", "O(1)"], a: 1 },
        { q: "Which data structure uses LIFO?", opts: ["Queue", "Stack", "Array"], a: 1 },
        { q: "What is a REST API?", opts: ["A database", "A design style for web APIs", "A programming language"], a: 1 },
        { q: "What is Git primarily used for?", opts: ["Code compilation", "Version control", "Database management"], a: 1 },
        { q: "Explain 'Big O' notation.", opts: ["Code size", "Algorithm efficiency", "Variable naming"], a: 1 },
        { q: "What is a primary key?", opts: ["Main file", "Unique database identifier", "Security password"], a: 1 },
        { q: "Which is a frontend framework?", opts: ["Django", "React", "Flask"], a: 1 }
    ],
    apt: [
        { q: "Choose the synonym of: HAPPY", opts: ["Sad", "Joyful", "Angry"], a: 1 },
        { q: "Next number: 2, 4, 8, ...", opts: ["12", "16", "24"], a: 1 },
        { q: "Train moving at 60km/h crosses a pole in 9s. Length?", opts: ["150m", "100m", "120m"], a: 0 },
        { q: "If A is brother of B, B is sister of C...", opts: ["C is father", "C is sibling", "Unrelated"], a: 1 },
        { q: "Odd one out: 3, 5, 7, 9, 11", opts: ["9", "7", "3"], a: 0 },
        { q: "A person sells an item for $120 making 20% profit. Cost price?", opts: ["$100", "$96", "$110"], a: 0 },
        { q: "What is 15% of 200?", opts: ["25", "30", "35"], a: 1 },
        { q: "Simplify: (4 + 8) / 2 x 3", opts: ["6", "18", "12"], a: 1 }
    ],
    AI: [
        { q: "What is the goal of AI?", opts: ["To simulate human intelligence", "To build faster computers", "To store more data"], a: 0 },
        { q: "Which is a search algorithm?", opts: ["A*", "B-Tree", "QuickSort"], a: 0 },
        { q: "What is a Heuristic?", opts: ["A rule of thumb", "A precise formula", "A database key"], a: 0 },
        { q: "Turing Test evaluates?", opts: ["Machine Intelligence", "Hardware Speed", "Network Latency"], a: 0 },
        { q: "Example of Weak AI?", opts: ["Siri", "Data from Star Trek", "Skynet"], a: 0 },
        { q: "What is Natural Language Processing?", opts: ["Data compression", "Understanding human speech", "Image editing"], a: 1 },
        { q: "Which is an AI subfield?", opts: ["Cloud Computing", "Machine Learning", "Blockchain"], a: 1 }
    ],
    ML: [
        { q: "Supervised Learning requires?", opts: ["Labeled data", "Unlabeled data", "No data"], a: 0 },
        { q: "What is Overfitting?", opts: ["Model learns noise", "Model is too simple", "Data is missing"], a: 0 },
        { q: "Which is a classifier?", opts: ["SVM", "K-Means", "PCA"], a: 0 },
        { q: "What is a Neural Network?", opts: ["A physical brain", "Computational model for patterns", "Storage device"], a: 1 },
        { q: "Which is used for dimensionality reduction?", opts: ["Random Forest", "PCA", "Linear Regression"], a: 1 }
    ],
    VLSI: [
        { q: "What does VLSI stand for?", opts: ["Very Large Scale Integration", "Value Line Scale Input", "Virtual Long Scale Interface"], a: 0 },
        { q: "Which tool is for circuit simulation?", opts: ["Spice", "Photoshop", "Notepad"], a: 0 },
        { q: "What is a MOSFET?", opts: ["Type of resistor", "Field-effect transistor", "Logic gate"], a: 1 },
        { q: "Law stating transistor count doubles every 2 years?", opts: ["Moore's Law", "Newton's Law", "Ohm's Law"], a: 0 }
    ],
    Embedded: [
        { q: "What defines an Embedded System?", opts: ["Single purpose computer", "General purpose PC", "Large server"], a: 0 },
        { q: "Common Embedded language?", opts: ["C/C++", "HTML", "PHP"], a: 0 },
        { q: "What is an RTOS?", opts: ["Real-time Operating System", "Regional Task Office", "Root Task Online"], a: 0 },
        { q: "What is a Microcontroller?", opts: ["Mini computer on a chip", "Large monitor", "Storage drive"], a: 0 }
    ]
};

const interviewPool = {
    hr: [
        { q: "Tell me about a time you handled a conflict.", keywords: ["listen", "compromise", "understand", "calm"] },
        { q: "Why should we hire you?", keywords: ["passionate", "skill", "fit", "value"] },
        { q: "Where do you see yourself in 5 years?", keywords: ["growth", "learning", "lead", "expert"] }
    ]
};

const resourcesPool = {
    general: {
        low: [{ type: "YouTube", title: "Python for Beginners", color: "#ef4444", link: "https://www.youtube.com/results?search_query=python+basics+tutorial" }],
        medium: [{ type: "Practice", title: "LeetCode Easy Problems", color: "#059669", link: "https://leetcode.com/problemset/all/?difficulty=EASY" }],
        high: [{ type: "YouTube", title: "System Design for Interviews", color: "#ef4444", link: "https://www.youtube.com/results?search_query=system+design+interview" }]
    }
};

// --- UTILS ---
function getRandomSubset(arr, n) {
    if (!arr) return [];
    const shuffled = [...arr].sort(() => 0.5 - Math.random());
    return shuffled.slice(0, n);
}

// --- NAVIGATION ---
function openLogin() {
    console.log("Opening login screen...");
    const landing = document.getElementById('landing-page');
    const login = document.getElementById('login-screen');

    if (landing) landing.classList.add('hidden');
    if (login) {
        login.style.display = 'flex';
        console.log("Login screen displayed");
    } else {
        console.error("Login screen element not found!");
    }
}

function toggleAuthMode() {
    isLoginMode = !isLoginMode;
    document.getElementById('auth-title').innerText = isLoginMode ? "Welcome Back" : "Create Account";
    document.getElementById('auth-subtitle').innerText = isLoginMode ? "Sign in with email" : "Start your prep journey";
    document.getElementById('auth-btn').innerText = isLoginMode ? "Enter" : "Sign Up";
    document.getElementById('auth-toggle-text').innerText = isLoginMode ? "Don't have an account?" : "Already have an account?";
    document.getElementById('auth-toggle-btn').innerText = isLoginMode ? "Sign Up" : "Sign In";
}

async function handleAuth() {
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value.trim();

    if (!email || !password) return alert("Please fill all fields.");

    const endpoint = isLoginMode ? "/login" : "/register";
    try {
        const res = await fetch(API_BASE + endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
            credentials: 'include'
        });
        const data = await res.json();

        if (data.error) throw new Error(data.error);

        if (!isLoginMode) {
            // Silently switch to login mode after successful registration
            toggleAuthMode();
        } else {
            user = data;
            user.email = email;
            document.getElementById('login-screen').classList.add('hidden');

            if (!user.onboarded) {
                document.getElementById('onboarding-screen').style.display = 'flex';
            } else {
                const pref = await fetch(API_BASE + `/profile/get/${user.user_id}`, { credentials: 'include' });
                user = await pref.json();
                document.getElementById('main-app').classList.remove('hidden');
                updateProfileUI();
            }
        }
    } catch (err) {
        alert(err.message);
    }
}

async function handleOnboardingUpload() {
    const fileInput = document.getElementById('ob-resume');
    if (!fileInput.files.length) return;

    const formData = new FormData();
    formData.append('resume', fileInput.files[0]);

    const statusText = document.querySelector('#onboarding-screen p[style*="color: #4f46e5"]');
    const originalText = statusText ? statusText.innerText : "Uploading...";

    try {
        const res = await fetch(API_BASE + "/upload", {
            method: 'POST',
            body: formData,
            credentials: 'include'
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        currentSessionId = data.session_id;
        if (data.skills) document.getElementById('ob-skills').value = data.skills.join(', ');
        // Removed ATS score alert to reduce popups
    } catch (err) {
        alert("Upload failed: " + err.message);
    }
}

async function completeOnboarding() {
    console.log("Saving onboarding profile...");
    if (!user) {
        console.error("User state missing during onboarding!");
        return alert("Session lost. Please login again.");
    }

    const nameEl = document.getElementById('ob-name');
    const phoneEl = document.getElementById('ob-phone');
    const collegeEl = document.getElementById('ob-college');
    const yearEl = document.getElementById('ob-year');
    const skillsEl = document.getElementById('ob-skills');

    if (!nameEl) return console.error("Missing ob-name element");

    const name = nameEl.value.trim();
    if (!name) return alert("Please enter your name.");

    const profileData = {
        user_id: user.user_id,
        name: name,
        phone: phoneEl ? phoneEl.value.trim() : "",
        college: collegeEl ? collegeEl.value.trim() : "",
        year: yearEl ? (parseInt(yearEl.value) || 2024) : 2024,
        skills: skillsEl ? skillsEl.value.trim() : ""
    };

    console.log("Sending profile data:", profileData);

    try {
        const res = await fetch(API_BASE + "/profile/save", {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(profileData),
            credentials: 'include'
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        user = { ...user, ...profileData, onboarded: 1 };
        document.getElementById('onboarding-screen').style.display = 'none';
        document.getElementById('main-app').classList.remove('hidden');
        updateProfileUI();
    } catch (err) {
        alert("Failed to save profile: " + err.message);
    }
}

function updateProfileUI() {
    if (user && document.getElementById('user-display')) {
        document.getElementById('user-display').innerText = user.name;

        // Update photos
        const photoUrl = user.photo || `https://ui-avatars.com/api/?name=${encodeURIComponent(user.name)}&background=4f46e5&color=fff`;
        if (document.getElementById('user-photo')) document.getElementById('user-photo').src = photoUrl;
        if (document.getElementById('edit-photo-preview')) document.getElementById('edit-photo-preview').src = photoUrl;
    }
}

function openProfileEdit() {
    if (!user) return;
    document.getElementById('edit-name').value = user.name || "";
    document.getElementById('edit-phone').value = user.phone || "";
    document.getElementById('edit-college').value = user.college || "";
    document.getElementById('edit-year').value = user.year || 2024;
    document.getElementById('edit-skills').value = (user.skills && Array.isArray(user.skills)) ? user.skills.join(', ') : (user.skills || "");

    document.getElementById('profile-edit-modal').style.display = 'flex';
    document.getElementById('profile-menu').style.display = 'none';
}

function previewPhoto(event) {
    const reader = new FileReader();
    reader.onload = function () {
        const preview = document.getElementById('edit-photo-preview');
        preview.src = reader.result;
    }
    reader.readAsDataURL(event.target.files[0]);
}

async function savePersonalDetails() {
    const name = document.getElementById('edit-name').value.trim();
    if (!name) return alert("Name is required.");

    const photoPreview = document.getElementById('edit-photo-preview');

    const profileData = {
        user_id: user.user_id,
        name: name,
        phone: document.getElementById('edit-phone').value.trim(),
        college: document.getElementById('edit-college').value.trim(),
        year: parseInt(document.getElementById('edit-year').value) || 2024,
        skills: document.getElementById('edit-skills').value.trim(),
        photo: photoPreview.src // Base64 string
    };

    try {
        const res = await fetch(API_BASE + "/profile/save", {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(profileData),
            credentials: 'include'
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        user = { ...user, ...profileData };
        alert("Profile updated successfully!");
        closeModals();
        updateProfileUI();
    } catch (err) {
        alert("Failed to save: " + err.message);
    }
}

function toggleProfileMenu() {
    const menu = document.getElementById('profile-menu');
    if (menu) {
        if (menu.style.display === 'flex') {
            menu.style.display = 'none';
        } else {
            menu.style.display = 'flex';
        }
    }
}

async function logout() {
    if (confirm("Are you sure you want to logout?")) {
        try {
            await fetch(API_BASE + "/logout", { method: 'POST', credentials: 'include' });
        } catch (e) { }
        user = null;
        location.reload();
    }
}

// --- MODULES ---
function startModule(type) {
    document.getElementById('dashboard-home').classList.add('hidden');
    // Set limit: 2 for HR/Common, 5 for Resume
    interviewLimit = (type === 'common') ? 2 : 5;

    if (type === 'resume') {
        currentDomain = null;
        document.getElementById('int-title').innerText = "Resume Based Interview";
        if (currentSessionId) {
            setStep(2);
        } else {
            document.getElementById('main-progress').classList.remove('hidden');
            document.getElementById('step-label').style.display = 'block';
            document.getElementById('step-label').innerText = "Upload Resume";
            setStep(1);
        }
    } else if (type === 'domain') {
        document.getElementById('domain-modal').style.display = 'flex';
    } else if (type === 'common') {
        currentDomain = 'Common';
        setStep(4);
        document.getElementById('int-title').innerText = "HR & Behavioral Interview";
        document.getElementById('scrolling-chat').innerHTML = '';
        setTimeout(startAIInterview, 1000);
    }
}

function selectDomain(domain) {
    interviewLimit = 2; // Set to 2 for Domain interviews
    currentDomain = domain;
    document.querySelectorAll('.modal-overlay').forEach(m => m.style.display = 'none');
    document.getElementById('dashboard-home').classList.add('hidden');
    document.getElementById('main-progress').classList.remove('hidden');
    document.getElementById('step-label').style.display = 'block';
    document.getElementById('step-label').innerText = `Domain Interview: ${domain}`;
    startMCQ('domain');
}

function setStep(n) {
    // Hide dashboard and all steps
    document.getElementById('dashboard-home').classList.add('hidden');
    for (let i = 1; i <= 5; i++) {
        const s = document.getElementById(`step-${i}`);
        if (s) s.classList.add('hidden');
    }

    if (n === 0) {
        document.getElementById('dashboard-home').classList.remove('hidden');
        document.getElementById('main-progress').classList.add('hidden');
        document.getElementById('step-label').style.display = 'none';
        currentStep = 0;
    } else {
        const target = document.getElementById(`step-${n}`);
        if (target) target.classList.remove('hidden');

        document.getElementById('main-progress').classList.remove('hidden');
        const label = document.getElementById('step-label');
        label.style.display = 'block';

        // Update label text based on step
        const labels = ["", "Resume Upload", "Analysis Result", "Assessment Module", "AI Interview", "Performance Report"];
        label.innerText = labels[n] || "";

        const dots = document.querySelectorAll('.step');
        dots.forEach((dot, idx) => {
            if (idx < n) dot.classList.add('active');
            else dot.classList.remove('active');
        });
        currentStep = n;
    }
}

async function handleUpload() {
    const fileInput = document.getElementById('file-upload');
    if (!fileInput.files.length) return;

    const formData = new FormData();
    formData.append('resume', fileInput.files[0]);

    const statusText = document.getElementById('upload-status-text');
    const statusIcon = document.getElementById('upload-status-icon');
    const nextBtn = document.getElementById('resume-next-btn');

    statusText.innerText = "Analyzing Resume...";
    statusIcon.innerText = "⏳";
    statusIcon.style.animation = "spin 2s linear infinite";

    try {
        const res = await fetch(API_BASE + "/upload", {
            method: 'POST',
            body: formData,
            credentials: 'include'
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        currentSessionId = data.session_id;
        document.getElementById('ats-score-display').innerText = data.score + "/100";
        document.getElementById('skills-count-display').innerText = data.skills ? data.skills.length : 0;

        statusText.innerText = "Analysis Complete!";
        statusIcon.innerText = "✅";
        statusIcon.style.animation = "none";
        nextBtn.disabled = false;

        // Removed notification alert to reduce popups
    } catch (err) {
        alert("Upload failed: " + err.message);
        statusText.innerText = "Drop your PDF file here";
        statusIcon.innerText = "📤";
        statusIcon.style.animation = "none";
    }
}

// --- MCQ ---
function startMCQ(type) {
    mcqType = type;
    mcqIdx = 0;
    let poolKey = type === 'domain' ? currentDomain : type;
    let count = type === 'domain' ? 5 : 3;

    if (!questionsPool[poolKey]) poolKey = 'tech';
    activeMCQQuestions = getRandomSubset(questionsPool[poolKey], count);

    setStep(3);
    renderMCQ();
}

function renderMCQ() {
    if (mcqIdx >= activeMCQQuestions.length) {
        if (mcqType === 'tech') return startMCQ('apt');
        setStep(4);
        setTimeout(startAIInterview, 1000);
        return;
    }

    const q = activeMCQQuestions[mcqIdx];
    document.getElementById('mcq-q-text').innerText = q.q;
    const cont = document.getElementById('mcq-options-list');
    cont.innerHTML = '';

    q.opts.forEach((opt, i) => {
        const btn = document.createElement('div');
        btn.innerText = opt;
        btn.className = 'btn-secondary';
        btn.style.padding = '1rem';
        btn.style.borderRadius = '0.75rem';
        btn.style.cursor = 'pointer';
        btn.style.textAlign = 'left';
        btn.onclick = () => {
            if (i === q.a) scores[mcqType]++;
            mcqIdx++;
            renderMCQ();
        };
        cont.appendChild(btn);
    });
}

// --- INTERVIEW ---
async function startAIInterview() {
    try {
        const res = await fetch(API_BASE + "/interview/start", {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSessionId,
                context: currentDomain || 'Resume'
            }),
            credentials: 'include'
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        currentQuestion = data.question;
        addMsg(data.question, 'bot');
        speak(data.question);
    } catch (err) {
        addMsg("Connection Error. Please check your AI keys.", 'bot');
    }
}

async function sendAns() {
    const inp = document.getElementById('chat-inp');
    const txt = inp.value.trim();
    if (!txt) return;

    addMsg(txt, 'user');
    inp.value = '';

    try {
        const res = await fetch(API_BASE + "/interview/answer", {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSessionId,
                question: currentQuestion,
                answer: txt,
                context: currentDomain || 'Resume'
            }),
            credentials: 'include'
        });
        const data = await res.json();

        interviewRatings.push(data.rating || 7);
        // data.feedback is saved for the final report, but NOT shown in chat now.
        feedbackLog.push(`Q: ${currentQuestion} | Feedback: ${data.feedback}`);

        // REMOVED: addMsg(data.feedback, 'bot'); -> User requested no reply/feedback during interview.

        intIdx++;
        if (intIdx >= interviewLimit) {
            setTimeout(() => {
                addMsg("Excellent! You've completed the interview. Generating your final report now...", 'bot');
                setTimeout(showFinalResults, 2000);
            }, 500);
            return;
        }

        // Reduced delay since we aren't showing reading text
        setTimeout(() => {
            currentQuestion = data.next_question;
            if (!currentQuestion || currentQuestion === 'undefined') {
                console.warn("Server returned empty question. Using fallback.");
                currentQuestion = "Could you walk me through your professional background?";
            }

            const context_label = currentDomain === 'Common' ? 'HR' : (currentDomain || 'Resume');
            document.getElementById('int-title').innerText = `${context_label} Interview - Q${intIdx + 1}/5`;
            addMsg(currentQuestion, 'bot');
            speak(currentQuestion);
        }, 500); // 500ms delay for natural flow
    } catch (err) {
        console.error(err);
        addMsg("Connection lost. Retrying...", 'bot');
    }
}

function addMsg(txt, type) {
    const chat = document.getElementById('scrolling-chat');
    if (!chat) return;
    const div = document.createElement('div');
    div.className = `bubble bubble-${type === 'bot' ? 'bot' : 'user'}`;
    div.innerText = txt;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
}

function showFinalResults() {
    setStep(5);
    let interviewScore = 7;
    if (interviewRatings.length > 0) {
        interviewScore = Math.round(interviewRatings.reduce((a, b) => a + b, 0) / interviewRatings.length);
    }

    const container = document.getElementById('score-cards-container');
    container.innerHTML = `
        <div class="card" style="text-align:center;">
             <div style="color:var(--primary); font-size:2.5rem; font-weight:800;">${interviewScore}/10</div>
             <p style="font-weight:600; margin-top:0.5rem;">Interview Rating</p>
        </div>
        <div class="card" style="text-align:center;">
             <div style="color:var(--text-dark); font-size:2.5rem; font-weight:800;">${scores.tech + scores.apt}/5</div>
             <p style="font-weight:600; margin-top:0.5rem;">MCQ Performance</p>
        </div>
    `;

    const list = document.getElementById('int-feedback-list');
    list.innerHTML = feedbackLog.map(l => `<li>${l}</li>`).join('');
}

async function downloadReport() {
    const btn = event.target;
    btn.innerText = "Processing...";

    const payload = {
        user_id: user.user_id,
        domain: currentDomain || 'Resume',
        score_mcq: scores.tech + scores.apt + (scores.domain || 0),
        score_interview: Math.round(interviewRatings.reduce((a, b) => a + b, 0) / interviewRatings.length) || 7,
        feedback: feedbackLog
    };

    try {
        const res = await fetch(API_BASE + "/export/pdf", {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            credentials: 'include'
        });
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = "Interview_Report.pdf";
        a.click();
    } catch (e) {
        alert("Export failed.");
    } finally {
        btn.innerText = "Export Performance PDF";
    }
}

// --- VOICE ---
function speak(txt) {
    if (!synth) return;
    const utter = new SpeechSynthesisUtterance(txt);
    synth.speak(utter);
}

function toggleVoice() {
    if (!('webkitSpeechRecognition' in window)) return alert("Speech recognition not supported.");
    if (!recognition) {
        recognition = new webkitSpeechRecognition();
        recognition.onstart = () => document.getElementById('mic-btn').classList.add('mic-active');
        recognition.onend = () => document.getElementById('mic-btn').classList.remove('mic-active');
        recognition.onresult = (e) => {
            document.getElementById('chat-inp').value = e.results[0][0].transcript;
            sendAns();
        };
    }
    recognition.start();
}

function goBack() {
    // Reset state
    intIdx = 0;
    mcqIdx = 0;
    scores = { tech: 0, apt: 0, domain: 0 };
    interviewRatings = [];
    document.getElementById('scrolling-chat').innerHTML = '';

    setStep(0);
}

function closeModals() {
    document.querySelectorAll('.modal-overlay').forEach(m => {
        if (m.id !== 'login-screen' && m.id !== 'onboarding-screen') {
            m.style.display = 'none';
        }
    });
}

// Close modals on background click
window.onclick = (e) => {
    if (e.target.className === 'modal-overlay') {
        const id = e.target.id;
        // Don't allow closing auth modals by clicking background if not logged in
        if (id !== 'login-screen' && id !== 'onboarding-screen') {
            e.target.style.display = 'none';
        }
    }
};
