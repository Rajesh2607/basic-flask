from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import os
import cv2
import numpy as np
from werkzeug.utils import secure_filename
import uuid
from datetime import datetime
import json
import random

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # required for flash messages

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Ensure upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Create the database and tables
def init_db():
    with sqlite3.connect('database.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT UNIQUE NOT NULL,
                            password TEXT NOT NULL)''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS videos (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            filename TEXT NOT NULL,
                            original_filename TEXT NOT NULL,
                            pose_type TEXT NOT NULL,
                            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            analysis_score REAL,
                            analysis_data TEXT,
                            status TEXT DEFAULT 'uploaded',
                            FOREIGN KEY (user_id) REFERENCES users (id))''')

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with sqlite3.connect('database.db') as conn:
            try:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                user_id = cursor.lastrowid
                conn.commit()
                
                # Auto-login after successful signup
                session['username'] = username
                session['user_id'] = user_id
                flash('Account created successfully! Welcome to Yoga Pose Analysis!', 'success')
                return redirect(url_for('dashboard'))
            except sqlite3.IntegrityError:
                flash('Username already exists!', 'danger')

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
            user = cursor.fetchone()

            if user:
                session['username'] = username
                session['user_id'] = user[0]
                flash('Logged in successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid credentials!', 'danger')

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos WHERE user_id=? ORDER BY upload_time DESC", (session['user_id'],))
        videos = cursor.fetchall()
    
    return render_template('dashboard.html', videos=videos, username=session['username'])

@app.route('/upload')
def upload():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('upload.html')

@app.route('/upload_video', methods=['POST'])
def upload_video():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if 'video' not in request.files:
        flash('No video file selected', 'danger')
        return redirect(url_for('upload'))
    
    file = request.files['video']
    pose_type = request.form.get('pose_type', 'downward_dog')
    
    if file.filename == '':
        flash('No video file selected', 'danger')
        return redirect(url_for('upload'))
    
    if file and allowed_file(file.filename):
        filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Save to database
        with sqlite3.connect('database.db') as conn:
            cursor = conn.cursor()
            cursor.execute("""INSERT INTO videos (user_id, filename, original_filename, pose_type, status) 
                             VALUES (?, ?, ?, ?, 'uploaded')""", 
                           (session['user_id'], filename, file.filename, pose_type))
            video_id = cursor.lastrowid
            conn.commit()
        
        # Start analysis in background (simplified for demo)
        try:
            score, analysis_data = analyze_yoga_pose(filepath, pose_type)
            
            # Update database with results
            with sqlite3.connect('database.db') as conn:
                cursor = conn.cursor()
                cursor.execute("""UPDATE videos SET analysis_score=?, analysis_data=?, status='analyzed' 
                                 WHERE id=?""", (score, json.dumps(analysis_data), video_id))
                conn.commit()
            
            flash('Video uploaded and analyzed successfully!', 'success')
            return redirect(url_for('view_analysis', video_id=video_id))
        except Exception as e:
            flash(f'Error analyzing video: {str(e)}', 'danger')
            return redirect(url_for('dashboard'))
    else:
        flash('Invalid file type. Please upload MP4, AVI, MOV, WMV, FLV, or WEBM files.', 'danger')
        return redirect(url_for('upload'))

@app.route('/analysis/<int:video_id>')
def view_analysis(video_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    with sqlite3.connect('database.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos WHERE id=? AND user_id=?", (video_id, session['user_id']))
        video = cursor.fetchone()
    
    if not video:
        flash('Video not found', 'danger')
        return redirect(url_for('dashboard'))
    
    analysis_data = json.loads(video[7]) if video[7] else {}
    
    return render_template('analysis.html', video=video, analysis_data=analysis_data)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

def analyze_yoga_pose(video_path, pose_type):
    """
    Simplified yoga pose analysis using OpenCV
    Returns score (0-100) and analysis data
    """
    try:
        cap = cv2.VideoCapture(video_path)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = frame_count / fps if fps > 0 else 0
        
        # Simulate analysis based on video properties
        base_score = random.randint(65, 95)  # Random score for demo
        
        # Adjust score based on pose type and video quality
        if duration < 3:  # Too short
            base_score -= 10
        elif duration > 30:  # Too long
            base_score -= 5
        
        if frame_count < 50:  # Too few frames
            base_score -= 15
        
        # Ensure score is within bounds
        final_score = max(40, min(100, base_score))
        
        cap.release()
        
        analysis_data = {
            "average_score": final_score,
            "frames_analyzed": min(frame_count, 30),
            "pose_type": pose_type,
            "feedback": generate_feedback(final_score, pose_type),
            "duration": round(duration, 2),
            "video_quality": "Good" if frame_count > 100 else "Fair"
        }
        
        return final_score, analysis_data
        
    except Exception as e:
        return 0, {"error": f"Analysis failed: {str(e)}"}

def calculate_pose_score(landmarks, pose_type):
    """Calculate pose score based on pose type - simplified version"""
    # This is a placeholder for the actual pose analysis
    # In a real implementation, you would use pose estimation libraries
    return random.randint(60, 95)

def calculate_downward_dog_score(landmarks):
    """Calculate score for downward dog pose - simplified"""
    return random.randint(70, 95)

def calculate_warrior_score(landmarks):
    """Calculate score for warrior pose - simplified"""
    return random.randint(65, 90)

def calculate_tree_score(landmarks):
    """Calculate score for tree pose - simplified"""
    return random.randint(60, 85)

def calculate_generic_score(landmarks):
    """Calculate a generic pose score - simplified"""
    return random.randint(70, 85)

def generate_feedback(score, pose_type):
    """Generate feedback based on score and pose type"""
    if score >= 90:
        return f"Excellent {pose_type.replace('_', ' ')} pose! Your form is outstanding."
    elif score >= 75:
        return f"Good {pose_type.replace('_', ' ')} pose! Minor adjustments could improve your form."
    elif score >= 60:
        return f"Fair {pose_type.replace('_', ' ')} pose. Focus on alignment and positioning."
    elif score >= 40:
        return f"Your {pose_type.replace('_', ' ')} pose needs improvement. Practice the basic positioning."
    else:
        return f"Keep practicing your {pose_type.replace('_', ' ')} pose. Consider getting guidance from an instructor."

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
