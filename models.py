from datetime import datetime
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# === Администраторы ===
class Admin(UserMixin, db.Model):
    __tablename__ = "admins"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# === Ученики (загруженные из Excel) ===
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(50))
    name = db.Column(db.String(100))
    klass = db.Column(db.String(10))
    parallel = db.Column(db.String(10))  # <-- новая колонка
    average = db.Column(db.Float)
    place = db.Column(db.Integer)
    korean_rating = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


    def __repr__(self):
        return f"<Student {self.name} — {self.klass} ({self.average})>"


# === Таблица сохранённых рейтингов (для гостевого режима) ===
class SavedRating(db.Model):
    __tablename__ = "saved_ratings"
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(256), nullable=False)
    klass = db.Column(db.String(64), nullable=False)
    parallel = db.Column(db.String(32), nullable=True)
    average = db.Column(db.Float, nullable=False)
    korean_rating = db.Column(db.Integer, nullable=False)
    place = db.Column(db.Integer, nullable=False)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<SavedRating {self.student_name} ({self.parallel})>"
