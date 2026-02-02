import os
import json
import random
import requests

class LLMEngine:
    def __init__(self):
        # Load API keys
        self.gemini_key = os.getenv("GOOGLE_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")

    def _generate_text(self, prompt, temperature=0.7):
        """Unified method to call either Gemini or GPT-4o-mini using REST APIs."""
        
        # 1. Try OpenAI REST API if key exists
        if self.openai_key:
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.openai_key}"
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature
                }
                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                if response.status_code == 200:
                    return response.json()['choices'][0]['message']['content']
                else:
                    print(f"OpenAI REST Error: {response.text}")
            except Exception as e:
                print(f"OpenAI REST Exception: {e}")

        # 2. Try Gemini REST API if key exists
        if self.gemini_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": 1000
                    }
                }
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    return response.json()['candidates'][0]['content']['parts'][0]['text']
                else:
                    print(f"Gemini REST Error: {response.text}")
            except Exception as e:
                print(f"Gemini REST Exception: {e}")

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
                # Find start and end of JSON array
                start = clean_res.find('[')
                end = clean_res.rfind(']') + 1
                if start >= 0 and end > 0:
                    return json.loads(clean_res[start:end])
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

            # --- FIXED QUESTION BANK ---
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

            if context == "Resume":
                skills_lower = [s.lower() for s in skills] if skills else []
                eligible_pool = []
                if any(x in skills_lower for x in ['c', 'c programming']): eligible_pool.extend(C_QUESTIONS)
                if any(x in skills_lower for x in ['python']): eligible_pool.extend(PYTHON_QUESTIONS)
                if any(x in skills_lower for x in ['java']): eligible_pool.extend(JAVA_QUESTIONS)
                
                if not eligible_pool: eligible_pool = ALL_FIXED_QUESTIONS
                
                previous_qs = [h.get('q', '') for h in history]
                available_qs = [q for q in eligible_pool if q not in previous_qs]
                if available_qs: return random.choice(available_qs)
                
            elif context in ["Common", "HR"]:
                HR_QUESTIONS = [
                    "Tell me about yourself.",
                    "Why should we hire you?",
                    "Why do you want to work for our company?",
                    "Where do you see yourself in 5 years?",
                    "How do you handle pressure or stress?",
                    "Describe a challenge you faced and how you overcame it."
                ]
                if turn_count == 2: return "What are your strengths?"
                
                previous_qs_norm = set([h.get('q', '').strip().lower() for h in history])
                available_qs = [q for q in HR_QUESTIONS if q.strip().lower() not in previous_qs_norm]
                if available_qs: return random.choice(available_qs)
            
            # LLM FALLBACK
            prompt = f"Role: Interviewer\nContext: {context}\nHistory: {history_str}\nAsk ONE clear question."
            res = self._generate_text(prompt, temperature=0.85)
            return res.strip() if res and len(res.strip()) > 5 else "Describe your background."

        except Exception as e:
            print(f"Error in generate_question: {e}")
            return "Tell me about your technical skills."

    def evaluate_answer(self, question, answer):
        prompt = f"""
        Analyze the interview answer.
        Question: {question}
        Answer: {answer}
        Output JSON: {{"feedback": "string", "rating": number}}
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
        return {"feedback": "Good attempt. Try the STAR method.", "rating": 6}
