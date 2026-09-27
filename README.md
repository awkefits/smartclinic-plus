# 🏥 SmartClinic+

A Smart Patient Management System

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python setup_db.py   # also run again after pulling, to add new tables
python seed_demo.py  # optional: demo patients, doctor, nurse + sample bookings (remove with --remove)
python app.py
```

- **Needs**: MySQL running in XAMPP
- **Open**: http://localhost:5050

## Features

- **Patient**: Register, edit profile, check in, book / reschedule / cancel appointments, view prescriptions
- **Doctor**: Doctor dashboard (patient lookup, consultation notes, schedule), write e-prescriptions, call in and finish consultations
- **Nurse**: Check in patients, mark urgent, book appointments for patients
- **Admin**: Create staff accounts, manage patients and appointments
- **Notifications**: Patient and doctor are notified when an appointment is booked, moved or cancelled

## Login

- **Admin**: `admin@smartclinic.test` / `admin123`
- **Patient**: Register on the sign-up page
- **Doctor / Nurse**: Created by the admin

### Demo accounts (after `python seed_demo.py`)

All use the password `demo1234`. Test data only.

| Role | Email | Name |
|---|---|---|
| Patient | `kasseus@smartclinic.test` | Kasseus Andrei Baleda |
| Patient | `gean@smartclinic.test` | Gean Marco Bayawa |
| Patient | `kirvey@smartclinic.test` | Kirvey Kent Morre |
| Doctor | `chino@smartclinic.test` | Dr. Chino Salangsang |
| Nurse | `maya@smartclinic.test` | Maya Thompson |

## Waiting Room Queue

- Urgent first, then first come, first served
- One line per doctor, plus an "any doctor" line
- About 15 minutes per patient ahead

## Appointments

- Times: 9:00, 10:00, 11:00 AM, 1:00, 2:00 PM each day
- Only free times are shown; a cancelled appointment frees its time

## Technology Stack

- Flask (Python)
- MySQL (XAMPP)
- Bootstrap
