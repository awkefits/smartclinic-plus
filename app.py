"""SmartClinic+ - patient profiles, role-based login, waiting-room queue."""

import os
from datetime import datetime

import pymysql
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

# --- 1. Setup ---

load_dotenv()  # load .env

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-not-secure")

# Estimated minutes per patient
MINUTES_PER_PATIENT = 15

# Form security (CSRF)
CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"  # redirect if not logged in
login_manager.login_message_category = "danger"

ROLES = ("patient", "doctor", "nurse", "admin")
STAFF = ("doctor", "nurse", "admin")


# --- 2. Database ---

def run_sql(sql, args=(), fetch=None):
    """Run SQL. fetch: "all" = rows, "one" = row, None = new id. Always pass values via %s."""
    connection = pymysql.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "smartclinic_plus"),
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, args)
            if fetch == "all":
                result = cursor.fetchall()
            elif fetch == "one":
                result = cursor.fetchone()
            else:
                result = cursor.lastrowid
        connection.commit()
        return result
    finally:
        connection.close()


# --- 3. Login Helpers ---

class User(UserMixin):
    """Logged-in user."""

    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.email = row["email"]
        self.role = row["role"]


@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login."""
    row = run_sql("SELECT * FROM users WHERE id = %s", (user_id,), "one")
    return User(row) if row else None


def require_role(*allowed_roles):
    """403 unless user has one of these roles."""
    if current_user.role not in allowed_roles:
        abort(403)


def hash_password(password):
    # pbkdf2: scrypt is missing on some Macs
    return generate_password_hash(password, method="pbkdf2:sha256")


def parse_date(text):
    """'YYYY-MM-DD' -> date. Blank -> None."""
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d").date()


def create_user(name, email, password, role, date_of_birth=None, contact_info=None):
    """Add a user (+ profile if patient)."""
    user_id = run_sql(
        "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
        (name, email, hash_password(password), role),
    )
    if role == "patient":
        run_sql(
            "INSERT INTO patient_profiles (user_id, contact_info, date_of_birth) VALUES (%s, %s, %s)",
            (user_id, contact_info, date_of_birth),
        )
    return user_id


def email_taken(email):
    return run_sql("SELECT id FROM users WHERE email = %s", (email,), "one") is not None


def profile_id_of(user_id):
    row = run_sql("SELECT id FROM patient_profiles WHERE user_id = %s", (user_id,), "one")
    return row["id"] if row else None


# --- 4. Login Pages ---

@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Patient sign-up only."""
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        try:
            date_of_birth = parse_date(request.form["date_of_birth"])
        except ValueError:
            flash("Date of birth must be a real date.", "danger")
            return render_template("register.html")

        if not name or not email or not password:
            flash("Name, email and password are required.", "danger")
        elif email_taken(email):
            flash("An account with that email already exists.", "danger")
        else:
            create_user(name, email, password, "patient", date_of_birth,
                        request.form["contact_info"].strip() or None)
            flash("Account created. You can log in now.", "success")
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        row = run_sql("SELECT * FROM users WHERE email = %s", (email,), "one")

        if row and check_password_hash(row["password_hash"], request.form["password"]):
            login_user(User(row))
            return redirect(url_for("dashboard"))
        flash("Wrong email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    my_profile_id = profile_id_of(current_user.id) if current_user.role == "patient" else None
    return render_template("dashboard.html", my_profile_id=my_profile_id)


# --- 5. Patient Pages ---
# Patient: own profile | Doctor/Nurse: view all | Admin: view + edit all

def get_profile_or_404(profile_id):
    profile = run_sql(
        """SELECT p.*, u.name, u.email
           FROM patient_profiles p JOIN users u ON u.id = p.user_id
           WHERE p.id = %s""",
        (profile_id,), "one",
    )
    if profile is None:
        abort(404)
    return profile


@app.route("/patients")
@login_required
def patient_list():
    require_role(*STAFF)
    patients = run_sql(
        """SELECT p.id, p.date_of_birth, u.name, u.email
           FROM patient_profiles p JOIN users u ON u.id = p.user_id
           ORDER BY u.name""",
        fetch="all",
    )
    return render_template("patient_list.html", patients=patients)


@app.route("/patients/<int:profile_id>")
@login_required
def patient_view(profile_id):
    profile = get_profile_or_404(profile_id)
    is_mine = profile["user_id"] == current_user.id
    if not (is_mine or current_user.role in STAFF):
        abort(403)
    can_edit = is_mine or current_user.role == "admin"
    return render_template("patient_view.html", profile=profile, can_edit=can_edit)


@app.route("/patients/<int:profile_id>/edit", methods=["GET", "POST"])
@login_required
def patient_edit(profile_id):
    profile = get_profile_or_404(profile_id)
    if not (profile["user_id"] == current_user.id or current_user.role == "admin"):
        abort(403)

    if request.method == "POST":
        try:
            date_of_birth = parse_date(request.form["date_of_birth"])
        except ValueError:
            flash("Date of birth must be a real date.", "danger")
            return render_template("patient_edit.html", profile=profile)

        run_sql(
            """UPDATE patient_profiles
               SET contact_info = %s, current_medications = %s, date_of_birth = %s
               WHERE id = %s""",
            (request.form["contact_info"].strip() or None,
             request.form["current_medications"].strip() or None,
             date_of_birth, profile_id),
        )
        flash("Profile saved.", "success")
        return redirect(url_for("patient_view", profile_id=profile_id))

    return render_template("patient_edit.html", profile=profile)


# --- 6. Admin Pages ---

@app.route("/users")
@login_required
def user_list():
    require_role("admin")
    users = run_sql("SELECT id, name, email, role FROM users ORDER BY role, name", fetch="all")
    return render_template("user_list.html", users=users)


@app.route("/users/new", methods=["GET", "POST"])
@login_required
def user_new():
    """Admin creates any account."""
    require_role("admin")

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        role = request.form["role"]

        if not name or not email or not password or role not in ROLES:
            flash("Fill in every field and pick a role.", "danger")
        elif email_taken(email):
            flash("An account with that email already exists.", "danger")
        else:
            create_user(name, email, password, role)
            flash(f"{role.title()} account created for {name}.", "success")
            return redirect(url_for("user_list"))

    return render_template("user_new.html", roles=ROLES)


# --- 7. Queue Pages (Waiting Room) ---
# Status: waiting -> in_consultation -> completed (or cancelled)
# Order: urgent first, then earliest. One line per doctor + "any doctor" line.

ACTIVE = ("waiting", "in_consultation")


def get_waiting_list():
    """Waiting list with place and estimated wait."""
    waiting = run_sql(
        """SELECT q.*, u.name AS patient_name, d.name AS doctor_name
           FROM queue_entries q
           JOIN patient_profiles p ON p.id = q.patient_id
           JOIN users u ON u.id = p.user_id
           LEFT JOIN users d ON d.id = q.doctor_id
           WHERE q.status = 'waiting'
           ORDER BY (q.priority = 'urgent') DESC, q.checked_in_at, q.id""",
        fetch="all",
    )
    now = datetime.now()
    people_ahead = {}  # doctor id -> count
    for entry in waiting:
        counted = people_ahead.get(entry["doctor_id"], 0) + 1
        people_ahead[entry["doctor_id"]] = counted
        entry["place"] = counted
        entry["estimated_minutes"] = (counted - 1) * MINUTES_PER_PATIENT
        entry["minutes_waiting"] = int((now - entry["checked_in_at"]).total_seconds() // 60)
    return waiting


def get_entry_or_404(entry_id):
    entry = run_sql(
        """SELECT q.*, p.user_id AS patient_user_id, u.name AS patient_name
           FROM queue_entries q
           JOIN patient_profiles p ON p.id = q.patient_id
           JOIN users u ON u.id = p.user_id
           WHERE q.id = %s""",
        (entry_id,), "one",
    )
    if entry is None:
        abort(404)
    return entry


def active_entry_of(profile_id):
    return run_sql(
        "SELECT * FROM queue_entries WHERE patient_id = %s AND status IN ('waiting', 'in_consultation')",
        (profile_id,), "one",
    )


def back_to_queue():
    """Patient -> own status, staff -> board."""
    if current_user.role == "patient":
        return redirect(url_for("queue_mine"))
    return redirect(url_for("queue_board"))


@app.route("/queue")
@login_required
def queue_board():
    """Staff waiting-room board."""
    require_role(*STAFF)
    in_consultation = run_sql(
        """SELECT q.*, u.name AS patient_name, d.name AS doctor_name
           FROM queue_entries q
           JOIN patient_profiles p ON p.id = q.patient_id
           JOIN users u ON u.id = p.user_id
           LEFT JOIN users d ON d.id = q.doctor_id
           WHERE q.status = 'in_consultation'
           ORDER BY q.called_at""",
        fetch="all",
    )
    return render_template("queue_board.html", waiting=get_waiting_list(),
                           in_consultation=in_consultation)


@app.route("/queue/mine")
@login_required
def queue_mine():
    """Patient's place in line."""
    require_role("patient")
    entry = active_entry_of(profile_id_of(current_user.id))
    my_place = None
    if entry and entry["status"] == "waiting":
        for waiting in get_waiting_list():
            if waiting["id"] == entry["id"]:
                my_place = waiting
    doctor = None
    if entry and entry["doctor_id"]:
        doctor = run_sql("SELECT name FROM users WHERE id = %s", (entry["doctor_id"],), "one")
    return render_template("queue_mine.html", entry=entry, my_place=my_place, doctor=doctor)


@app.route("/queue/checkin", methods=["GET", "POST"])
@login_required
def queue_checkin():
    """Check in (self, or any patient for staff)."""
    is_staff = current_user.role in STAFF
    if not is_staff:
        require_role("patient")

    doctors = run_sql("SELECT id, name FROM users WHERE role = 'doctor' ORDER BY name", fetch="all")
    patients = run_sql(
        """SELECT p.id, u.name, u.email
           FROM patient_profiles p JOIN users u ON u.id = p.user_id ORDER BY u.name""",
        fetch="all",
    ) if is_staff else []

    def show_form():
        return render_template("queue_checkin.html", doctors=doctors, patients=patients,
                               is_staff=is_staff)

    if request.method == "GET":
        return show_form()

    # Pick patient and priority
    if is_staff:
        profile_id = request.form.get("patient_id", type=int)
        if not profile_id or not run_sql("SELECT id FROM patient_profiles WHERE id = %s",
                                         (profile_id,), "one"):
            flash("Choose a patient to check in.", "danger")
            return show_form()
        priority = "urgent" if request.form.get("priority") == "urgent" else "normal"
    else:
        profile_id = profile_id_of(current_user.id)
        priority = "normal"  # patients can't self-mark urgent

    doctor_id = request.form.get("doctor_id", type=int) or None
    if doctor_id and not run_sql("SELECT id FROM users WHERE id = %s AND role = 'doctor'",
                                 (doctor_id,), "one"):
        flash("Choose a doctor from the list, or leave it as any doctor.", "danger")
        return show_form()

    if active_entry_of(profile_id):
        flash("That patient is already in the queue.", "danger")
        return show_form()

    run_sql(
        """INSERT INTO queue_entries (patient_id, doctor_id, priority, reason, checked_in_at)
           VALUES (%s, %s, %s, %s, %s)""",
        (profile_id, doctor_id, priority, request.form["reason"].strip()[:255] or None,
         datetime.now()),
    )
    flash("Checked in.", "success")
    return back_to_queue()


@app.route("/queue/<int:entry_id>/call", methods=["POST"])
@login_required
def queue_call(entry_id):
    """Call patient in."""
    require_role(*STAFF)
    entry = get_entry_or_404(entry_id)
    if entry["status"] != "waiting":
        flash("That patient is not waiting.", "danger")
        return back_to_queue()

    doctor_id = entry["doctor_id"]
    if current_user.role == "doctor":
        if doctor_id not in (None, current_user.id):
            abort(403)  # another doctor's patient
        doctor_id = current_user.id  # claim "any doctor" patient

    run_sql(
        "UPDATE queue_entries SET status = 'in_consultation', called_at = %s, doctor_id = %s WHERE id = %s",
        (datetime.now(), doctor_id, entry_id),
    )
    flash(f"{entry['patient_name']} called in.", "success")
    return back_to_queue()


@app.route("/queue/<int:entry_id>/complete", methods=["POST"])
@login_required
def queue_complete(entry_id):
    """Finish consultation."""
    require_role(*STAFF)
    entry = get_entry_or_404(entry_id)
    if current_user.role == "doctor" and entry["doctor_id"] != current_user.id:
        abort(403)
    if entry["status"] != "in_consultation":
        flash("That patient is not in a consultation.", "danger")
        return back_to_queue()

    run_sql("UPDATE queue_entries SET status = 'completed', completed_at = %s WHERE id = %s",
            (datetime.now(), entry_id))
    flash(f"Consultation with {entry['patient_name']} finished.", "success")
    return back_to_queue()


@app.route("/queue/<int:entry_id>/cancel", methods=["POST"])
@login_required
def queue_cancel(entry_id):
    """Staff: cancel any. Patient: own, while waiting."""
    entry = get_entry_or_404(entry_id)
    if current_user.role == "patient":
        if entry["patient_user_id"] != current_user.id or entry["status"] != "waiting":
            abort(403)
    else:
        require_role(*STAFF)
    if entry["status"] not in ACTIVE:
        flash("That check-in is already closed.", "danger")
        return back_to_queue()

    run_sql("UPDATE queue_entries SET status = 'cancelled', completed_at = %s WHERE id = %s",
            (datetime.now(), entry_id))
    flash("Check-in cancelled.", "success")
    return back_to_queue()


if __name__ == "__main__":
    app.run(debug=True, port=5050)
