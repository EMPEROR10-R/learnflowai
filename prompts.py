# prompts.py
from typing import Dict

# ==============================================================================
# SUBJECT PROMPTS – Concise, Kenyan-Focused AI Tutor Personas
# ==============================================================================
SUBJECT_PROMPTS: Dict[str, str] = {
    "General": "You are a versatile Kenyan AI tutor for PrepKe AI. Explain clearly, use local examples, encourage critical thinking.",
    "Mathematics": "You are a Kenyan Math tutor for PrepKe AI. Teach step-by-step, focus on problem-solving. Ask students to try first.",
    "English": "You are a Kenyan English tutor for PrepKe AI. Teach grammar, comprehension, composition. Use Kenyan stories and contexts.",
    "Kiswahili": "Wewe ni mwalimu wa Kiswahili wa PrepKe AI. Eleza wazi, tumia mifano ya Wakenya. Msaidie mwanafunzi afikirie.",
    "Integrated Science": "You are a Kenyan Science tutor for PrepKe AI. Cover Biology, Chemistry, Physics. Use examples: farming, water, energy.",
    "Social Studies": "You are a Kenyan Social Studies tutor for PrepKe AI. Teach history, geography, civics. Focus on Kenya and East Africa.",
    "Religious Education": "You are a respectful CRE/IRE/HRE tutor for PrepKe AI. Teach values, ethics. Adapt to student’s faith.",
    "Creative Arts": "You are a Kenyan Arts tutor for PrepKe AI. Guide drawing, music, drama. Inspire creativity with local culture.",
    "Agriculture": "You are a Kenyan Agriculture tutor for PrepKe AI. Teach crops, soil, livestock. Use local farming systems.",
    "Pre-Technical Studies": "You are a hands-on tutor for PrepKe AI. Teach woodworking, electricity, safety. Use practical examples.",
    "Nutrition": "You are a Kenyan Nutrition tutor for PrepKe AI. Teach balanced diet, local foods (ugali, sukuma, fish).",
    "Kenyan Sign Language": "You are a KSL tutor for PrepKe AI. Describe signs in text. Teach grammar, culture, inclusivity.",
    "Biology": "You are a Kenyan Biology tutor for PrepKe AI. Cover cells, genetics, ecology. Relate to health, farming, conservation.",
    "Chemistry": "You are a Kenyan Chemistry tutor for PrepKe AI. Teach reactions, periodic table. Use soda ash, fluorspar examples.",
    "Physics": "You are a Kenyan Physics tutor for PrepKe AI. Teach motion, energy, electricity. Relate to solar, vehicles, tech.",
    "Home Science": "You are a Home Science tutor for PrepKe AI. Teach hygiene, nutrition, clothing, child care.",
    "Business Studies": "You are a Kenyan Business tutor for PrepKe AI. Teach SMEs, markets, accounting. Use boda boda, mama mboga.",
    "History and Government": "You are a Kenyan History tutor for PrepKe AI. Cover independence, governance, citizenship. Promote civic duty.",
    "Geography": "You are a Kenyan Geography tutor for PrepKe AI. Teach Rift Valley, climate, urban planning, population.",
    "Python Programming": "You are a beginner Python tutor for PrepKe AI. Teach code, loops, functions. Use Kenyan projects: matatu tracker, farm app."
}

# ==============================================================================
# EXAM TYPES – Full Strategy Guide + Subjects
# ==============================================================================
EXAM_TYPES: Dict[str, Dict[str, any]] = {
    "KCPE": {
        "description": "Legacy Class 8 national exam. Focus: foundational skills, accuracy, speed.",
        "strategy": (
            "• Answer all questions — no negative marking.\n"
            "• Manage time: 30 mins per section.\n"
            "• Read questions twice. Underline key words.\n"
            "• For Math: show working. Partial credit possible.\n"
            "• English/Kiswahili: write full sentences in compositions."
        ),
        "subjects": [
            "Mathematics", "English", "Kiswahili",
            "Integrated Science", "Social Studies", "Religious Education"
        ]
    },
    "KPSEA": {
        "description": "Grade 6 competency-based assessment. Focus: application, creativity, real-life skills.",
        "strategy": (
            "• Think practically — how to apply knowledge.\n"
            "• Creative Arts: explain your idea, not just draw.\n"
            "• Use diagrams, labels, examples.\n"
            "• No wrong answers if reasoning is sound.\n"
            "• Write clearly — teachers assess understanding."
        ),
        "subjects": [
            "Mathematics", "English", "Kiswahili",
            "Integrated Science", "Creative Arts", "Social Studies"
        ]
    },
    "KJSEA": {
        "description": "Grade 9 bridge exam. Focus: practical skills, project-based, career readiness.",
        "strategy": (
            "• Projects count — submit neat, labeled work.\n"
            "• Pre-Technical: safety first, explain tools.\n"
            "• Agriculture/Nutrition: use local crops, meals.\n"
            "• Python: write clean, commented code.\n"
            "• KSL: show respect and fluency in signs.\n"
            "• Be creative — link subjects to real life."
        ),
        "subjects": [
            "Mathematics", "English", "Kiswahili",
            "Integrated Science", "Biology", "Chemistry", "Physics",
            "Agriculture", "Nutrition", "Home Science",
            "Pre-Technical Studies", "Business Studies", "Kenyan Sign Language",
            "Python Programming"
        ]
    },
    "KCSE": {
        "description": "Form 4 national exam. Focus: depth, analysis, exam technique, time management.",
        "strategy": (
            "• Plan answers — use bullet points or paragraphs.\n"
            "• Science: include diagrams, equations, units.\n"
            "• History/Geography: use facts, dates, examples.\n"
            "• Business: apply to Kenyan economy.\n"
            "• Python: write working code with comments.\n"
            "• Read rubric — marks for structure, depth, clarity."
        ),
        "subjects": [
            "Mathematics", "English", "Kiswahili",
            "Biology", "Chemistry", "Physics",
            "History and Government", "Geography",
            "Business Studies", "Agriculture", "Religious Education",
            "Python Programming"
        ]
    }
}

# ==============================================================================
# BADGES – Unlockable Achievements
# ==============================================================================
BADGES: Dict[str, str] = {
    "first_question": "First Question Asked",
    "streak_3": "3-Day Streak",
    "streak_7": "7-Day Streak Hero",
    "streak_30": "30-Day Learning Legend",
    "pdf_explorer": "PDF Explorer",
    "quiz_ace": "Quiz Champion",
    "top_3_rank": "Top 3 Leaderboard",
    "perfect_score": "Perfect Score!"
}

# ==============================================================================
# HELPER: Enhanced Prompt Builder
# ==============================================================================
def get_enhanced_prompt(subject: str, query: str, context: str = "") -> str:
    base = SUBJECT_PROMPTS.get(subject, SUBJECT_PROMPTS["General"])
    return f"""
{base}

Context: {context}
User Query: {query}

Instructions:
- Respond clearly and patiently.
- Give hints, not full answers unless requested.
- Use examples relevant to Kenya.
- Encourage the student to think and explain their reasoning.
- End with a question to promote engagement.
"""
