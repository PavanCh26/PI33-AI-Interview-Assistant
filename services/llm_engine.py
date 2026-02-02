# AI imports moved inside methods to save memory
import os
import json
import random

class LLMEngine:
    def __init__(self):
        # Load API keys
        self.gemini_key = os.getenv("GOOGLE_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.gemini_model = None
        self.openai_client = None
        self._initialized = False

    def _lazy_init(self):
        if self._initialized: return
        
        if self.openai_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=self.openai_key)
            except ImportError:
                print("DEBUG: openai not installed")

        if self.gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_key)
                self.gemini_model = genai.GenerativeModel('gemini-1.5-flash')
            except ImportError:
                print("DEBUG: google-generativeai not installed")
        
        self._initialized = True

    def _generate_text(self, prompt, temperature=0.7):
        """Unified method to call either Gemini or GPT-4o-mini."""
        self._lazy_init()
        
        # Prefer OpenAI if available, else use Gemini
        if self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"OpenAI Error: {e}")
                
        if self.gemini_model:
            try:
                import google.generativeai as genai
                response = self.gemini_model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=500
                    )
                )
                return response.text
            except Exception as e:
                print(f"Gemini Error: {e}")
                
        return None

    def extract_skills(self, text):
        prompt = f"""
        Extract a list of technical and soft skills from the following resume text. 
        Return ONLY a JSON list of strings.
        Resume Text: {text[:4000]}
        """
        res = self._generate_text(prompt, temperature=0.2)
        if res:
            try:
                clean_res = res.replace("```json", "").replace("```", "").strip()
                return json.loads(clean_res)
            except:
                pass
        return ["Python", "Problem Solving", "Technical Skills"]

    def score_resume(self, text):
        prompt = f"""
        Analyze the following resume and provide an ATS readiness score out of 100 based on structure, keywords, and clarity.
        Return ONLY the numeric score.
        Resume Text: {text[:4000]}
        """
        res = self._generate_text(prompt, temperature=0.2)
        if res:
            try:
                return int(''.join(filter(str.isdigit, res)))
            except:
                pass
        return 75

    def generate_question(self, skills, history, context="Resume"):
        try:
            history_str = "\n".join([f"Q: {h['q']}\nA: {h['a']}" for h in history])
            turn_count = len(history)

            # --- FIXED QUESTION BANK (User Requested) ---
            C_QUESTIONS = [
                "What is the difference between malloc() and calloc()?",
                "Explain pointers and pointer arithmetic with an example.",
                "What is the use of static keyword in C? Explain with scenarios.",
                "How does memory allocation work in C? What causes memory leaks?",
                "Write a C program to reverse a string without using library functions."
            ]
            
            PYTHON_QUESTIONS = [
                "What is the difference between a list, tuple, and set in Python?",
                "Explain how Python manages memory and garbage collection.",
                "What are decorators in Python? Where are they used?",
                "Explain the difference between deep copy and shallow copy.",
                "Write a Python function to find the second largest number in a list."
            ]
            
            JAVA_QUESTIONS = [
                "What is the difference between == and .equals() in Java?",
                "Explain OOP concepts used in Java with real examples.",
                "What is JVM, JRE, and JDK? How do they differ?",
                "What is exception handling? Difference between checked and unchecked exceptions.",
                "Write a Java program to check whether a string is a palindrome."
            ]
            
            ALL_FIXED_QUESTIONS = C_QUESTIONS + PYTHON_QUESTIONS + JAVA_QUESTIONS

            # --- RESUME CONTEXT ---
            if context == "Resume":
                skills_lower = [s.lower() for s in skills] if skills else []
                eligible_pool = []
                
                # Build pool based on skills
                if any(x in skills_lower for x in ['c', 'c programming', 'c language']):
                    eligible_pool.extend(C_QUESTIONS)
                if any(x in skills_lower for x in ['python', 'python3', 'python programming']):
                    eligible_pool.extend(PYTHON_QUESTIONS)
                if any(x in skills_lower for x in ['java', 'core java', 'java programming']):
                    eligible_pool.extend(JAVA_QUESTIONS)
                    
                # Fallback to all if empty
                if not eligible_pool:
                    eligible_pool = ALL_FIXED_QUESTIONS
                
                previous_qs = [h.get('q', '') for h in history]
                available_qs = [q for q in eligible_pool if q not in previous_qs]
                
                if available_qs:
                    return random.choice(available_qs)
                    
                role_description = "Hiring Manager"
                task_instruction = f"Ask a tough technical question about: {', '.join(skills[:5])}"

            # --- HR / COMMON CONTEXT ---
            elif context == "Common" or context == "HR":
                HR_QUESTIONS = [
                    "Tell me about yourself.",
                    "Why should we hire you?",
                    "Why do you want to work for our company?",
                    "Where do you see yourself in 5 years?",
                    "How do you handle pressure or stress?",
                    "Describe a challenge you faced and how you overcame it.",
                    "Are you willing to relocate or work flexible hours?",
                    "Do you have any questions for us?"
                ]
                
                # FORCED 3rd QUESTION LOGIC
                target_q3 = "What are your strengths?"
                
                if turn_count == 2: # 0, 1, 2(3rd)
                    return target_q3

                previous_qs_norm = set([h.get('q', '').strip().lower() for h in history])
                
                available_qs = []
                for q in HR_QUESTIONS:
                    if q == target_q3: 
                        continue # Don't ask strengths early
                    if q.strip().lower() not in previous_qs_norm:
                        available_qs.append(q)
                        
                if available_qs:
                    return random.choice(available_qs)
                    
                if HR_QUESTIONS:
                    q = random.choice(HR_QUESTIONS)
                    if q == target_q3 and turn_count != 2:
                        return "Tell me about yourself." # Safety fallback
                    return q
                    
                role_description = "HR Manager"
                task_instruction = "Ask a behavioral interview question."

            # --- DOMAIN CONTEXT ---
            else:
                role_description = f"Principal {context} Engineer"
                task_instruction = f"Ask a challenging technical domain question about {context}."

            # --- LLM FALLBACK GENERATION ---
            variety_seed = random.randint(1, 100000)
            prompt = f"""
            Role: {role_description}
            Context: {context}
            Question {turn_count + 1}
            {task_instruction}
            History: {history_str}
            
            Instructions: Ask ONE clear question. No filler.
            """
            
            res = self._generate_text(prompt, temperature=0.85)
            if res and len(res.strip()) > 5:
                # Basic check to avoid "undefined" strings or short errors
                return res.strip()
                
            return "Describe your professional background."

        except Exception as e:
            print(f"Error in generate_question: {e}", flush=True)
            return "Tell me about your technical skills."

    def evaluate_answer(self, question, answer):
        prompt = f"""
        Role: Interview Coach & Mentor.
        Question Asked: {question}
        Candidate Answer: {answer}
        
        Analyze the response.
        
        Requirements:
        1. Feedback: Provide specific areas of improvement based on the answer.
        2. Resources: Suggest 1-2 SPECIFIC resources (Book names, Topics to Google, or specific techniques) to improve this skill.
        3. Rating: Rate out of 10.
        
        Output JSON Format ONLY:
        {{"feedback": "Your answer was... Improve by... Suggested Resources: 1. ... 2. ...", "rating": 7}}
        """
        res = self._generate_text(prompt, temperature=0.3)
        if res:
            try:
                clean_res = res.replace("```json", "").replace("```", "").strip()
                start = clean_res.find('{')
                end = clean_res.rfind('}') + 1
                if start >= 0 and end > 0:
                    return json.loads(clean_res[start:end])
            except:
                pass
        return {"feedback": "Good attempt. Try to structure your answer using the STAR method. Suggested Resources: 'Cracking the Coding Interview' or generic HR prep guides.", "rating": 6}
