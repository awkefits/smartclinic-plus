# 🏥 SmartClinic+

A Smart Patient Management System

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python setup_db.py
python app.py
```

- **Needs**: MySQL running in XAMPP
- **Open**: http://localhost:5050

## Features

- **Patient**: Register, edit profile, check in
- **Doctor**: View patients, call in, finish consultations
- **Nurse**: Check in patients, mark urgent
- **Admin**: Create staff accounts, manage patients

## Login

- **Admin**: `admin@smartclinic.test` / `admin123`
- **Patient**: Register on the sign-up page
- **Doctor / Nurse**: Created by the admin

## Waiting Room Queue

- Urgent first, then first come, first served
- One line per doctor, plus an "any doctor" line
- About 15 minutes per patient ahead

## Technology Stack

- Flask (Python)
- MySQL (XAMPP)
- Bootstrap
