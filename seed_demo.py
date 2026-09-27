"""Fill the database with demo data (run after setup_db.py): python seed_demo.py
Remove it again:                                              python seed_demo.py --remove

Creates 3 patients, 1 doctor and 1 nurse, plus sample appointments, notifications,
prescriptions, consultation notes and waiting-room check-ins. Dates are relative to
today, so the dashboards always have something to show. Safe to re-run: it stops if
the demo accounts already exist.

--remove deletes only the demo accounts and everything linked to them (including any
bookings real patients made with the demo doctor). The admin account is kept.

Every demo account uses the password DEMO_PASSWORD. Test data only.
"""

import sys
from datetime import date, datetime, timedelta

from app import create_user, email_taken, get_appointment_or_404, notify_both, profile_id_of, run_sql

DEMO_PASSWORD = "demo1234"

PATIENTS = [
    # name, email, date of birth, contact info, current medications
    ("Kasseus Andrei Baleda", "kasseus@smartclinic.test", date(2003, 5, 14),
     "0491 570 156 · 12 Harbour St, Sydney NSW", "Amlodipine 5mg once daily"),
    ("Gean Marco Bayawa", "gean@smartclinic.test", date(2004, 2, 3),
     "0491 570 157 · 48 Park Rd, Parramatta NSW", None),
    ("Kirvey Kent Morre", "kirvey@smartclinic.test", date(2003, 11, 22),
     "0491 570 158 · 7 Ocean Ave, Bondi NSW", "Cetirizine 10mg as needed"),
]
DOCTOR = ("Dr. Chino Salangsang", "chino@smartclinic.test")
NURSE = ("Maya Thompson", "maya@smartclinic.test")
DEMO_EMAILS = [p[1] for p in PATIENTS] + [DOCTOR[1], NURSE[1]]


def remove_demo_data():
    """Delete the demo accounts and every row that points at them (children first)."""
    marks = ", ".join(["%s"] * len(DEMO_EMAILS))
    users = f"SELECT id FROM users WHERE email IN ({marks})"
    profiles = f"SELECT id FROM patient_profiles WHERE user_id IN ({users})"
    appointments = f"SELECT id FROM appointments WHERE patient_id IN ({profiles}) OR doctor_id IN ({users})"
    prescriptions = f"SELECT id FROM prescriptions WHERE patient_id IN ({profiles}) OR doctor_id IN ({users})"
    two, three = DEMO_EMAILS * 2, DEMO_EMAILS * 3

    # MySQL can't read and delete the same table in one statement, so collect ids first
    appointment_ids = [r["id"] for r in run_sql(appointments, two, "all")]
    prescription_ids = [r["id"] for r in run_sql(prescriptions, two, "all")]

    def delete_ids(table, column, ids):
        if ids:
            run_sql(f"DELETE FROM {table} WHERE {column} IN ({', '.join(['%s'] * len(ids))})", ids)

    run_sql(f"DELETE FROM notifications WHERE user_id IN ({users})", DEMO_EMAILS)
    delete_ids("notifications", "appointment_id", appointment_ids)
    delete_ids("prescription_items", "prescription_id", prescription_ids)
    delete_ids("prescriptions", "id", prescription_ids)
    run_sql(f"DELETE FROM consultation_notes WHERE patient_id IN ({profiles}) OR doctor_id IN ({users})", two)
    run_sql(f"DELETE FROM queue_entries WHERE patient_id IN ({profiles}) OR doctor_id IN ({users})", two)
    delete_ids("appointments", "id", appointment_ids)
    run_sql(f"DELETE FROM patient_profiles WHERE user_id IN ({users})", DEMO_EMAILS)
    run_sql(f"DELETE FROM users WHERE email IN ({marks})", DEMO_EMAILS)


if "--remove" in sys.argv:
    if not email_taken(DOCTOR[1]):
        print("No demo data found. Nothing to remove.")
    else:
        remove_demo_data()
        print("Demo data removed. The admin account and anything else you created are untouched.")
    raise SystemExit

if email_taken(DOCTOR[1]):
    print("Demo data is already loaded. Nothing to do.")
    raise SystemExit

# --- Accounts ---
doctor_id = create_user(*DOCTOR, DEMO_PASSWORD, "doctor")
create_user(*NURSE, DEMO_PASSWORD, "nurse")

