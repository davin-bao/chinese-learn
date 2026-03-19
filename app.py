#!/usr/bin/env python3
"""
中文学习知识付费平台 - ChineseLearn Pro
简化版：使用Session登录
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import random
import hashlib
import json
import os
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chineselearn.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ============== 数据模型 ==============

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(100))
    avatar = db.Column(db.String(500))
    password_hash = db.Column(db.String(200))
    is_vip = db.Column(db.Boolean, default=False)
    vip_expire = db.Column(db.DateTime, nullable=True)
    free_used_today = db.Column(db.Integer, default=0)
    last_free_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    english = db.Column(db.String(500))
    chinese = db.Column(db.String(500))
    options = db.Column(db.String(500))
    correct_index = db.Column(db.Integer)
    difficulty = db.Column(db.String(20))
    category = db.Column(db.String(50))
    source = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))
    is_correct = db.Column(db.Boolean)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)

# ============== 辅助函数 ==============

def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None

app.jinja_env.globals['current_user'] = get_current_user

# ============== 路由 ==============

@app.route('/')
def index():
    user = get_current_user()
    is_vip = False
    
    if user:
        if user.is_vip and user.vip_expire and user.vip_expire > datetime.utcnow():
            is_vip = True
        else:
            # 检查免费次数
            today = datetime.utcnow().date()
            if user.last_free_date and user.last_free_date.date() == today:
                free_remaining = max(0, 3 - user.free_used_today)
            else:
                free_remaining = 3
    else:
        free_remaining = 3
    
    return render_template('index.html', user=user, is_vip=is_vip, free_remaining=free_remaining)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.json.get('username')
        password = request.json.get('password')
        
        if User.query.filter_by(username=username).first():
            return jsonify({'error': '用户名已存在'}), 400
        
        user = User(
            username=username,
            password_hash=hashlib.sha256(password.encode()).hexdigest(),
            email=f'{username}@example.com',
            avatar=f'https://api.dicebear.com/7.x/avataaars/svg?seed={username}'
        )
        db.session.add(user)
        db.session.commit()
        
        session['user_id'] = user.id
        return jsonify({'status': 'ok', 'username': username})
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.json.get('username')
        password = request.json.get('password')
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        user = User.query.filter_by(username=username, password_hash=password_hash).first()
        if not user:
            return jsonify({'error': '用户名或密码错误'}), 401
        
        session['user_id'] = user.id
        return jsonify({'status': 'ok', 'username': username})
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

@app.route('/api/question')
def get_question():
    """获取一道题目"""
    user = get_current_user()
    is_logged_in = user is not None
    is_vip = False
    
    if user:
        if user.is_vip and user.vip_expire and user.vip_expire > datetime.utcnow():
            is_vip = True
        else:
            # 检查免费次数
            today = datetime.utcnow().date()
            if user.last_free_date and user.last_free_date.date() == today:
                if user.free_used_today >= 3 and not is_vip:
                    return jsonify({
                        'error': 'free_limit',
                        'message': '今日免费次数已用完，请登录或升级VIP',
                        'is_vip': False
                    })
            else:
                user.free_used_today = 0
                user.last_free_date = datetime.utcnow()
                db.session.commit()
    
    question = Question.query.order_by(db.func.random()).first()
    if not question:
        return jsonify({'error': 'no_questions', 'message': '暂无题目'})
    
    options = json.loads(question.options)
    
    return jsonify({
        'id': question.id,
        'english': question.english,
        'chinese': question.chinese,
        'options': options,
        'difficulty': question.difficulty,
        'category': question.category,
        'is_vip': is_vip,
        'is_logged_in': is_logged_in
    })

@app.route('/api/answer', methods=['POST'])
def submit_answer():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'not_logged_in', 'message': '请先登录'}), 401
    
    data = request.json
    question_id = data.get('question_id')
    answer_index = data.get('answer_index')
    
    question = Question.query.get(question_id)
    if not question:
        return jsonify({'error': 'not_found'})
    
    is_correct = answer_index == question.correct_index
    
    progress = UserProgress(
        user_id=user.id,
        question_id=question_id,
        is_correct=is_correct
    )
    db.session.add(progress)
    
    # 更新免费次数
    today = datetime.utcnow().date()
    if not (user.is_vip and user.vip_expire and user.vip_expire > datetime.utcnow()):
        if not user.last_free_date or user.last_free_date.date() != today:
            user.free_used_today = 1
            user.last_free_date = datetime.utcnow()
        else:
            user.free_used_today += 1
    
    db.session.commit()
    
    return jsonify({
        'correct': is_correct,
        'correct_answer': question.correct_index,
        'chinese': question.chinese
    })

@app.route('/vip')
def vip_page():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    return render_template('vip.html', user=user)

@app.route('/api/vip/buy', methods=['POST'])
def buy_vip():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'not_logged_in'}), 401
    
    data = request.json
    plan = data.get('plan', 'monthly')
    
    if plan == 'monthly':
        expire = datetime.utcnow() + timedelta(days=30)
    else:
        expire = datetime.utcnow() + timedelta(days=365)
    
    user.is_vip = True
    user.vip_expire = expire
    db.session.commit()
    
    return jsonify({
        'status': 'ok',
        'expire': expire.strftime('%Y-%m-%d'),
        'message': 'VIP购买成功！'
    })

@app.route('/api/stats')
def get_stats():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'not_logged_in'})
    
    total = UserProgress.query.filter_by(user_id=user.id).count()
    correct = UserProgress.query.filter_by(user_id=user.id, is_correct=True).count()
    
    return jsonify({
        'total': total,
        'correct': correct,
        'accuracy': round(correct/total*100, 1) if total > 0 else 0,
        'is_vip': user.is_vip,
        'vip_expire': user.vip_expire.strftime('%Y-%m-%d') if user.vip_expire else None
    })

# ============== 内容采集（自动） ==============

def collect_content():
    """自动采集内容生成题目"""
    # 这里可以接入各种API获取内容
    # 目前使用预设内容
    pass

# ============== 初始化 ==============

def init_db():
    db.create_all()
    
    if Question.query.count() == 0:
        sample_questions = [
            {"english": "Hello, how are you?", "chinese": "你好，你好吗？", "difficulty": "easy", "category": "daily"},
            {"english": "Nice to meet you.", "chinese": "很高兴认识你。", "difficulty": "easy", "category": "daily"},
            {"english": "Good morning!", "chinese": "早上好！", "difficulty": "easy", "category": "daily"},
            {"english": "Thank you very much!", "chinese": "非常感谢！", "difficulty": "easy", "category": "daily"},
            {"english": "What time is it now?", "chinese": "现在几点钟？", "difficulty": "easy", "category": "daily"},
            {"english": "I would like a cup of coffee.", "chinese": "我想要一杯咖啡。", "difficulty": "medium", "category": "travel"},
            {"english": "Where is the nearest subway station?", "chinese": "最近的地铁站在哪里？", "difficulty": "medium", "category": "travel"},
            {"english": "Could you speak more slowly, please?", "chinese": "请你说慢一点好吗？", "difficulty": "medium", "category": "daily"},
            {"english": "I'm interested in learning Chinese.", "chinese": "我对学习中文很感兴趣。", "difficulty": "medium", "category": "study"},
            {"english": "What is your profession?", "chinese": "你的职业是什么？", "difficulty": "medium", "category": "business"},
            {"english": "Let me think about it.", "chinese": "让我考虑一下。", "difficulty": "hard", "category": "business"},
            {"english": "I would appreciate it if you could help me.", "chinese": "如果你能帮助我，我会非常感激。", "difficulty": "hard", "category": "business"},
            {"english": "The weather is quite nice today.", "chinese": "今天的天气非常好。", "difficulty": "easy", "category": "daily"},
            {"english": "I love reading books.", "chinese": "我喜欢读书。", "difficulty": "easy", "category": "hobby"},
            {"english": "Can you recommend a good restaurant?", "chinese": "你能推荐一家好的餐厅吗？", "difficulty": "medium", "category": "travel"},
            {"english": "I'm looking forward to seeing you.", "chinese": "我很期待见到你。", "difficulty": "medium", "category": "daily"},
            {"english": "It takes about 30 minutes by bus.", "chinese": "坐公交车大约需要30分钟。", "difficulty": "medium", "category": "travel"},
            {"english": "I completely agree with your opinion.", "chinese": "我完全同意你的观点。", "difficulty": "hard", "category": "business"},
            {"english": "Please feel free to contact me anytime.", "chinese": "请随时联系我。", "difficulty": "hard", "category": "business"},
            {"english": "Practice makes perfect.", "chinese": "熟能生巧。", "difficulty": "medium", "category": "study"},
        ]
        
        for q in sample_questions:
            all_chinese = [item['chinese'] for item in sample_questions]
            wrong_options = random.sample([c for c in all_chinese if c != q['chinese']], 3)
            options = wrong_options + [q['chinese']]
            random.shuffle(options)
            correct_idx = options.index(q['chinese'])
            
            question = Question(
                english=q['english'],
                chinese=q['chinese'],
                options=json.dumps(options),
                correct_index=correct_idx,
                difficulty=q['difficulty'],
                category=q['category'],
                source='system'
            )
            db.session.add(question)
        
        db.session.commit()
        print(f"✅ 初始化了 {len(sample_questions)} 道题目")

if __name__ == '__main__':
    with app.app_context():
        init_db()
    
    app.run(host='0.0.0.0', port=5000, debug=False)