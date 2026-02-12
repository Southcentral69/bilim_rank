import os
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from config import Config
from models import db, Admin, Student, SavedRating
from grades_processor import allowed_file, process_grades_file
import pandas as pd
import io
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

# init db
db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# ensure folders exist
if not os.path.exists(app.config.get("UPLOAD_FOLDER", "uploads")):
    os.makedirs(app.config.get("UPLOAD_FOLDER", "uploads"))
os.makedirs('data', exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

# Создаём таблицы при старте приложения
with app.app_context():
    db.create_all()

    # создаём аккаунт админа, если нет (пароль: admin123 — сменить обязательно)
    if not Admin.query.filter_by(username="admin").first():
        a = Admin(username="admin")
        a.set_password("admin123")
        db.session.add(a)
        db.session.commit()
        print("Created default admin user: admin / admin123 — смените пароль!")

# -----------------------
# РОУТЫ
# -----------------------

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = Admin.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Неверный логин или пароль", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))
@app.route('/login_guest')
def login_guest():
    # логика гость-входа, например:
    # session['user_type'] = 'guest'
    return redirect(url_for('dashboard'))  # либо нужная страница

# Главная — выбор параллели (1..11). НЕ требует логина (можно посмотреть рейтинги).
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/reflection")
def reflection():
    return render_template("reflection.html")

# Гостевой просмотр — показывает сохранённые рейтинги (последние)
@app.route("/guest")
def guest():
    # читаем из SavedRating, но если пусто — попробуем data/all_classes.csv
    ratings = SavedRating.query.order_by(SavedRating.place).all()
    if not ratings:
        csv_path = Path("data/all_classes.csv")
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            students = df.to_dict(orient='records')
            return render_template("dashboard.html", students=students, guest=True)
        flash("Рейтингов пока нет (админ ещё не загрузил файлы).", "info")
        return render_template("dashboard.html", students=[], guest=True)

    students = [{
        "name": r.student_name,
        "class": r.klass,
        "average": r.average,
        "place": r.place,
        "korean_rating": r.korean_rating,
        "parallel": r.parallel
    } for r in ratings]
    return render_template("dashboard.html", students=students, guest=True)

# Страница просмотра рейтинга для конкретной параллели (например /class/5)
# Делаем универсально: если есть логин — читаем из Student; если гость — читаем из SavedRating/CSV
@app.route("/class/<int:grade>")
def class_view(grade):
    if current_user.is_authenticated:
        filt = Student.query.filter(Student.klass.like(f"{grade}%"))
        students = filt.order_by(Student.place).all()
        # Передаём объекты SQLAlchemy, шаблон dashboard.html должен уметь работать и с ними
        return render_template("dashboard.html", grade=grade, students=students)
    else:
        # гость — ищем в SavedRating
        filt = SavedRating.query.filter(SavedRating.klass.like(f"{grade}%"))
        ratings = filt.order_by(SavedRating.place).all()
        if ratings:
            students = [{
                "name": r.student_name,
                "class": r.klass,
                "average": r.average,
                "place": r.place,
                "korean_rating": r.korean_rating
            } for r in ratings]
            return render_template("dashboard.html", grade=grade, students=students, guest=True)
        # fallback: пробуем CSV
        csv_path = Path("data/all_classes.csv")
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df_grade = df[df['class'].astype(str).str.startswith(str(grade))]
            students = df_grade.sort_values("place").to_dict(orient='records')
            return render_template("dashboard.html", grade=grade, students=students, guest=True)
        flash("Рейтингов для этой параллели пока нет.", "info")
        return render_template("dashboard.html", grade=grade, students=[], guest=True)

# Админ-панель (всё записи) — требует логина
@app.route("/dashboard")
@login_required
def dashboard():
    # показываем последние загруженные рейтинги (вся таблица)
    students = Student.query.order_by(Student.place).all()
    return render_template("dashboard.html", students=students)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    files = request.files.getlist('file')

    if not files or files[0].filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('dashboard'))

    all_data = []

    for file in files:
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config.get("UPLOAD_FOLDER", "uploads"), filename)
            file.save(filepath)

            df = process_grades_file(filepath)
            # process_grades_file должен возвращать DataFrame с колонками:
            # ['name'/'ФИО', 'class' или 'class', 'average'] — подстроиться под твою реализацию
            all_data.append(df)

    # 🔹 Объединяем все классы в один DataFrame
    if all_data:
        full_data = pd.concat(all_data, ignore_index=True)
        # Приводим колонки к предсказуемым именам (настраивай под свою функцию)
        # Попробуем стандартные варианты:
        if 'average' not in full_data.columns:
            if 'Средний балл' in full_data.columns:
                full_data = full_data.rename(columns={'Средний балл': 'average'})
        if 'name' not in full_data.columns:
            if 'ФИО' in full_data.columns:
                full_data = full_data.rename(columns={'ФИО': 'name'})
        if 'class' not in full_data.columns:
            if 'Класс' in full_data.columns:
                full_data = full_data.rename(columns={'Класс': 'class'})

        # Убедимся, что есть нужные колонки
        required = ['name', 'class', 'average']
        for col in required:
            if col not in full_data.columns:
                flash(f"В обработанных данных отсутствует колонка '{col}'. Проверь шаблон обработчика.", "danger")
                return redirect(url_for('dashboard'))

        # 🔹 Сортируем по среднему баллу и пересчитываем рейтинг по всем
        full_data = full_data.sort_values("average", ascending=False).reset_index(drop=True)
        full_data["place"] = full_data.index + 1

        total = len(full_data)
        def korean_rating(rank):
            p = (rank / total) * 100
            if p <= 4: return 1
            if p <= 11: return 2
            if p <= 23: return 3
            if p <= 40: return 4
            if p <= 60: return 5
            if p <= 77: return 6
            if p <= 89: return 7
            if p <= 96: return 8
            return 9

        full_data["korean_rating"] = full_data["place"].apply(korean_rating)

        # Если нет столбца parallel — попытаемся извлечь из class (например '6A' -> '6')
        if 'parallel' not in full_data.columns:
            full_data['parallel'] = full_data['class'].astype(str).str.extract(r'(^\d{1,2})')[0].fillna('')

        # Сохраняем объединённые данные в CSV
        os.makedirs('data', exist_ok=True)
        full_data_for_csv = full_data.rename(columns={'class': 'class'})  # оставляем названия
        full_data_for_csv.to_csv('data/all_classes.csv', index=False)

        # -------------------------------
        # Сохранение в базу: Student и SavedRating
        # Вариант: полностью обновляем таблицы (удаляем старые записи и добавляем новые)
        # -------------------------------
        try:
            # удаляем старые записи (можно сделать более тонко — удалять только определённые параллели)
            Student.query.delete()
            SavedRating.query.delete()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка очистки таблиц: {e}", "danger")
            return redirect(url_for('dashboard'))

        # добавляем новые записи
        try:
            for _, row in full_data.iterrows():
                name = str(row.get('name', '')).strip()
                klass = str(row.get('class', '')).strip()
                avg = float(row.get('average', 0))
                place = int(row.get('place', 0))
                kr = int(row.get('korean_rating', 0))
                parallel = str(row.get('parallel', '')).strip()

                s = Student(
                    external_id=None,
                    name=name,
                    klass=klass,
                    average=avg,
                    place=place,
                    korean_rating=kr,
                    uploaded_at=datetime.utcnow()
                )
                db.session.add(s)

                sr = SavedRating(
                    student_name=name,
                    klass=klass,
                    parallel=parallel,
                    average=avg,
                    korean_rating=kr,
                    place=place,
                    saved_at=datetime.utcnow()
                )
                db.session.add(sr)

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при записи в БД: {e}", "danger")
            return redirect(url_for('dashboard'))

        # 🔹 Передаём объединённый рейтинг в шаблон (как список dict)
        students = full_data.to_dict(orient='records')
        flash(f'Успешно загружено {len(full_data)} учеников из {len(files)} файлов', 'success')
        return render_template('dashboard.html', students=students)

    flash('Ошибка при обработке файлов', 'danger')
    return redirect(url_for('dashboard'))

