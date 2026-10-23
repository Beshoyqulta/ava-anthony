import os
import secrets
import json
import re
from io import BytesIO
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import jwt
import qrcode
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, text
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
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 240,
    "pool_timeout": 30,
    "pool_size": 3,
    "max_overflow": 5,
}
db = SQLAlchemy(app)
frontend_origin = os.getenv("FRONTEND_ORIGIN", "*")
if frontend_origin != "*":
    parsed_origin = urlsplit(frontend_origin)
    if parsed_origin.scheme and parsed_origin.netloc:
        frontend_origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"
cors_options = {
    "origins": frontend_origin,
    "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"],
}
CORS(app, resources={r"/api/*": cors_options})


@app.before_request
def handle_api_preflight():
    if request.method == "OPTIONS" and request.path.startswith("/api/"):
        return ("", 204)


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
    # Legacy database column kept populated for compatibility with databases
    # created before the approval workflow was removed.
    approval_status = db.Column(db.String(24), default="approved", nullable=False)
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
    student = db.relationship("Student")
    badge = db.relationship("Badge")


class PointAward(db.Model):
    """Manual point adjustments made by a member of the admin team."""
    __tablename__ = "point_awards"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    awarded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    awarded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    student = db.relationship("Student")
    admin = db.relationship("User", foreign_keys=[awarded_by])


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


class QRSession(db.Model):
    """A short-lived QR display opened by a خادم for one catalog طايو."""
    __tablename__ = "qr_sessions"
    id = db.Column(db.Integer, primary_key=True)
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id"), nullable=False)
    opened_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(96), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    opened_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)
    badge = db.relationship("Badge")


