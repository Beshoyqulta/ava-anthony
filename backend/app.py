import os
import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit

import jwt
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'ava_anthony.db')}")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI=DATABASE_URL,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    JWT_SECRET=os.getenv("JWT_SECRET", "development-only-secret"),
)
db = SQLAlchemy(app)
frontend_origin = os.getenv("FRONTEND_ORIGIN", "*")
if frontend_origin != "*":
    parsed_origin = urlsplit(frontend_origin)
    if parsed_origin.scheme and parsed_origin.netloc:
        frontend_origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"
CORS(app, resources={r"/api/*": {"origins": frontend_origin}})


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(160), nullable=False)
    birthday = db.Column(db.Date, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(24), nullable=False, default="student")
    status = db.Column(db.String(24), nullable=False, default="active")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    total_points = db.Column(db.Integer, default=0, nullable=False)
    badge_count = db.Column(db.Integer, default=0, nullable=False)
    user = db.relationship("User", backref=db.backref("student_profile", uselist=False))


class Admin(db.Model):
    __tablename__ = "admins"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("admin_profile", uselist=False))


class Badge(db.Model):
    __tablename__ = "badges"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    points = db.Column(db.Integer, nullable=False)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    image_path = db.Column(db.String(255), nullable=True)
    claim_message = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class StudentBadge(db.Model):
    __tablename__ = "student_badges"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id"), nullable=False)
    awarded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    points_awarded = db.Column(db.Integer, nullable=False)
    awarded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    note = db.Column(db.String(255), nullable=True)
    __table_args__ = (UniqueConstraint("student_id", "badge_id", name="uq_student_badge_once"),)
    student = db.relationship("Student")
    badge = db.relationship("Badge")


class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    class_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(24), nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (UniqueConstraint("student_id", "class_date", name="uq_student_attendance_day"),)
    student = db.relationship("Student")


class QRScan(db.Model):
    __tablename__ = "qr_scans"
    id = db.Column(db.Integer, primary_key=True)
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="success")
    scanned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


BADGE_SEED = [
    ("أهلًا بيك", "للحضور", 1, "BADGE-001", "assets/badges/hello-jesus.jpg", "الخدمة نورت"),
    ("برافو عليك", "للمشاركة أثناء الفصل", 5, "BADGE-002", "assets/badges/good-job-peter.jpg", "الله ينور"),
    ("عندك موهبة", "لعمل شيء استثنائي", 25, "BADGE-003", "assets/badges/talent-luke-icon.jpg", "اهتم بموهبتك"),
    ("وحشتنا", "عند الغياب أسبوعين متتاليين", 2, "BADGE-004", "assets/badges/miss-you.jpg", "وحشتنا"),
    ("عيد ميلاد سعيد", "في عيد ميلاد المخدوم", 30, "BADGE-005", "assets/badges/birthday.jpg", "كل سنة وإنت ماشي مع يسوع"),
    ("حضور القداس", "لحضور القداس", 5, "BADGE-006", "assets/badges/mass-mark.jpg", "تعيش وتصلي"),
    ("شماس أمين", "للخدمة كشماس", 5, "BADGE-007", "assets/badges/deacon-stephen.jpg", "تعيش وتخدم"),
    ("تعيشي وتحضري بدري", "للحضور المبكر — مخصصة للبنات", 5, "BADGE-008", "assets/badges/hello-mary.jpg", "تعيشي وتحضري بدري"),
]


def normalize_phone(phone):
    value = "".join(str(phone or "").split()).replace("-", "")
    if value.startswith("00"):
        value = "+" + value[2:]
    elif value.startswith("01"):
        value = "+20" + value
    elif value.startswith("20"):
        value = "+" + value
    return value


def parse_date(value):
    return date.fromisoformat(value) if value else None


def user_json(user):
    return {"id": user.id, "full_name": user.full_name, "phone_number": user.phone_number, "birthday": user.birthday.isoformat() if user.birthday else None, "role": user.role, "status": user.status}


