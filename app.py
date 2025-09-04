from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from flask_cors import CORS
import os
import google.generativeai as genai
from dotenv import load_dotenv
from sqlalchemy import case

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configure database
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'todos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configure Gemini
try:
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY not found in .env file")
    
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")  # Note: using gemini-pro instead of gemini-1.5-flash
    GENAI_AVAILABLE = True
except Exception as e:
    print(f"Error configuring Gemini: {str(e)}")
    GENAI_AVAILABLE = False
    model = None

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    priority = db.Column(db.String(20), default='medium')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/todos', methods=['GET'])
def get_todos():
    try:
        # Order by custom priority: high > medium > low, then newest first
        priority_order = case(
            (Todo.priority == 'high', 3),
            (Todo.priority == 'medium', 2),
            (Todo.priority == 'low', 1),
            else_=0
        )
        todos = Todo.query.order_by(priority_order.desc(), Todo.created_at.desc()).all()
        
        # Count tasks by priority
        high_priority = sum(1 for todo in todos if todo.priority == 'high')
        medium_priority = sum(1 for todo in todos if todo.priority == 'medium')
        low_priority = sum(1 for todo in todos if todo.priority == 'low')
        
        return jsonify({
            'todos': [{
                'id': todo.id, 
                'content': todo.content, 
                'priority': todo.priority,
                'created_at': todo.created_at.isoformat()
            } for todo in todos],
            'statistics': {
                'total': len(todos),
                'high_priority': high_priority,
                'medium_priority': medium_priority,
                'low_priority': low_priority
            }
        })
    except SQLAlchemyError as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/todos', methods=['POST'])
def add_todo():
    try:
        data = request.get_json()
        content = data.get('content', '').strip()
        priority = data.get('priority', 'medium')
        if not content:
            return jsonify({'error': 'Content is required'}), 400
        new_todo = Todo(content=content, priority=priority)
        db.session.add(new_todo)
        db.session.commit()
        return jsonify({'id': new_todo.id, 'content': new_todo.content, 'priority': new_todo.priority}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/todos/<int:todo_id>', methods=['DELETE'])
def delete_todo(todo_id):
    try:
        todo = Todo.query.get_or_404(todo_id)
        db.session.delete(todo)
        db.session.commit()
        return jsonify({'message': 'Todo deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/todos/<int:todo_id>', methods=['PUT'])
def update_todo(todo_id):
    try:
        todo = Todo.query.get_or_404(todo_id)
        data = request.get_json()
        
        if 'content' in data:
            new_content = data.get('content', '').strip()
            if not new_content:
                return jsonify({'error': 'Content cannot be empty'}), 400
            todo.content = new_content
            
        if 'priority' in data:
            priority = data.get('priority')
            if priority not in ['high', 'medium', 'low']:
                return jsonify({'error': 'Invalid priority value'}), 400
            todo.priority = priority
            
        db.session.commit()
        return jsonify({
            'id': todo.id,
            'content': todo.content,
            'priority': todo.priority,
            'created_at': todo.created_at.isoformat()
        })
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/assistant', methods=['POST'])
def get_ai_response():
    try:
        if not GENAI_AVAILABLE:
            return jsonify({'error': 'AI assistant is not available'}), 503

        data = request.get_json()
        user_input = data.get('input', '')
        if not user_input:
            return jsonify({'error': 'Empty input'}), 400

        prompt = f"""As a todo list assistant, help with this question: {user_input}"""

        response = model.generate_content(prompt)
        return jsonify({'response': response.text})

    except Exception as e:
        print(f"Error in AI response: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)