patient = {}  # first name -> patient profile id
for name, email, born, contact, medications in PATIENTS:
    user_id = create_user(name, email, DEMO_PASSWORD, "patient", born, contact)
    profile_id = profile_id_of(user_id)
    if medications:
        run_sql("UPDATE patient_profiles SET current_medications = %s WHERE id = %s", (medications, profile_id))
    patient[name.split()[0]] = profile_id

today = date.today()
now = datetime.now()

# --- Appointments (+ the notifications a real booking would send) ---
APPOINTMENTS = [
    # patient, days from today, time, reason, status
    ("Kasseus", 0, "09:00", "Blood pressure follow-up", "scheduled"),
    ("Gean", 0, "11:00", "Sore throat and cough", "scheduled"),
    ("Kirvey", 1, "10:00", "Annual check-up", "scheduled"),
    ("Kasseus", 7, "13:00", "Review blood test results", "scheduled"),
    ("Gean", 2, "14:00", "Flu vaccination", "cancelled"),
]
for first_name, days, time, reason, status in APPOINTMENTS:
    appointment_id = run_sql(
        """INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, status, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (patient[first_name], doctor_id, today + timedelta(days=days), time, reason, status,
         now - timedelta(days=3)),
    )
    appointment = get_appointment_or_404(appointment_id)
    notify_both(appointment, "Confirmation", "Appointment booked")
    if status == "cancelled":
        notify_both(appointment, "Cancellation", "Appointment cancelled")

# --- Prescriptions ---
PRESCRIPTIONS = [
    # patient, days ago, allergies, instructions, [(drug, strength, form, frequency, duration, quantity)]
    ("Kasseus", 14, None, "Check blood pressure at home each morning; review in 4 weeks.",
     [("Amlodipine", "5mg", "Tablet", "1 tablet, once daily", "30 days", "30 tabs, 2 refills")]),
    ("Gean", 0, "Penicillin", "Finish the full course. Rest and drink plenty of fluids.",
     [("Azithromycin", "500mg", "Tablet", "1 tablet, once daily", "3 days", "3 tabs"),
      ("Paracetamol", "500mg", "Tablet", "1-2 tablets every 6 hours as needed", "5 days", "20 tabs")]),
]
for first_name, days_ago, allergies, instructions, items in PRESCRIPTIONS:
    prescription_id = run_sql(
        """INSERT INTO prescriptions (patient_id, doctor_id, license_number, allergies, instructions, issued_on, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (patient[first_name], doctor_id, "MED0001234", allergies, instructions,
         today - timedelta(days=days_ago), now - timedelta(days=days_ago)),
    )
    for item in items:
        run_sql(
            """INSERT INTO prescription_items (prescription_id, drug_name, strength, form, frequency, duration, quantity)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (prescription_id, *item),
        )

# --- Consultation notes ---
NOTES = [
    ("Kasseus", 14, "BP 145/92. Started amlodipine 5mg daily. Advised less salt and regular walks. Review in 4 weeks."),
    ("Gean", 0, "Sore throat for 4 days, mild fever (38.1°C), swollen tonsils. Penicillin allergy, so prescribed azithromycin."),
    ("Kirvey", 30, "Seasonal allergies flaring. Continue cetirizine as needed. No other concerns."),
]
for first_name, days_ago, note in NOTES:
    run_sql(
        "INSERT INTO consultation_notes (patient_id, doctor_id, note, created_at) VALUES (%s, %s, %s, %s)",
        (patient[first_name], doctor_id, note, now - timedelta(days=days_ago)),
    )

# --- Waiting room (checked in a few minutes ago) ---
run_sql(
    """INSERT INTO queue_entries (patient_id, doctor_id, status, priority, reason, checked_in_at)
       VALUES (%s, %s, 'waiting', %s, %s, %s)""",
    (patient["Gean"], doctor_id, "normal", "Sore throat and cough", now - timedelta(minutes=12)),
)
run_sql(
    """INSERT INTO queue_entries (patient_id, doctor_id, status, priority, reason, checked_in_at)
       VALUES (%s, %s, 'waiting', %s, %s, %s)""",
    (patient["Kirvey"], None, "urgent", "Allergic reaction, itchy rash", now - timedelta(minutes=5)),
)

print("Demo data loaded. Log in with any of these (password: %s):" % DEMO_PASSWORD)
for name, email, *_ in PATIENTS:
    print(f"  patient  {email:28} {name}")
print(f"  doctor   {DOCTOR[1]:28} {DOCTOR[0]}")
print(f"  nurse    {NURSE[1]:28} {NURSE[0]}")
print("  admin    admin@smartclinic.test      (password: admin123)")
