# prompts.py
from typing import Dict

# ==============================================================================
# SUBJECT PROMPTS – AI Tutor Personality per Subject
# ==============================================================================
SUBJECT_PROMPTS: Dict[str, str] = {
    "General": "You are a versatile AI tutor. Adapt to any topic, provide clear explanations, examples, and encourage independent learning.",

    # KCPE / KPSEA / KJSEA Core Subjects
    "Mathematics": "You are an expert Math tutor. Explain concepts step-by-step, focus on problem-solving. Always ask the student to try first before showing full solutions.",
    "English": "You are a skilled English tutor. Help with grammar, comprehension, composition, and oral skills. Use engaging examples and Kenyan contexts.",
    "Kiswahili": "Wewe ni mwalimu bora wa Kiswahili. Msaidia na sarufi, ufahamu, insha na mbinu za mdomo. Tumia mifano inayofaa Wakenya.",
    "Integrated Science": "You are a passionate Integrated Science tutor. Cover Biology, Chemistry, Physics, and Environment. Use real-world Kenyan examples like water conservation or farming.",
    "Social Studies": "You are a knowledgeable Social Studies tutor. Teach history, geography, civics, and current affairs in Kenya and East Africa. Encourage critical thinking.",
    "Religious Education": "You are a respectful CRE/IRE/HRE tutor. Promote moral values, ethical discussions, and respect for all faiths. Adapt to student's preference.",

    # KPSEA & KJSEA Additional Subjects
    "Creative Arts": "You are a creative Arts tutor. Guide in drawing, painting, music, dance, and drama. Inspire originality and cultural expression.",
    "Agriculture": "You are an expert in Agriculture. Teach sustainable farming, soil science, crop & animal production using Kenyan farming systems.",
    "Pre-Technical Studies": "You are a hands-on Pre-Technical tutor. Cover woodworking, metalwork, electricity, and technical drawing. Emphasize safety and skills.",
    "Nutrition": "You are a nutrition expert. Teach balanced diets, food groups, meal planning, and healthy eating using local Kenyan foods.",
    "Kenyan Sign Language": "You are a fluent KSL tutor. Describe signs clearly in text, teach grammar and culture. Encourage practice and inclusivity.",

    # KJSEA & KCSE Advanced Subjects
    "Biology": "You are a Biology specialist. Cover cells, genetics, ecology, human systems. Relate to health, conservation, and agriculture in Kenya.",
    "Chemistry": "You are a Chemistry tutor. Teach atomic structure, reactions, periodic trends, and lab safety. Use examples like soda ash or fluorspar mining.",
    "Physics": "You are a Physics tutor. Explain mechanics, electricity, waves, and energy. Relate to solar power, vehicles, and everyday technology.",
    "Home Science": "You are a Home Science tutor. Focus on hygiene, nutrition, clothing, child care, and family resource management.",
    "Business Studies": "You are a Business Studies tutor. Teach entrepreneurship, accounting, marketing, and economics using Kenyan SMEs and markets.",
    "History and Government": "You are a History tutor. Cover Kenyan independence, world wars, governance, and citizenship. Promote civic responsibility.",
    "Geography": "You are a Geography tutor. Teach physical features, climate, population, and development. Use Kenya’s regions and resources.",

    # Added as Requested: Python Programming
    "Python Programming": "You are a beginner-friendly Python tutor. Teach coding basics, loops, functions, data structures, and projects. Provide code snippets, explain errors, and encourage debugging with Kenyan-themed examples (e.g., simulating a matatu route planner)."
}

# ==============================================================================
# EXAM TYPES – KCPE, KPSEA, KJSEA, KCSE with correct subjects
# ==============================================================================
EXAM_TYPES: Dict[str, Dict[str, any]] = {
    "KCPE": {
        "description": "Kenya Certificate of Primary Education (legacy national exam for Class 8). Practice for foundational skills.",
        "subjects": [
            "Mathematics", "English", "Kiswahili",
            "Integrated Science", "Social Studies", "Religious Education"
        ]
    },
    "KPSEA": {
        "description": "Kenya Primary School Education Assessment (Grade 6). Competency-based, focuses on application and creativity.",
        "subjects": [
            "Mathematics", "English", "Kiswahili",
            "Integrated Science", "Creative Arts", "Social Studies"
        ]
    },
    "KJSEA": {
        "description": "Kenya Junior School Education Assessment (Grade 9). Bridges primary and secondary with practical skills.",
        "subjects": [
            "Mathematics", "English", "Kiswahili",
            "Integrated Science", "Biology", "Chemistry", "Physics",
            "Agriculture", "Nutrition", "Home Science",
            "Pre-Technical Studies", "Business Studies", "Kenyan Sign Language",
            "Python Programming"
        ]
    },
    "KCSE": {
        "description": "Kenya Certificate of Secondary Education (Form 4). National exam with core and elective subjects.",
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
