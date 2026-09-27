"""SmartClinic+ - patient profiles, role-based login, waiting-room queue,
appointments + notifications, doctor dashboard, e-prescriptions."""

import os
from datetime import date, datetime

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

# Bookable appointment times (24-hour, same every day)
TIME_SLOTS = ("09:00", "10:00", "11:00", "13:00", "14:00")

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


@app.template_filter("slot")
def format_slot(slot):
    """'13:00' -> '1:00 PM'."""
    return datetime.strptime(slot, "%H:%M").strftime("%I:%M %p").lstrip("0")


@app.template_filter("nice_date")
def format_date(value):
    """date -> '1 Oct 2026'. None -> '-'."""
    return f"{value.day} {value.strftime('%b %Y')}" if value else "-"


@app.context_processor
def unread_notifications():
    """Unread count for the navbar badge."""
    if not current_user.is_authenticated:
        return {"unread_count": 0}
    row = run_sql("SELECT COUNT(*) AS total FROM notifications WHERE user_id = %s AND is_read = 0",
                  (current_user.id,), "one")
    return {"unread_count": row["total"]}


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
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
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
    """Home page: profile card + tabs of short lists for the user's role."""
    today = date.today()
    tabs = {}
    my_profile_id = None
    queue_entry = my_place = None

    if current_user.role == "patient":
        my_profile_id = profile_id_of(current_user.id)
        tabs["appointments"] = run_sql(
            APPOINTMENT_SELECT + """ WHERE a.patient_id = %s AND a.status = 'scheduled' AND a.appointment_date >= %s
                                     ORDER BY a.appointment_date, a.appointment_time LIMIT 5""",
            (my_profile_id, today), "all",
        )
        tabs["prescriptions"] = recent_prescriptions("rx.patient_id = %s", my_profile_id)
        queue_entry = active_entry_of(my_profile_id)
        if queue_entry and queue_entry["status"] == "waiting":
            my_place = next((w for w in get_waiting_list() if w["id"] == queue_entry["id"]), None)
    else:
        mine = current_user.role == "doctor"
        tabs["appointments"] = run_sql(
            APPOINTMENT_SELECT + " WHERE a.appointment_date = %s AND a.status = 'scheduled'"
            + (" AND a.doctor_id = %s" if mine else "") + " ORDER BY a.appointment_time",
            (today, current_user.id) if mine else (today,), "all",
        )
        waiting = get_waiting_list()
        if mine:  # own line + the "any doctor" line
            waiting = [w for w in waiting if w["doctor_id"] in (None, current_user.id)]
        tabs["waiting"] = waiting
        if mine:
            tabs["prescriptions"] = recent_prescriptions("rx.doctor_id = %s", current_user.id)
        else:
            tabs["patients"] = run_sql(
                """SELECT p.id, p.date_of_birth, u.name, u.email
                   FROM patient_profiles p JOIN users u ON u.id = p.user_id
                   ORDER BY p.id DESC LIMIT 5""",
                fetch="all",
            )

    initials = "".join(word[0] for word in current_user.name.replace("Dr.", "").split()[:2]).upper()
    return render_template("dashboard.html", my_profile_id=my_profile_id, tabs=tabs, initials=initials,
                           queue_entry=queue_entry, my_place=my_place)