BADGE_SEED = [
    ("أهلًا بيك", "للحضور", 1, "BADGE-001", "assets/badges/hello-jesus.jpg", "الخدمة نورت"),
    ("برافو عليك", "للمشاركة أثناء الفصل", 5, "BADGE-002", "assets/badges/good-job-peter.jpg", "الله ينور"),
    ("عندك موهبة", "لعمل شيء استثنائي", 25, "BADGE-003", "assets/badges/talent-luke-icon.jpg", "اهتم بموهبتك"),
    ("وحشتنا", "عند الغياب أسبوعين متتاليين", 2, "BADGE-004", "assets/badges/miss-you.jpg", "وحشتنا"),
    ("عيد ميلاد سعيد", "في عيد ميلاد المخدوم", 30, "BADGE-005", "assets/badges/birthday.avif", "كل سنة وإنت ماشي مع يسوع"),
    ("حضور القداس", "لحضور القداس", 5, "BADGE-006", "assets/badges/mass-mark.jpg", "تعيش وتصلي"),
    ("شماس أمين", "للخدمة كشماس", 5, "BADGE-007", "assets/badges/deacon-stephen.jpg", "تعيش وتخدم"),
    ("تعيشي وتحضري بدري", "للحضور المبكر — مخصصة للبنات", 5, "BADGE-008", "assets/badges/hello-mary.jpg", "تعيش وتصلي"),
    ("الاعتراف", "للشجاعة في الاعتراف بالخطايا", 15, "BADGE-009", "assets/badges/confession.jpg", "لاَ تَسْتَحِي أَنْ تَعْتَرِفَ بِخَطَايَاكَ، وَلاَ تُغَالِبْ مَجْرَى النَّهْرِ (سفر يشوع بن سيراخ 4: 31)"),
    ("اسمو ابشويس", "للتسبيح وتمجيد الرب", 5, "BADGE-010", "assets/badges/asmou-abshweis.jpeg", "سبحوا الربَّ يا جميع الأمم ولتباركه كافة الشعوب. لأن رحمته قد ثبتت علينا وحق الرب يدوم إلى الأبد هلليلويا."),
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


def valid_phone_input(phone):
    raw = str(phone or "").strip()
    return bool(re.fullmatch(r"\+?[0-9][0-9\s-]*", raw))


def parse_date(value):
    return date.fromisoformat(value) if value else None


def user_json(user):
    return {"id": user.id, "full_name": user.full_name, "phone_number": user.phone_number, "birthday": user.birthday.isoformat() if user.birthday else None, "role": user.role, "status": user.status}


def student_json(student):
    return {**user_json(student.user), "student_id": student.id, "total_points": student.total_points, "badge_count": student.badge_count}


def badge_json(badge):
    return {"id": badge.id, "name": badge.name, "reason": badge.reason, "points": badge.points, "code": badge.code, "image_path": badge.image_path, "claim_message": badge.claim_message, "is_active": badge.is_active}


def award_birthday_badge_if_due(user):
    """Award the birthday طايو once per Sunday-school year after its birthday."""
    if user.role != "student" or not user.birthday or not user.student_profile:
        return None

    today = datetime.now(ZoneInfo("Africa/Cairo")).date()
    school_year_start = date(today.year, 9, 21)
    if today < school_year_start:
        school_year_start = date(today.year - 1, 9, 21)

    birthday_this_cycle = date(
        school_year_start.year if user.birthday.month >= 9 else school_year_start.year + 1,
        user.birthday.month,
        user.birthday.day,
    )
    if birthday_this_cycle < school_year_start or birthday_this_cycle > today:
        return None

    school_year_label = f"{school_year_start.year}-{school_year_start.year + 1}"
    note = f"birthday:auto:{school_year_label}"
    if StudentBadge.query.filter_by(student_id=user.student_profile.id, note=note).first():
        return None

    badge = Badge.query.filter_by(code="BADGE-005", is_active=True).first()
    if not badge:
        return None

    student = user.student_profile
    db.session.add(StudentBadge(
        student_id=student.id,
        badge_id=badge.id,
        awarded_by=None,
        points_awarded=badge.points,
        note=note,
    ))
    student.total_points += badge.points
    student.badge_count += 1
    db.session.commit()
    return badge


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
    requested_role = data.get("role", "student")
    if requested_role != "student":
        return jsonify(error="إنشاء حسابات الخدام يتم يدويًا فقط"), 403
    if not name or not valid_phone_input(data.get("phone_number")) or not phone or len(password) < 8:
        return jsonify(error="الاسم ورقم الهاتف وكلمة مرور من 8 أحرف مطلوبة"), 400
    if User.query.filter_by(phone_number=phone).first():
        return jsonify(error="رقم الهاتف مستخدم بالفعل"), 409
    user = User(full_name=name, phone_number=phone, birthday=parse_date(data.get("birthday")), password_hash=generate_password_hash(password, method="pbkdf2:sha256"), role="student", status="active")
    db.session.add(user)
    db.session.flush()
    db.session.add(Student(user_id=user.id))
    db.session.commit()
    return jsonify(message="تم إنشاء حساب المخدوم", user=user_json(user)), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    if not valid_phone_input(data.get("phone_number")):
        return jsonify(error="استخدم أرقام الهاتف الإنجليزية فقط"), 400
    user = User.query.filter_by(phone_number=normalize_phone(data.get("phone_number"))).first()
    if not user or not check_password_hash(user.password_hash, data.get("password", "")):
        return jsonify(error="رقم الهاتف أو كلمة المرور غير صحيح"), 401
    if user.status != "active" or user.role not in {"admin", "student"}:
        return jsonify(error="الحساب غير مفعل"), 403
    birthday_badge = award_birthday_badge_if_due(user)
    return jsonify(
        token=token_for(user),
        user=user_json(user),
        birthday_awarded=bool(birthday_badge),
        birthday_badge=badge_json(birthday_badge) if birthday_badge else None,
    )


@app.post("/api/auth/forgot-password")
def forgot_password():
    """Temporary self-service reset until SMS/OTP delivery is connected."""
    data = request.get_json(silent=True) or {}
    phone = normalize_phone(data.get("phone_number"))
    birthday = parse_date(data.get("birthday"))
    new_password = data.get("new_password", "")
    user = User.query.filter_by(phone_number=phone).first()
    if not valid_phone_input(data.get("phone_number")) or not user or not birthday or user.birthday != birthday or len(new_password) < 8:
        return jsonify(error="بيانات استعادة الحساب غير صحيحة"), 400
    user.password_hash = generate_password_hash(new_password, method="pbkdf2:sha256")
    db.session.commit()
    return jsonify(message="تم تغيير كلمة المرور بنجاح")


@app.get("/api/me")
@require_roles("admin", "student")
def me(user):
    award_birthday_badge_if_due(user)
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
    session_token = str(data.get("session_token", "")).strip()
    session = QRSession.query.filter_by(token=session_token, is_active=True).first() if session_token else None
    last_seen = session.last_seen_at.replace(tzinfo=timezone.utc) if session and session.last_seen_at.tzinfo is None else (session.last_seen_at if session else None)
    if session and last_seen < datetime.now(timezone.utc) - timedelta(seconds=60):
        session.is_active = False
        session.closed_at = datetime.now(timezone.utc)
        db.session.commit()
        session = None
    if not session:
        return jsonify(error="جلسة الـ QR غير مفتوحة أو انتهت"), 410
    badge = session.badge if session.badge and session.badge.is_active else None
    student = user.student_profile
    if not badge or not student:
        return jsonify(error="كود الطايو غير صحيح"), 404
    award = StudentBadge(student_id=student.id, badge_id=badge.id, awarded_by=user.id, points_awarded=badge.points, note=data.get("note"))
    db.session.add(award)
    db.session.add(QRScan(badge_id=badge.id, student_id=student.id, status="success"))
    student.total_points += badge.points
    student.badge_count += 1
    db.session.commit()
    return jsonify(message=badge.claim_message or "الخدمة نورت", points_added=badge.points, total_points=student.total_points, badge=badge_json(badge))


@app.post("/api/qr-sessions")
@require_roles("admin")
def open_qr_session(user):
    data = request.get_json(silent=True) or {}
    badge = db.session.get(Badge, data.get("badge_id"))
    if not badge or not badge.is_active:
        return jsonify(error="الطايو غير موجود"), 404
    # A خادم can display only one active QR at a time. Opening another one
    # automatically closes the previous display.
    QRSession.query.filter_by(opened_by=user.id, is_active=True).update({"is_active": False, "closed_at": datetime.now(timezone.utc)})
    session = QRSession(badge_id=badge.id, opened_by=user.id, token=secrets.token_urlsafe(32))
    db.session.add(session)
    db.session.commit()
    return jsonify(session={"id": session.id, "token": session.token, "badge": badge_json(badge), "is_active": True}), 201


@app.post("/api/qr-sessions/<string:token>/close")
@require_roles("admin")
def close_qr_session(user, token):
    session = QRSession.query.filter_by(token=token, opened_by=user.id, is_active=True).first()
    if not session:
        return jsonify(error="جلسة QR غير موجودة أو مغلقة بالفعل"), 404
    session.is_active = False
    session.closed_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(message="تم إغلاق كود QR")


@app.post("/api/qr-sessions/<string:token>/heartbeat")
@require_roles("admin")
def heartbeat_qr_session(user, token):
    session = QRSession.query.filter_by(token=token, opened_by=user.id, is_active=True).first()
    if not session:
        return jsonify(error="جلسة QR غير موجودة أو مغلقة بالفعل"), 404
    session.last_seen_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(is_active=True)


@app.get("/api/qr-sessions/<string:token>/image")
def qr_session_image(token):
    """Render the active session as a PNG; inactive sessions cannot render."""
    session = QRSession.query.filter_by(token=token, is_active=True).first()
    last_seen = session.last_seen_at.replace(tzinfo=timezone.utc) if session and session.last_seen_at.tzinfo is None else (session.last_seen_at if session else None)
    if not session or last_seen < datetime.now(timezone.utc) - timedelta(seconds=60):
        if session:
            session.is_active = False
            session.closed_at = datetime.now(timezone.utc)
            db.session.commit()
        return jsonify(error="جلسة QR غير مفتوحة"), 404

    payload = {"type": "ava-anthony-qr", "session_token": session.token}
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return send_file(output, mimetype="image/png", max_age=0)


@app.get("/api/students")
@require_roles("admin")
def students(_user):
    rows = Student.query.join(User).order_by(Student.total_points.desc(), User.full_name.asc()).all()
    return jsonify(students=[student_json(s) for s in rows])


@app.get("/api/students/<int:student_id>")
@require_roles("admin", "student")
def student_detail(user, student_id):
    student = db.session.get(Student, student_id)
    if not student or (user.role == "student" and user.student_profile.id != student_id):
        return jsonify(error="المخدوم غير موجود"), 404
    awards = StudentBadge.query.filter_by(student_id=student_id).order_by(StudentBadge.awarded_at.desc()).all()
    return jsonify(student=student_json(student), badges=[{**badge_json(a.badge), "award_id": a.id, "awarded_at": a.awarded_at.isoformat(), "points_awarded": a.points_awarded} for a in awards])


@app.delete("/api/students/<int:student_id>/badges/<int:award_id>")
@require_roles("admin")
def remove_student_badge(_user, student_id, award_id):
    student = db.session.get(Student, student_id)
    award = db.session.get(StudentBadge, award_id)
    if not student or not award or award.student_id != student_id:
        return jsonify(error="الطايو غير موجود لهذا المخدوم"), 404
    student.total_points -= award.points_awarded
    student.badge_count = max(0, student.badge_count - 1)
    db.session.delete(award)
    db.session.commit()
    return jsonify(message="تم حذف الطايو", total_points=student.total_points, badge_count=student.badge_count)


@app.post("/api/students/<int:student_id>/points")
@require_roles("admin")
def award_points(user, student_id):
    data = request.get_json(silent=True) or {}
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify(error="المخدوم غير موجود"), 404
    badge = db.session.get(Badge, data.get("badge_id")) if data.get("badge_id") else None
    if badge and badge.is_active:
        award = StudentBadge(
            student_id=student.id,
            badge_id=badge.id,
            awarded_by=user.id,
            points_awarded=badge.points,
            note="manual",
        )
        student.total_points += badge.points
        student.badge_count += 1
        db.session.add(award)
        db.session.commit()
        return jsonify(
            message="تم منح الطايو للمخدوم",
            points_added=badge.points,
            total_points=student.total_points,
            badge_count=student.badge_count,
            badge=badge_json(badge),
        ), 201
    else:
        reason = str(data.get("reason", "")).strip()
        try:
            points = int(data.get("points", 0))
        except (TypeError, ValueError):
            points = 0
    if points == 0 or abs(points) > 10000 or not reason or len(reason) > 255:
        return jsonify(error="اختر طايوًا صالحًا" if data.get("badge_id") else "بيانات النقاط غير صحيحة"), 400
    award = PointAward(student_id=student.id, awarded_by=user.id, points=points, reason=reason)
    student.total_points += points
    db.session.add(award)
    db.session.commit()
    return jsonify(
        message="تم تحديث نقاط المخدوم",
        points_added=points,
        total_points=student.total_points,
        award={"id": award.id, "student_id": student.id, "points": award.points, "reason": award.reason, "awarded_at": award.awarded_at.isoformat(), "awarded_by": user.full_name},
    ), 201


@app.get("/api/students/<int:student_id>/points")
@require_roles("admin")
def point_history(_user, student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify(error="المخدوم غير موجود"), 404
    rows = PointAward.query.filter_by(student_id=student.id).order_by(PointAward.awarded_at.desc()).all()
    return jsonify(points=[{"id": row.id, "student_id": row.student_id, "points": row.points, "reason": row.reason, "awarded_at": row.awarded_at.isoformat(), "awarded_by": row.admin.full_name} for row in rows])


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
        else:
            badge.claim_message = message
            badge.name = name
            badge.reason = reason
            badge.points = points
            badge.image_path = image
    db.session.commit()


def migrate_legacy_schema():
    """Remove the old one-award-per-badge constraint from deployed databases."""
    if db.engine.dialect.name != "postgresql":
        return
    try:
        db.session.execute(text("ALTER TABLE student_badges DROP CONSTRAINT IF EXISTS uq_student_badge_once"))
        db.session.commit()
    except Exception:
        db.session.rollback()


def migrate_manual_points_to_badges():
    """Convert older positive manual point records into visible badge awards."""
    for point_award in PointAward.query.filter(PointAward.points > 0).order_by(PointAward.id).all():
        marker = f"manual-point-award:{point_award.id}"
        if StudentBadge.query.filter_by(note=marker).first():
            continue

        badge = Badge.query.filter_by(name=point_award.reason, points=point_award.points, is_active=True).first()
        if not badge:
            badge = Badge(
                name=(point_award.reason or "نقاط يدوية")[:160],
                reason="تم تحويلها من نقاط يدوية مسجلة سابقًا",
                points=point_award.points,
                code=f"MANUAL-{point_award.id}",
                claim_message="تم تسجيل الطايو يدويًا",
                is_active=True,
                created_by=point_award.awarded_by,
            )
            db.session.add(badge)
            db.session.flush()

        student = db.session.get(Student, point_award.student_id)
        if not student:
            continue
        db.session.add(StudentBadge(
            student_id=student.id,
            badge_id=badge.id,
            awarded_by=point_award.awarded_by,
            points_awarded=point_award.points,
            awarded_at=point_award.awarded_at,
            note=marker,
        ))
        # The original PointAward already contributed to total_points.
        student.badge_count += 1
    db.session.commit()


with app.app_context():
    seed_database()
    migrate_legacy_schema()
    migrate_manual_points_to_badges()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
