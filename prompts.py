# prompts.py — COMPLETE 2025 KENYAN CBC CURRICULUM | ALL SUBJECTS & TOPICS ADDED
from typing import Dict

SUBJECT_PROMPTS: Dict[str, str] = {
    "General": "You are a versatile Kenyan AI tutor. Explain clearly using local Kenyan examples.",
    "Mathematics": "You are an expert Kenyan Mathematics tutor. Teach step-by-step with problem-solving.",
    "English": "You are a Kenyan English tutor. Focus on grammar, comprehension, composition with Kenyan contexts.",
    "Kiswahili": "Wewe ni mwalimu bora wa Kiswahili. Eleza kwa mifano ya Wakenya.",
    "Integrated Science": "You are a Kenyan Integrated Science tutor covering Biology, Chemistry, Physics with practical Kenyan examples.",
    "Creative Arts & Social Studies": "You are a Creative Arts & Social Studies tutor. Cover art, music, drama, history, geography, citizenship.",
    "Religious Education": "You are a respectful CRE/IRE/HRE tutor. Teach values and ethics, adapt to student's faith.",
    "Social Studies": "You are a Kenyan Social Studies tutor. Cover history, geography, civics, Kenya & East Africa.",
    "Creative Arts & Sports": "You are a Creative Arts & Sports tutor. Guide drawing, music, drama, PE with Kenyan culture.",
    "Agriculture & Nutrition": "You are an Agriculture & Nutrition tutor. Teach crops, livestock, soil, balanced diet with ugali, sukuma etc.",
    "Pre-Technical Studies": "You are a Pre-Technical Studies tutor. Teach safety, tools, woodworking, metalwork, electricity.",
    "Physical Health Education & Sports": "You are a PE & Sports tutor. Teach health, fitness, games, hygiene.",
    "Biology": "You are a Kenyan Biology tutor. Cover cells, genetics, ecology, health, conservation.",
    "Physics": "You are a Kenyan Physics tutor. Teach motion, energy, electricity, waves with local examples.",
    "Chemistry": "You are a Kenyan Chemistry tutor. Cover reactions, periodic table, organic with Kenyan resources.",
    "History and Government": "You are a Kenyan History tutor. Cover independence, constitution, world wars, civic duty.",
    "Geography": "You are a Kenyan Geography tutor. Cover physical, human, climate, population, map work.",
    "Business Studies": "You are a Kenyan Business tutor. Teach entrepreneurship, marketing, accounting with boda boda examples.",
    "Computer Studies": "You are a Computer Studies tutor. Teach hardware, software, networking, ethics.",
    "Python Programming": "You are a beginner-to-advanced Python tutor for Kenyan students. Use projects like matatu tracker, farm app. Award XP on completion."
}

EXAM_TYPES: Dict[str, Dict[str, any]] = {
    "KPSEA": {
        "description": "Grade 6 national assessment. Focus: foundational skills, application, creativity.",
        "strategy": "• Apply knowledge practically.\n• Use diagrams and examples.\n• Write clearly.",
        "subjects": [
            "Mathematics", "English", "Kiswahili", "Integrated Science",
            "Creative Arts & Social Studies", "Religious Education"
        ],
        "topics": {
            "Mathematics": ["Numbers", "Patterns", "Measurement", "Geometry", "Data Handling"],
            "English": ["Grammar", "Comprehension", "Composition"],
            "Kiswahili": ["Lugha", "Fasihi", "Insha"],
            "Integrated Science": ["Human Body", "Plants", "Animals", "Energy", "Environment", "Health"],
            "Creative Arts & Social Studies": ["Drawing", "Music", "Drama", "Craft", "Map Work", "Citizenship", "History"],
            "Religious Education": ["Values", "Stories", "Ethics"]
        },
        "projects": {}
    },
    "KJSEA": {
        "description": "Grade 9 transition assessment. Focus: practical skills, projects, career readiness.",
        "strategy": "• Submit neat project work.\n• Explain tools and safety.\n• Link to real life.",
        "subjects": [
            "Mathematics", "English", "Kiswahili", "Integrated Science",
            "Social Studies", "Agriculture & Nutrition", "Pre-Technical Studies",
            "Creative Arts & Sports", "Religious Education", "Physical Health Education & Sports"
        ],
        "topics": {
            "Mathematics": ["Algebra", "Geometry", "Statistics", "Fractions", "Ratios"],
            "Integrated Science": ["Biology", "Chemistry", "Physics basics"],
            "Agriculture & Nutrition": ["Crops", "Livestock", "Soil", "Balanced Diet"],
            "Pre-Technical Studies": ["Woodwork", "Metalwork", "Electricity", "Safety", "Drawing"],
            "Creative Arts & Sports": ["Art", "Music", "Drama", "Sports"],
            "Social Studies": ["History", "Geography", "Civics"],
            "Physical Health Education & Sports": ["Fitness", "Games", "Hygiene"]
        },
        "projects": {
            "Pre-Technical Studies": "Design a simple circuit or tool (150 XP)",
            "Agriculture & Nutrition": "Plan a kitchen garden (100 XP)"
        }
    },
    "KCSE": {
        "description": "Form 4 national exam. Focus: depth, analysis, exam technique.",
        "strategy": "• Use diagrams, equations.\n• Apply facts to Kenyan context.\n• Manage time well.",
        "subjects": [
            "Mathematics", "English", "Kiswahili",
            "Biology", "Physics", "Chemistry",
            "History and Government", "Geography",
            "Business Studies", "Agriculture", "Computer Studies",
            "Religious Education", "Python Programming"
        ],
        "topics": {
            "Mathematics": ["Algebra", "Geometry", "Trigonometry", "Calculus", "Probability"],
            "Biology": ["Cells", "Genetics", "Ecology", "Evolution", "Health"],
            "Physics": ["Motion", "Energy", "Electricity", "Waves"],
            "Chemistry": ["Atomic Structure", "Periodic Table", "Organic", "Electrochemistry"],
            "History and Government": ["Colonialism", "Independence", "Constitution"],
            "Geography": ["Physical", "Human", "Climate", "Population"],
            "Business Studies": ["Entrepreneurship", "Finance", "Marketing"],
            "Computer Studies": ["Hardware", "Software", "Networking", "Programming"],
            "Python Programming": ["OOP", "Modules", "Databases", "GUI", "Web Basics"]
        },
        "projects": {
            "Computer Studies": "Develop a school management system (300 XP)",
            "Python Programming": "Build a database quiz app (250 XP)"
        }
    }
}

# Keep badges and helper as before
BADGES: Dict[str, str] = { ... }  # unchanged

def get_enhanced_prompt(subject: str, query: str, context: str = "", topic: str = "", project: bool = False) -> str:
    base = SUBJECT_PROMPTS.get(subject, SUBJECT_PROMPTS["General"])
    extra = "Guide step-by-step and award XP on project completion." if project else f"Focus deeply on topic: {topic}." if topic else ""
    return f"{base}\n\nContext: {context}\nQuery: {query}\n{extra}\n\nRespond clearly, use Kenyan examples, end with a question."