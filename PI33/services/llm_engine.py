import google.generativeai as genai
import os
import json
import random

class LLMEngine:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    def _call_gemini(self, prompt):
        if not self.model:
            return None
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Gemini API Error: {e}")
            return None

    def extract_skills(self, text):
        if not self.model:
            return ["Python", "SQL", "Communication"] # Fallback

        prompt = f"""
        Extract a list of technical and soft skills from the following resume text. 
        Return ONLY a JSON list of strings.
        Resume Text: {text[:4000]}
        """
        res = self._call_gemini(prompt)
        if res:
            try:
                # Clean markdown if present
                clean_res = res.replace("```json", "").replace("```", "").strip()
                return json.loads(clean_res)
            except:
                pass
        return ["Technical Skills", "Problem Solving"]

    def score_resume(self, text):
        if not self.model:
            return random.randint(70, 85) # Fallback

        prompt = f"""
        Analyze the following resume and provide an ATS readiness score out of 100 based on structure, keywords, and clarity.
        Return ONLY the numeric score.
        Resume Text: {text[:4000]}
        """
        res = self._call_gemini(prompt)
        if res:
            try:
                return int(''.join(filter(str.isdigit, res)))
            except:
                pass
        return 75

    def generate_question(self, skills, history, context="Resume"):
        if not self.model:
            return f"Tell me about your experience related to {context}."

        history_str = "\n".join([f"Q: {h['q']}\nA: {h['a']}" for h in history])
        covered_topics = [h['q'].lower() for h in history]
        turn_count = len(history)
        
        # Determine behavior based on context
        if context == "Resume":
            role_description = "Senior Technical Recruiter focusing on Resume Verification."
            task_instruction = f"""
            TASK: Ask a technical question STRICTLY based on the candidate's background and skills listed in their resume.
            Candidate Skills: {', '.join(skills)}
            Focus on their specific projects, technologies mentioned, or experiences.
            Do not ask general technical questions outside of their provided background.
            """
        elif context == "Common" or context == "HR":
            role_description = "HR Manager."
            task_instruction = """
            TASK: Ask a basic HR or Behavioral question.
            Examples: 'Tell me about yourself', 'Why should we hire you?', 'How do you handle conflict?', 'Where do you see yourself in 5 years?'.
            Keep it professional and standard for an entry-to-mid level interview.
            """
        else:
            # Technical Domain (AI, ML, VLSI, Embedded, etc.)
            role_description = f"Senior Expert in {context}."
            task_instruction = f"""
            TASK: Ask a technical question STRICTLY related to the {context} domain.
            Focus on core concepts, advanced theories, or practical applications within {context}.
            Discard resume details if they are not relevant to {context}; focus on the domain knowledge.
            """

        prompt = f"""
        Role: {role_description}
        Interview Progress: Question {turn_count + 1} of 5.
        
        {task_instruction}
        
        Previous History (DO NOT REPEAT TOPICS FROM HERE):
        {history_str}
        
        REQUIREMENTS:
        1. Brief 1-sentence acknowledgement of the last answer (if any).
        2. Ask a unique, clear question based on the task above.
        3. NEVER ask the same question twice.
        4. If it's the first question, skip acknowledgment.
        
        Return ONLY the Response (Acknowledgement + The NEW Question).
        """
        res = self._call_gemini(prompt)
        return res.strip() if res else f"Let's talk about your experience with {context}. Can you describe a challenging project you worked on?"

    def evaluate_answer(self, question, answer):
        if not self.model:
            return {"feedback": "Good answer. Consider adding more metrics to your result section.", "rating": 8}

        prompt = f"""
        Role: Senior Technical Lead & Evaluator.
        Question Asked: {question}
        Candidate Answer: {answer}
        
        Analyze the response for:
        - Technical Accuracy & Depth.
        - Problem-solving Logic.
        - Communication Clarity (STAR method usage).
        
        Requirements:
        1. Be CRITICAL. Point out exactly what was missing or where the logic was weak.
        2. If correct, suggest how to make it 'Senior Level' (e.g., mention scalability, edge cases).
        3. Rate out of 10 based on professional standards.
        
        Return ONLY a JSON object: {{"feedback": "Critical technical feedback...", "rating": 7}}
        """
        res = self._call_gemini(prompt)
        if res:
            try:
                # Clean markdown
                clean_res = res.replace("```json", "").replace("```", "").strip()
                start = clean_res.find('{')
                end = clean_res.rfind('}') + 1
                if start >= 0 and end > 0:
                    return json.loads(clean_res[start:end])
            except:
                pass
        return {"feedback": "Your answer is decent, but lacks technical depth and specific examples. Try explaining the 'Why' behind your decisions.", "rating": 6}