def student_json(student):
    return {**user_json(student.user), "student_id": student.id, "total_points": student.total_points, "badge_count": student.badge_count}


def badge_json(badge):
    return {"id": badge.id, "name": badge.name, "reason": badge.reason, "points": badge.points, "code": badge.code, "image_path": badge.image_path, "claim_message": badge.claim_message, "is_active": badge.is_active}


def token_for(user):
    payload = {"sub": str(user.id), "role": user.role, "exp": datetime.now(timezone.utc) + timedelta(hours=24)}
    return jwt.encode(payload, app.config["JWT_SECRET"], algorithm="HS256")


def current_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(header[7:], app.config["JWT_SECRET"], algorithms=["HS256"])
        return db.session.get(User, int(payload["sub"]))
    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None


def require_roles(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user or user.status != "active":
                return jsonify(error="تسجيل الدخول مطلوب"), 401
            if roles and user.role not in roles:
                return jsonify(error="ليس لديك صلاحية لهذا الإجراء"), 403
            return fn(user, *args, **kwargs)
        return wrapper
    return decorator


@app.get("/api/health")
def health():
    return jsonify(status="ok", service="ava-anthony-api")


@app.post("/api/auth/signup")
def signup():
    data = request.get_json(silent=True) or {}
    name, phone, password = data.get("full_name", "").strip(), normalize_phone(data.get("phone_number")), data.get("password", "")
    role = data.get("role", "student")
    if not name or not phone or len(password) < 8 or role not in {"student", "admin"}:
        return jsonify(error="الاسم ورقم الهاتف وكلمة مرور من 8 أحرف مطلوبة"), 400
    if User.query.filter_by(phone_number=phone).first():
        return jsonify(error="رقم الهاتف مستخدم بالفعل"), 409
    user = User(full_name=name, phone_number=phone, birthday=parse_date(data.get("birthday")), password_hash=generate_password_hash(password, method="pbkdf2:sha256"), role=role, status="active")
    db.session.add(user)
    db.session.flush()
    if role == "student":
        db.session.add(Student(user_id=user.id))
    else:
        db.session.add(Admin(user_id=user.id))
    db.session.commit()
    return jsonify(message="تم إنشاء حساب المخدوم" if role == "student" else "تم إنشاء حساب الخادم", user=user_json(user)), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    user = User.query.filter_by(phone_number=normalize_phone(data.get("phone_number"))).first()
    if not user or not check_password_hash(user.password_hash, data.get("password", "")):
        return jsonify(error="رقم الهاتف أو كلمة المرور غير صحيح"), 401
    if user.status != "active" or user.role not in {"admin", "student"}:
        return jsonify(error="الحساب غير مفعل"), 403
    return jsonify(token=token_for(user), user=user_json(user))


@app.get("/api/me")
@require_roles("admin", "student")
def me(user):
    return jsonify(user=user_json(user), student=student_json(user.student_profile) if user.student_profile else None)


@app.get("/api/badges")
@require_roles("admin", "student")
def badges(_user):
    return jsonify(badges=[badge_json(b) for b in Badge.query.filter_by(is_active=True).order_by(Badge.id).all()])


@app.post("/api/badges")
@require_roles("admin")
def create_badge(user):
    data = request.get_json(silent=True) or {}
    name, points = data.get("name", "").strip(), int(data.get("points", 0))
    if not name or points < 1:
        return jsonify(error="اسم الطايو وعدد النقاط مطلوبان"), 400
    badge = Badge(name=name, reason=data.get("reason"), points=points, code=data.get("code") or f"BADGE-{secrets.token_hex(4).upper()}", image_path=data.get("image_path"), claim_message=data.get("claim_message"), created_by=user.id)
    db.session.add(badge)
    db.session.commit()
    return jsonify(badge=badge_json(badge)), 201


@app.post("/api/badges/redeem")
@require_roles("student")
def redeem_badge(user):
    data = request.get_json(silent=True) or {}
    badge = Badge.query.filter_by(code=str(data.get("code", "")).upper(), is_active=True).first()
    student = user.student_profile
    if not badge or not student:
        return jsonify(error="كود الطايو غير صحيح"), 404
    if StudentBadge.query.filter_by(student_id=student.id, badge_id=badge.id).first():
        return jsonify(error="تم استلام هذا الطايو من قبل"), 409
    award = StudentBadge(student_id=student.id, badge_id=badge.id, awarded_by=user.id, points_awarded=badge.points, note=data.get("note"))
    db.session.add(award)
    db.session.add(QRScan(badge_id=badge.id, student_id=student.id, status="success"))
    student.total_points += badge.points
    student.badge_count += 1
    db.session.commit()
    return jsonify(message=badge.claim_message or "الخدمة نورت", points_added=badge.points, total_points=student.total_points, badge=badge_json(badge))


@app.get("/api/students")
@require_roles("admin")
def students(_user):
    return jsonify(students=[student_json(s) for s in Student.query.join(User).order_by(User.full_name).all()])


@app.get("/api/students/<int:student_id>")
@require_roles("admin", "student")
def student_detail(user, student_id):
    student = db.session.get(Student, student_id)
    if not student or (user.role == "student" and user.student_profile.id != student_id):
        return jsonify(error="المخدوم غير موجود"), 404
    awards = StudentBadge.query.filter_by(student_id=student_id).order_by(StudentBadge.awarded_at.desc()).all()
    return jsonify(student=student_json(student), badges=[{**badge_json(a.badge), "awarded_at": a.awarded_at.isoformat(), "points_awarded": a.points_awarded} for a in awards])


@app.get("/api/admins")
@require_roles("admin")
def admins(_user):
    rows = Admin.query.join(User, Admin.user_id == User.id).order_by(User.full_name).all()
    return jsonify(admins=[{**user_json(a.user), "admin_id": a.id} for a in rows])


@app.get("/api/leaderboard")
@require_roles("admin", "student")
def leaderboard(_user):
    rows = Student.query.join(User).order_by(Student.total_points.desc(), User.full_name.asc()).all()
    return jsonify(leaderboard=[{"rank": i + 1, "student_id": s.id, "name": s.user.full_name, "points": s.total_points, "badges": s.badge_count} for i, s in enumerate(rows)])


@app.post("/api/attendance")
@require_roles("admin")
def record_attendance(user):
    data = request.get_json(silent=True) or {}
    student, class_date, status = db.session.get(Student, data.get("student_id")), parse_date(data.get("class_date")), data.get("status")
    if not student or not class_date or status not in {"present", "late", "absent"}:
        return jsonify(error="بيانات الحضور غير مكتملة"), 400
    record = Attendance.query.filter_by(student_id=student.id, class_date=class_date).first() or Attendance(student_id=student.id, class_date=class_date, recorded_by=user.id)
    record.status = status
    record.recorded_by = user.id
    db.session.add(record)
    db.session.commit()
    return jsonify(id=record.id, student_id=student.id, class_date=class_date.isoformat(), status=status)


@app.get("/api/attendance")
@require_roles("admin", "student")
def attendance(user):
    query = Attendance.query
    if user.role == "student":
        query = query.filter_by(student_id=user.student_profile.id)
    rows = query.order_by(Attendance.class_date.desc()).all()
    return jsonify(attendance=[{"id": r.id, "student_id": r.student_id, "student_name": r.student.user.full_name, "class_date": r.class_date.isoformat(), "status": r.status} for r in rows])


def seed_database():
    db.create_all()
    for name, reason, points, code, image, message in BADGE_SEED:
        badge = Badge.query.filter_by(code=code).first()
        if not badge:
            db.session.add(Badge(name=name, reason=reason, points=points, code=code, image_path=image, claim_message=message))
    db.session.commit()


with app.app_context():
    seed_database()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