# Публичный API для получения сохранённых рейтингов (использует CSV если есть)
@app.route('/api/ratings')
def api_ratings():
    csv_path = Path('data/all_classes.csv')
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        return jsonify(df.to_dict(orient='records'))
    # fallback: из БД
    ratings = SavedRating.query.order_by(SavedRating.place).all()
    if not ratings:
        return jsonify({"error": "Нет данных"}), 404
    return jsonify([{
        "name": r.student_name,
        "class": r.klass,
        "average": r.average,
        "place": r.place,
        "korean_rating": r.korean_rating
    } for r in ratings])

@app.route("/export/csv")
@login_required
def export_csv():
    # Поддержка ?grade=<n> (опционально)
    grade = request.args.get("grade")
    query = Student.query
    if grade:
        # использовать LIKE, чтобы поймать '5', '5A', '5 Б' и т.п.
        query = query.filter(Student.klass.like(f"{grade}%"))
    students = query.order_by(Student.place).all()
    df = pd.DataFrame([{
        "external_id": s.external_id,
        "name": s.name,
        "class": s.klass,
        "average": s.average,
        "place": s.place,
        "korean_rating": s.korean_rating
    } for s in students])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(io.BytesIO(buf.getvalue().encode("utf-8")), mimetype="text/csv",
                     as_attachment=True, download_name="ratings_export.csv")

if __name__ == "__main__":
    app.run(debug=True)
