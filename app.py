import os
import sqlite3
import json
import google.generativeai as genai
from flask import Flask, render_template, request, redirect, url_for, g, abort, Response, flash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_very_secret_key_for_flask'
DATABASE = 'chat_app.db'

# --- Настройка Gemini ---
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    # Используем рабочую модель. Когда 2.5 станет доступна, замените здесь.
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("✅ Модель Gemini успешно сконфигурирована: gemini-1.5-flash")
except Exception as e:
    print(f"❌ Ошибка конфигурации Gemini API: {e}")
    model = None

# --- Функции для работы с БД ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.context_processor
def inject_chats():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, title FROM chats ORDER BY created_at DESC")
    all_chats = cursor.fetchall()
    return dict(all_chats=all_chats)

# --- Маршруты ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat/<int:chat_id>')
def chat(chat_id):
    db = get_db()
    current_chat = db.cursor().execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
    if not current_chat:
        abort(404)
    messages = db.cursor().execute("SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp ASC", (chat_id,)).fetchall()
    display_messages = [msg for msg in messages if msg['role'] != 'system']
    return render_template('chat.html', chat=current_chat, messages=display_messages)

@app.route('/stream_chat/<int:chat_id>', methods=['POST'])
def stream_chat(chat_id):
    print(f"\n🚀 Получен POST-запрос на /stream_chat/{chat_id}")
    user_input = request.form.get('user_input', '').strip()
    if not user_input:
        return Response("Сообщение не может быть пустым.", status=400)

    print(f"💬 Сообщение от пользователя: '{user_input}'")
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, 'user', user_input))
    db.commit()
    print("💾 Сообщение пользователя сохранено в БД.")

    messages = cursor.execute("SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp ASC", (chat_id,)).fetchall()
    history = [{'role': msg['role'], 'parts': [msg['content']]} for msg in messages]
    print(f"📖 Сформирована история из {len(history)} сообщений для API.")

    def generate():
        try:
            print("🧠 Отправка запроса в Gemini API...")
            chat_session = model.start_chat(history=history)
            stream = chat_session.send_message(user_input, stream=True)
            print("🌊 Начало стриминга ответа от Gemini.")
            full_response_text = ""
            for chunk in stream:
                if chunk.text:
                    full_response_text += chunk.text
                    yield f"data: {json.dumps({'text': chunk.text})}\n\n"
            print("✅ Стриминг завершен. Полный ответ получен.")
            db_conn = sqlite3.connect(DATABASE)
            db_conn.cursor().execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (chat_id, 'model', full_response_text))
            db_conn.commit()
            db_conn.close()
            print("💾 Ответ модели сохранен в БД.")
        except Exception as e:
            print(f"❌❌❌ КРИТИЧЕСКАЯ ОШИБКА ВНУТРИ ГЕНЕРАТОРА: {e}")
            yield f"data: {json.dumps({'error': f'Ошибка на сервере: {e}'})}\n\n"
    return Response(generate(), mimetype='text/event-stream')

@app.route('/new_chat', methods=['POST'])
def new_chat():
    system_prompt = request.form['system_prompt'].strip()
    first_message = request.form['first_message'].strip()
    if not first_message:
        return redirect(url_for('index'))
    db = get_db()
    cursor = db.cursor()
    title = first_message[:50] + '...' if len(first_message) > 50 else first_message
    cursor.execute("INSERT INTO chats (title, system_prompt) VALUES (?, ?)", (title, system_prompt))
    new_chat_id = cursor.lastrowid
    if system_prompt:
        cursor.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (new_chat_id, 'user', system_prompt))
        cursor.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (new_chat_id, 'model', "Хорошо, я буду следовать этим инструкциям."))
    cursor.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (new_chat_id, 'user', first_message))
    db.commit()
    messages = cursor.execute("SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp ASC", (new_chat_id,)).fetchall()
    history = [{'role': msg['role'], 'parts': [msg['content']]} for msg in messages]
    chat_session = model.start_chat(history=history)
    response = chat_session.send_message(first_message)
    cursor.execute("INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)", (new_chat_id, 'model', response.text))
    db.commit()
    return redirect(url_for('chat', chat_id=new_chat_id))

@app.route('/delete_chat/<int:chat_id>', methods=['POST'])
def delete_chat(chat_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
    cursor.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    db.commit()
    flash("Чат был успешно удален.", "success")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)