def recent_prescriptions(where, value):
    """Latest 5 prescriptions matching one condition, e.g. 'rx.doctor_id = %s'."""
    return run_sql(
        """SELECT rx.id, rx.issued_on, pu.name AS patient_name, d.name AS doctor_name,
                  (SELECT COUNT(*) FROM prescription_items i WHERE i.prescription_id = rx.id) AS item_count
           FROM prescriptions rx
           JOIN patient_profiles p ON p.id = rx.patient_id
           JOIN users pu ON pu.id = p.user_id
           JOIN users d ON d.id = rx.doctor_id
           WHERE """ + where + " ORDER BY rx.issued_on DESC, rx.id DESC LIMIT 5",
        (value,), "all",
    )


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
    prescriptions = run_sql(
        """SELECT rx.id, rx.issued_on, d.name AS doctor_name,
                  (SELECT COUNT(*) FROM prescription_items i WHERE i.prescription_id = rx.id) AS item_count
           FROM prescriptions rx JOIN users d ON d.id = rx.doctor_id
           WHERE rx.patient_id = %s ORDER BY rx.issued_on DESC, rx.id DESC""",
        (profile_id,), "all",
    )
    notes = notes_for(profile_id) if current_user.role in STAFF else []
    return render_template("patient_view.html", profile=profile, can_edit=can_edit,
                           prescriptions=prescriptions, notes=notes)


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
        """INSERT INTO queue_entries (patient_id, doctor_id, status, priority, reason, checked_in_at)
           VALUES (%s, %s, 'waiting', %s, %s, %s)""",
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


# --- 8. Appointment Pages (Booking + Notifications) ---
# Patient: book/manage own | Nurse/Admin: book/manage any | Doctor: see/manage own
# Status: scheduled -> cancelled. Every change notifies the patient and the doctor.

BOOKING_STAFF = ("nurse", "admin")

APPOINTMENT_SELECT = """
    SELECT a.*, p.user_id AS patient_user_id, pu.name AS patient_name, d.name AS doctor_name
    FROM appointments a
    JOIN patient_profiles p ON p.id = a.patient_id
    JOIN users pu ON pu.id = p.user_id
    JOIN users d ON d.id = a.doctor_id
"""


def all_doctors():
    return run_sql("SELECT id, name FROM users WHERE role = 'doctor' ORDER BY name", fetch="all")


def all_patients():
    return run_sql(
        """SELECT p.id, u.name, u.email
           FROM patient_profiles p JOIN users u ON u.id = p.user_id ORDER BY u.name""",
        fetch="all",
    )


def free_slots(doctor_id, day, ignore_appointment_id=0):
    """Times the doctor is still free that day (past times today are left out)."""
    rows = run_sql(
        """SELECT appointment_time FROM appointments
           WHERE doctor_id = %s AND appointment_date = %s AND status = 'scheduled' AND id <> %s""",
        (doctor_id, day, ignore_appointment_id), "all",
    )
    taken = {row["appointment_time"] for row in rows}
    slots = [slot for slot in TIME_SLOTS if slot not in taken]
    if day == date.today():
        now = datetime.now().strftime("%H:%M")
        slots = [slot for slot in slots if slot > now]
    return slots


def read_booking_date(text):
    """Form date -> date. Flashes and returns None if invalid or in the past."""
    try:
        day = parse_date(text)
    except ValueError:
        day = None
    if day is None:
        flash("Pick a valid date.", "danger")
    elif day < date.today():
        flash("Pick today or a future date.", "danger")
        day = None
    return day


def notify(user_id, appointment_id, notification_type, message):
    run_sql(
        """INSERT INTO notifications (user_id, appointment_id, notification_type, message, created_at)
           VALUES (%s, %s, %s, %s, %s)""",
        (user_id, appointment_id, notification_type, message, datetime.now()),
    )


def notify_both(appointment, notification_type, headline):
    """Tell the patient and the doctor about an appointment change."""
    when = f"{format_date(appointment['appointment_date'])} at {format_slot(appointment['appointment_time'])}"
    notify(appointment["patient_user_id"], appointment["id"], notification_type,
           f"{headline}: {appointment['doctor_name']} on {when}.")
    notify(appointment["doctor_id"], appointment["id"], notification_type,
           f"{headline}: {appointment['patient_name']} on {when}.")


def get_appointment_or_404(appointment_id):
    appointment = run_sql(APPOINTMENT_SELECT + " WHERE a.id = %s", (appointment_id,), "one")
    if appointment is None:
        abort(404)
    return appointment


