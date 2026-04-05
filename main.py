import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import sqlite3
import hashlib 

# ---------------------------------------------------------
# 1. SETUP
# ---------------------------------------------------------
YOUR_API_KEY = "AIzaSyCyIQy22wuUH5EFRaUZmMp3ERDKVg5e2lM"
genai.configure(api_key=YOUR_API_KEY) 

app = FastAPI(title="LifeAI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# 2. DATABASE SETUP 
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect('lifeai_v3.db') 
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, username TEXT UNIQUE, password_hash TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_plans (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, schedule_text TEXT, FOREIGN KEY(user_id) REFERENCES users(id))''')
    conn.commit()
    conn.close()

init_db()

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

# ---------------------------------------------------------
# 3. DATA MODELS
# ---------------------------------------------------------
class UserSignup(BaseModel):
    name: str
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserProfile(BaseModel):
    user_id: int
    main_goal: str
    available_hours: int
    mood: str
    personality: str 

# ---------------------------------------------------------
# 4. AUTHENTICATION ENDPOINTS
# ---------------------------------------------------------
@app.post("/api/signup")
async def signup(user_data: UserSignup):
    conn = sqlite3.connect('lifeai_v3.db')
    cursor = conn.cursor()
    try:
        hashed_pw = hash_password(user_data.password)
        cursor.execute("INSERT INTO users (name, username, password_hash) VALUES (?, ?, ?)", (user_data.name, user_data.username, hashed_pw))
        conn.commit()
        return {"status": "success", "user_id": cursor.lastrowid, "name": user_data.name}
    except sqlite3.IntegrityError:
        return {"status": "error", "message": "Username already exists."}
    finally:
        conn.close()

@app.post("/api/login")
async def login(creds: UserLogin):
    conn = sqlite3.connect('lifeai_v3.db')
    cursor = conn.cursor()
    hashed_pw = hash_password(creds.password)
    cursor.execute("SELECT id, name FROM users WHERE username = ? AND password_hash = ?", (creds.username, hashed_pw))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {"status": "success", "user_id": user[0], "name": user[1]}
    return {"status": "error", "message": "Invalid username or password."}

# ---------------------------------------------------------
# 5. AI GENERATION & PLAN ENDPOINTS
# ---------------------------------------------------------
@app.post("/api/generate-plan")
async def generate_smart_plan(profile: UserProfile):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""
        You are 'LifeAI', an intelligent scheduling assistant.
        
        USER DATA: 
        - Free Time: {profile.available_hours} hours. 
        - Main Goal: {profile.main_goal}. 
        
        YOUR PERSONA: {profile.personality}
        You MUST adopt this persona completely in your response tone and formatting:
        - If "Strict Drill Sergeant", be extremely demanding, use uppercase for yelling, scold them for being lazy, and schedule rigorous tasks.
        - If "Zen Master", be calm, use nature metaphors, prioritize mental balance, and speak peacefully.
        - If "Sarcastic Best Friend", be witty, roast them slightly, use jokes, but still give a genuinely helpful schedule.
        - If "Friendly Assistant", be standard, clear, and encouraging.

        TASK: Create a structured daily schedule based on their goal. Format cleanly with times. Use bullet points. Do not use large markdown headers.
        """
        
        response = model.generate_content(prompt)
        
        conn = sqlite3.connect('lifeai_v3.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_plans WHERE user_id = ?", (profile.user_id,))
        cursor.execute("INSERT INTO user_plans (user_id, schedule_text) VALUES (?, ?)", (profile.user_id, response.text))
        conn.commit()
        conn.close()

        return {"status": "success", "schedule": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/get-plan/{user_id}")
async def get_saved_plan(user_id: int):
    conn = sqlite3.connect('lifeai_v3.db')
    cursor = conn.cursor()
    cursor.execute("SELECT schedule_text FROM user_plans WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return {"status": "success", "schedule": row[0]}
    return {"status": "empty"}

# --- NEW: Delete Plan Endpoint ---
@app.delete("/api/delete-plan/{user_id}")
async def delete_plan(user_id: int):
    try:
        conn = sqlite3.connect('lifeai_v3.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_plans WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Plan successfully deleted."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    print("🚀 Starting LifeAI Auth Server on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
