from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
import os
import json
from textblob import TextBlob
import random
from werkzeug.utils import secure_filename
import requests
import re

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///C:/Users/debna/Downloads/virtual interview bot/interviewbot.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def welcome():
    return render_template('welcome.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('interview_type'))
        else:
            flash('Invalid email or password.')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already registered.')
            return redirect(url_for('signup'))
        new_user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('category', None)
    session.pop('interview_type', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

@app.route('/interview_type', methods=['GET', 'POST'])
@login_required
def interview_type():
    if request.method == 'POST':
        session['interview_type'] = request.form['interview_type']
        return redirect(url_for('category'))
    return render_template('interview_type.html', user=current_user)

@app.route('/category', methods=['GET', 'POST'])
@login_required
def category():
    if request.method == 'POST':
        session['category'] = request.form['category']
        session['time_limit'] = int(request.form.get('time_limit', 600))
        session['difficulty'] = request.form.get('difficulty', 'Medium')
        session['challenge'] = 'challenge' in request.form
        
        # Check interview type from session
        interview_type = session.get('interview_type', 'written')
        if interview_type == 'video':
            return redirect(url_for('video_interview'))
        else:
            return redirect(url_for('interview'))
    return render_template('category.html', user=current_user)

@app.route('/interview')
@login_required
def interview():
    if 'category' not in session:
        return redirect(url_for('category'))
    time_limit = session.get('time_limit')
    if not time_limit:
        time_limit = 600  # default 10 min
    difficulty = session.get('difficulty', 'Medium')
    challenge = session.get('challenge', False)
    return render_template('index.html', user=current_user, time_limit=time_limit, difficulty=difficulty, challenge=challenge)

@app.route('/video_interview')
@login_required
def video_interview():
    if 'category' not in session or session.get('interview_type') != 'video':
        return redirect(url_for('category'))
    time_limit = session.get('time_limit')
    if not time_limit:
        time_limit = 600  # default 10 min
    difficulty = session.get('difficulty', 'Medium')
    challenge = session.get('challenge', False)
    return render_template('video_interview.html', user=current_user, time_limit=time_limit, difficulty=difficulty, challenge=challenge)

@app.route('/video_results')
@login_required
def video_results():
    if 'interview_progress' not in session:
        return redirect(url_for('interview_type'))
    
    # Get interview data from session
    summary = session.get('interview_progress', [])
    category = session.get('category', 'General')
    difficulty = session.get('difficulty', 'Medium')
    time_limit = session.get('time_limit', 600)
    
    # Calculate average score
    if summary:
        avg_score = sum(item['score'] for item in summary) / len(summary)
    else:
        avg_score = 0
    
    # Get sample answers
    with open(os.path.join(os.path.dirname(__file__), 'questions.json'), 'r', encoding='utf-8') as f:
        questions = json.load(f)
    
    # Filter questions based on session settings
    if session.get('challenge', False):
        filtered_questions = [q for q in questions if q.get('difficulty', 'Medium') == difficulty]
        random.shuffle(filtered_questions)
    else:
        filtered_questions = [q for q in questions if q.get('category') == category and q.get('difficulty', 'Medium') == difficulty]
    
    samples = [{'q': q['question'], 'a': q.get('answer', 'No sample answer available.')} for q in filtered_questions[:10]]
    
    # Get job recommendations
    try:
        import requests
        keywords = {
            'Technical': 'software engineer',
            'Coding': 'developer',
            'HR': 'human resources',
            'Behavioral': 'project manager',
            'Case Studies': 'consultant',
            'Domain-Specific': 'cloud',
        }
        query = keywords.get(category, 'job')
        resp = requests.get(f'https://remotive.io/api/remote-jobs?search={query}', timeout=5)
        jobs = resp.json().get('jobs', [])[:5]
        job_list = [{
            'title': job.get('title'),
            'company_name': job.get('company_name'),
            'candidate_required_location': job.get('candidate_required_location'),
            'url': job.get('url')
        } for job in jobs]
    except Exception:
        job_list = []
    
    # Calculate time taken (mock for now)
    time_taken = f"{len(summary) * 2} min"
    
    return render_template('video_results.html', 
                         user=current_user,
                         summary=summary, 
                         avg_score=avg_score,
                         samples=samples,
                         jobs=job_list,
                         category=category,
                         difficulty=difficulty,
                         time_taken=time_taken,
                         interview_type="Video")

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json()
    user_answer = data.get('answer', '')
    question_index = data.get('question_index', 0)
    category = session.get('category', None)
    difficulty = session.get('difficulty', 'Medium')
    challenge = session.get('challenge', False)

    # On first question, filter and store the question list in session
    if question_index == -1 or 'interview_questions' not in session:
        with open(os.path.join(os.path.dirname(__file__), 'questions.json'), 'r', encoding='utf-8') as f:
            questions = json.load(f)
        # Filter by difficulty
        if difficulty:
            questions = [q for q in questions if q.get('difficulty', 'Medium') == difficulty]
        # Challenge mode: randomize and mix categories
        if challenge:
            random.shuffle(questions)
        elif category:
            questions = [q for q in questions if q.get('category') == category]
        # Remove duplicate questions by question text
        seen = set()
        unique_questions = []
        for q in questions:
            if q['question'] not in seen:
                unique_questions.append(q)
                seen.add(q['question'])
        session['interview_questions'] = unique_questions
        session['interview_progress'] = []
        session.modified = True
    else:
        questions = session['interview_questions']

    if question_index == -1:
        questions = session['interview_questions']
        return jsonify({
            'score': None,
            'feedback': None,
            'next_question': questions[0]['question'] if questions else 'No questions available.',
            'next_index': 0 if questions else None
        })

    # Improved scoring logic
    blob = TextBlob(user_answer)
    sentiment = blob.sentiment.polarity
    grammar_errors = len(blob.correct().words) - len(blob.words)
    answer_length = len(user_answer.split())
    score = 5
    feedback = []
    # Sentiment
    if sentiment > 0.2:
        score += 1.5
        feedback.append("Positive tone! ")
    elif sentiment < -0.2:
        score -= 1
        feedback.append("Try to sound more positive. ")
    # Grammar
    if grammar_errors == 0:
        score += 1
        feedback.append("No grammar errors. ")
    elif grammar_errors == 1:
        score += 0.5
        feedback.append("Minor grammar issue. ")
    else:
        score -= 0.5
        feedback.append(f"{grammar_errors} grammar issues. ")
    # Length
    if answer_length >= 25:
        score += 1.5
        feedback.append("Great detailed answer! ")
    elif answer_length >= 15:
        score += 1
        feedback.append("Good answer length. ")
    elif answer_length < 5:
        score -= 1
        feedback.append("Try to write a more complete answer. ")
    # Keyword matching (bonus)
    keywords = []
    if 0 <= question_index < len(questions):
        q = questions[question_index]
        if 'answer' in q:
            keywords = [w.lower() for w in q['answer'].split() if len(w) > 4]
    matched = sum(1 for w in set(user_answer.lower().split()) if w in keywords)
    if matched >= 2:
        score += 1
        feedback.append("You used key concepts! ")
    score = min(10, max(1, round(score, 1)))

    # Save progress
    if len(session['interview_progress']) <= question_index:
        session['interview_progress'].append({
            'question': questions[question_index]['question'],
            'answer': user_answer,
            'score': score,
            'feedback': ''.join(feedback)
        })
        session.modified = True
    else:
        session['interview_progress'][question_index] = {
            'question': questions[question_index]['question'],
            'answer': user_answer,
            'score': score,
            'feedback': ''.join(feedback)
        }
        session.modified = True

    if question_index < len(questions) - 1:
        next_question = questions[question_index + 1]['question']
        next_index = question_index + 1
        complete = False
        summary = None
    else:
        next_question = "Interview complete! Thank you for your answers."
        next_index = None
        complete = True
        summary = session['interview_progress']

    # Calculate average score for donut chart
    avg_score = None
    if summary:
        avg_score = round(sum(item['score'] for item in summary) / len(summary), 2)

    response = {
        'score': score,
        'feedback': ''.join(feedback),
        'next_question': next_question,
        'next_index': next_index,
        'complete': complete,
        'summary': summary,
        'avg_score': avg_score
    }
    return jsonify(response)

@app.route('/get_sample_answers')
def get_sample_answers():
    # Use the same question list as the interview
    questions = session.get('interview_questions', None)
    if questions is None:
        # fallback: filter as before
        category = session.get('category', None)
        difficulty = session.get('difficulty', 'Medium')
        challenge = session.get('challenge', False)
        with open(os.path.join(os.path.dirname(__file__), 'questions.json'), 'r', encoding='utf-8') as f:
            questions = json.load(f)
        if difficulty:
            questions = [q for q in questions if q.get('difficulty', 'Medium') == difficulty]
        if challenge:
            random.shuffle(questions)
        elif category:
            questions = [q for q in questions if q.get('category') == category]
    samples = [{'q': q['question'], 'a': q.get('answer', 'No sample answer available.')} for q in questions]
    return jsonify({'samples': samples})

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(filepath):
    ext = filepath.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        try:
            import PyPDF2
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = '\n'.join(page.extract_text() or '' for page in reader.pages)
            if text.strip():
                return text
            # Fallback to OCR if PyPDF2 fails
            try:
                from pdf2image import convert_from_path
                import pytesseract
                from PIL import Image
                images = convert_from_path(filepath)
                ocr_text = ''
                for img in images:
                    ocr_text += pytesseract.image_to_string(img)
                if ocr_text.strip():
                    return ocr_text
            except ImportError:
                return ''  # OCR dependencies not installed
            except Exception:
                return ''
        except Exception:
            return ''
    elif ext == 'docx':
        try:
            import docx
            doc = docx.Document(filepath)
            return '\n'.join([p.text for p in doc.paragraphs])
        except Exception:
            return ''
    elif ext == 'txt':
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return ''

@app.route('/resume_review', methods=['GET', 'POST'])
@login_required
def resume_review():
    feedback = None
    if request.method == 'POST':
        file = request.files.get('resume')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            text = extract_text_from_file(filepath)
            if text:
                blob = TextBlob(text)
                feedback = {
                    'word_count': len(blob.words),
                    'sentiment': round(blob.sentiment.polarity, 2),
                    'grammar_issues': len(blob.correct().words) - len(blob.words),
                    'sample_feedback': "Looks good!" if blob.sentiment.polarity > 0 else "Try to use a more positive tone.",
                    'preview': text[:500] + ('...' if len(text) > 500 else '')
                }
            else:
                feedback = {'error': 'Could not extract text from file.'}
        else:
            feedback = {'error': 'Invalid file type. Please upload PDF, DOCX, or TXT.'}
    return render_template('resume_review.html', user=current_user, feedback=feedback)

@app.route('/get_jobs')
@login_required
def get_jobs():
    category = session.get('category', None)
    # Map your categories to job search keywords
    keywords = {
        'Technical': 'software engineer',
        'Coding': 'developer',
        'HR': 'human resources',
        'Behavioral': 'project manager',
        'Case Studies': 'consultant',
        'Domain-Specific': 'cloud',
    }
    query = keywords.get(category, 'job')
    try:
        resp = requests.get(f'https://remotive.io/api/remote-jobs?search={query}', timeout=5)
        jobs = resp.json().get('jobs', [])[:5]
        job_list = [{
            'title': job.get('title'),
            'company_name': job.get('company_name'),
            'candidate_required_location': job.get('candidate_required_location'),
            'url': job.get('url')
        } for job in jobs]
    except Exception:
        job_list = [
            {
                'title': 'Sample Software Engineer',
                'company_name': 'DemoTech',
                'candidate_required_location': 'Remote',
                'url': 'https://www.example.com/job/software-engineer'
            },
            {
                'title': 'Sample Data Analyst',
                'company_name': 'DataCorp',
                'candidate_required_location': 'Remote/India',
                'url': 'https://www.example.com/job/data-analyst'
            },
            {
                'title': 'Sample HR Specialist',
                'company_name': 'PeopleFirst',
                'candidate_required_location': 'India',
                'url': 'https://www.example.com/job/hr-specialist'
            },
            {
                'title': 'Sample Project Manager',
                'company_name': 'ManageIt',
                'candidate_required_location': 'Remote',
                'url': 'https://www.example.com/job/project-manager'
            },
            {
                'title': 'Sample Cloud Consultant',
                'company_name': 'Cloudify',
                'candidate_required_location': 'Remote/Global',
                'url': 'https://www.example.com/job/cloud-consultant'
            }
        ]
    return jsonify({'jobs': job_list})

def extract_keywords(text):
    stopwords = set(['the', 'and', 'with', 'from', 'that', 'this', 'which', 'such', 'into', 'over', 'under', 'for', 'are', 'was', 'has', 'have', 'had', 'but', 'not', 'can', 'will', 'would', 'should', 'could', 'their', 'them', 'then', 'than', 'also', 'been', 'being', 'were', 'when', 'where', 'what', 'why', 'how', 'who', 'whose', 'while', 'does', 'did', 'doing', 'done', 'use', 'using', 'used', 'by', 'on', 'in', 'to', 'of', 'as', 'is', 'it', 'at', 'or', 'an', 'a'])
    words = re.findall(r'\b\w+\b', text.lower())
    return set(w for w in words if len(w) > 4 and w not in stopwords)

if __name__ == '__main__':
    app.run(debug=True)