def require_appointment_access(appointment):
    """403 unless it's the user's own appointment (or they are nurse/admin)."""
    if current_user.role == "patient":
        allowed = appointment["patient_user_id"] == current_user.id
    elif current_user.role == "doctor":
        allowed = appointment["doctor_id"] == current_user.id
    else:
        allowed = current_user.role in BOOKING_STAFF
    if not allowed:
        abort(403)


@app.route("/appointments")
@login_required
def appointment_list():
    if current_user.role == "patient":
        where, args = "WHERE a.patient_id = %s", (profile_id_of(current_user.id),)
    elif current_user.role == "doctor":
        where, args = "WHERE a.doctor_id = %s", (current_user.id,)
    else:
        where, args = "", ()
    appointments = run_sql(
        APPOINTMENT_SELECT + where + " ORDER BY a.appointment_date, a.appointment_time",
        args, "all",
    )
    return render_template("appointment_list.html", appointments=appointments, today=date.today())


@app.route("/appointments/book", methods=["GET", "POST"])
@login_required
def appointment_book():
    """Step 1 (GET): pick doctor + date. Step 2 (POST): pick a free time."""
    is_staff = current_user.role in BOOKING_STAFF
    if not is_staff:
        require_role("patient")

    doctors = all_doctors()
    patients = all_patients() if is_staff else []
    source = request.form if request.method == "POST" else request.args
    doctor_id = source.get("doctor_id", type=int)
    patient_id = source.get("patient_id", type=int) if is_staff else profile_id_of(current_user.id)
    day = None
    slots = None  # None = not searched yet

    def show_form():
        return render_template("appointment_book.html", doctors=doctors, patients=patients,
                               is_staff=is_staff, doctor_id=doctor_id, patient_id=patient_id,
                               day=day, slots=slots, today=date.today())

    if not source.get("date"):
        return show_form()

    day = read_booking_date(source.get("date"))
    doctor = next((d for d in doctors if d["id"] == doctor_id), None)
    if doctor is None:
        flash("Choose a doctor from the list.", "danger")
    if is_staff and not any(p["id"] == patient_id for p in patients):
        flash("Choose a patient.", "danger")
        return show_form()
    if day is None or doctor is None:
        return show_form()

    slots = free_slots(doctor_id, day)
    if request.method == "GET":
        return show_form()

    time = request.form.get("time")
    if time not in slots:
        flash("That time is no longer free. Pick another one.", "danger")
        return show_form()

    appointment_id = run_sql(
        """INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, created_at)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (patient_id, doctor_id, day, time, request.form.get("reason", "").strip()[:255] or None,
         datetime.now()),
    )
    notify_both(get_appointment_or_404(appointment_id), "Confirmation", "Appointment booked")
    flash("Appointment booked.", "success")
    return redirect(url_for("appointment_list"))


@app.route("/appointments/<int:appointment_id>/reschedule", methods=["GET", "POST"])
@login_required
def appointment_reschedule(appointment_id):
    appointment = get_appointment_or_404(appointment_id)
    require_appointment_access(appointment)
    if appointment["status"] != "scheduled":
        flash("Only scheduled appointments can be moved.", "danger")
        return redirect(url_for("appointment_list"))

    source = request.form if request.method == "POST" else request.args
    day = None
    slots = None

    def show_form():
        return render_template("appointment_reschedule.html", appointment=appointment,
                               day=day, slots=slots, today=date.today())

    if not source.get("date"):
        return show_form()

    day = read_booking_date(source.get("date"))
    if day is None:
        return show_form()
    slots = free_slots(appointment["doctor_id"], day, appointment_id)
    if request.method == "GET":
        return show_form()

    time = request.form.get("time")
    if time not in slots:
        flash("That time is no longer free. Pick another one.", "danger")
        return show_form()

    run_sql("UPDATE appointments SET appointment_date = %s, appointment_time = %s WHERE id = %s",
            (day, time, appointment_id))
    notify_both(get_appointment_or_404(appointment_id), "Update", "Appointment moved to a new time")
    flash("Appointment moved.", "success")
    return redirect(url_for("appointment_list"))


@app.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
@login_required
def appointment_cancel(appointment_id):
    appointment = get_appointment_or_404(appointment_id)
    require_appointment_access(appointment)
    if appointment["status"] != "scheduled":
        flash("That appointment is already cancelled.", "danger")
        return redirect(url_for("appointment_list"))

    run_sql("UPDATE appointments SET status = 'cancelled' WHERE id = %s", (appointment_id,))
    notify_both(appointment, "Cancellation", "Appointment cancelled")
    flash("Appointment cancelled.", "success")
    return redirect(url_for("appointment_list"))


@app.route("/notifications")
@login_required
def notification_list():
    notifications = run_sql(
        "SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC, id DESC",
        (current_user.id,), "all",
    )
    run_sql("UPDATE notifications SET is_read = 1 WHERE user_id = %s", (current_user.id,))
    return render_template("notification_list.html", notifications=notifications)


# --- 9. Doctor Dashboard (Patient Lookup + Consultation Notes) ---

def notes_for(profile_id):
    return run_sql(
        """SELECT n.*, d.name AS doctor_name
           FROM consultation_notes n JOIN users d ON d.id = n.doctor_id
           WHERE n.patient_id = %s ORDER BY n.created_at DESC, n.id DESC""",
        (profile_id,), "all",
    )


@app.route("/doctor")
@login_required
def doctor_dashboard():
    require_role("doctor")
    search = request.args.get("q", "").strip()
    results = []
    if search:
        like = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        results = run_sql(
            """SELECT p.id, p.date_of_birth, u.name, u.email
               FROM patient_profiles p JOIN users u ON u.id = p.user_id
               WHERE u.name LIKE %s OR p.id = %s ORDER BY u.name""",
            (like, int(search) if search.isdigit() else 0), "all",
        )

    selected = None
    notes = []
    selected_id = request.args.get("patient", type=int)
    if selected_id:
        selected = get_profile_or_404(selected_id)
        notes = notes_for(selected_id)

    schedule = run_sql(
        APPOINTMENT_SELECT + """ WHERE a.doctor_id = %s AND a.status = 'scheduled' AND a.appointment_date >= %s
                                 ORDER BY a.appointment_date, a.appointment_time""",
        (current_user.id, date.today()), "all",
    )
    return render_template("doctor_dashboard.html", search=search, results=results,
                           selected=selected, notes=notes, schedule=schedule)


@app.route("/patients/<int:profile_id>/notes", methods=["POST"])
@login_required
def note_add(profile_id):
    require_role("doctor")
    get_profile_or_404(profile_id)
    note = request.form.get("note", "").strip()
    if not note:
        flash("Consultation notes cannot be empty.", "danger")
    else:
        run_sql(
            "INSERT INTO consultation_notes (patient_id, doctor_id, note, created_at) VALUES (%s, %s, %s, %s)",
            (profile_id, current_user.id, note, datetime.now()),
        )
        flash("Notes saved.", "success")
    return redirect(url_for("doctor_dashboard", patient=profile_id, q=request.form.get("q", "")))


# --- 10. E-Prescription Pages ---
# Doctor: write | Patient: view own | Staff: view all

MEDICATION_FORMS = ("Tablet", "Capsule", "Liquid", "Injection", "Topical", "Other")
MEDICATION_FIELDS = ("drug_name", "strength", "form", "frequency", "duration", "quantity")


def get_prescription_or_404(prescription_id):
    prescription = run_sql(
        """SELECT rx.*, pu.name AS patient_name, p.user_id AS patient_user_id, p.date_of_birth,
                  d.name AS doctor_name
           FROM prescriptions rx
           JOIN patient_profiles p ON p.id = rx.patient_id
           JOIN users pu ON pu.id = p.user_id
           JOIN users d ON d.id = rx.doctor_id
           WHERE rx.id = %s""",
        (prescription_id,), "one",
    )
    if prescription is None:
        abort(404)
    return prescription


@app.route("/prescriptions")
@login_required
def prescription_list():
    if current_user.role == "patient":
        where, args = "WHERE rx.patient_id = %s", (profile_id_of(current_user.id),)
    elif current_user.role == "doctor":
        where, args = "WHERE rx.doctor_id = %s", (current_user.id,)
    else:
        where, args = "", ()
    prescriptions = run_sql(
        """SELECT rx.id, rx.issued_on, pu.name AS patient_name, d.name AS doctor_name,
                  (SELECT COUNT(*) FROM prescription_items i WHERE i.prescription_id = rx.id) AS item_count
           FROM prescriptions rx
           JOIN patient_profiles p ON p.id = rx.patient_id
           JOIN users pu ON pu.id = p.user_id
           JOIN users d ON d.id = rx.doctor_id """ + where + " ORDER BY rx.issued_on DESC, rx.id DESC",
        args, "all",
    )
    return render_template("prescription_list.html", prescriptions=prescriptions)


@app.route("/prescriptions/new", methods=["GET", "POST"])
@login_required
def prescription_new():
    require_role("doctor")
    patients = all_patients()
    form = request.form if request.method == "POST" else {}

    # One dict per medication row, from the repeated form fields
    columns = [request.form.getlist(field) for field in MEDICATION_FIELDS]
    medications = [dict(zip(MEDICATION_FIELDS, (value.strip() for value in row))) for row in zip(*columns)]
    medications = [m for m in medications if m["drug_name"]]

    def show_form():
        return render_template("prescription_new.html", patients=patients, form=form,
                               medications=medications or [{}], forms=MEDICATION_FORMS,
                               selected_patient=request.values.get("patient_id", type=int),
                               today=date.today())

    if request.method == "GET":
        return show_form()

    patient_id = request.form.get("patient_id", type=int)
    license_number = request.form.get("license_number", "").strip()
    try:
        issued_on = parse_date(request.form.get("issued_on")) or date.today()
    except ValueError:
        flash("Date issued must be a real date.", "danger")
        return show_form()

    if not any(p["id"] == patient_id for p in patients):
        flash("Choose a patient.", "danger")
    elif not license_number:
        flash("Enter your license / registration number.", "danger")
    elif not medications:
        flash("Add at least one medication.", "danger")
    elif any(not m["strength"] or not m["frequency"] for m in medications):
        flash("Every medication needs a strength and a dosage / frequency.", "danger")
    else:
        prescription_id = run_sql(
            """INSERT INTO prescriptions (patient_id, doctor_id, license_number, allergies, instructions,
                                          issued_on, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (patient_id, current_user.id, license_number[:60],
             request.form.get("allergies", "").strip()[:255] or None,
             request.form.get("instructions", "").strip() or None, issued_on, datetime.now()),
        )
        for m in medications:
            run_sql(
                """INSERT INTO prescription_items (prescription_id, drug_name, strength, form, frequency,
                                                   duration, quantity)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (prescription_id, m["drug_name"][:120], m["strength"][:60],
                 m["form"] if m["form"] in MEDICATION_FORMS else None, m["frequency"][:120],
                 m["duration"][:60] or None, m["quantity"][:60] or None),
            )
        flash("Prescription created.", "success")
        return redirect(url_for("prescription_view", prescription_id=prescription_id))

    return show_form()


@app.route("/prescriptions/<int:prescription_id>")
@login_required
def prescription_view(prescription_id):
    prescription = get_prescription_or_404(prescription_id)
    if not (prescription["patient_user_id"] == current_user.id or current_user.role in STAFF):
        abort(403)
    items = run_sql("SELECT * FROM prescription_items WHERE prescription_id = %s ORDER BY id",
                    (prescription_id,), "all")
    return render_template("prescription_view.html", rx=prescription, items=items)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
