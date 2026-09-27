-- SmartClinic+ tables (safe to re-run)

-- Login accounts
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(120) NOT NULL,
    email         VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20)  NOT NULL DEFAULT 'patient'   -- patient/doctor/nurse/admin
);

-- Patient details (one per patient)
CREATE TABLE IF NOT EXISTS patient_profiles (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    user_id             INT NOT NULL UNIQUE,
    contact_info        VARCHAR(255),
    current_medications TEXT,
    date_of_birth       DATE,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Waiting-room check-ins
CREATE TABLE IF NOT EXISTS queue_entries (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    patient_id    INT NOT NULL,
    doctor_id     INT NULL,                                  -- NULL = any doctor
    status        VARCHAR(20) NOT NULL DEFAULT 'waiting',    -- waiting/in_consultation/completed/cancelled
    priority      VARCHAR(10) NOT NULL DEFAULT 'normal',     -- normal/urgent
    reason        VARCHAR(255),
    checked_in_at DATETIME NOT NULL,
    called_at     DATETIME,
    completed_at  DATETIME,
    FOREIGN KEY (patient_id) REFERENCES patient_profiles(id),
    FOREIGN KEY (doctor_id)  REFERENCES users(id)
);

-- Booked appointments (from the booking system)
CREATE TABLE IF NOT EXISTS appointments (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    patient_id       INT NOT NULL,
    doctor_id        INT NOT NULL,
    appointment_date DATE NOT NULL,
    appointment_time VARCHAR(5) NOT NULL,                    -- 24-hour "HH:MM", one of TIME_SLOTS
    reason           VARCHAR(255),
    status           VARCHAR(20) NOT NULL DEFAULT 'scheduled',  -- scheduled/cancelled
    created_at       DATETIME NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patient_profiles(id),
    FOREIGN KEY (doctor_id)  REFERENCES users(id)
);

-- Messages about appointments (booked, moved, cancelled)
CREATE TABLE IF NOT EXISTS notifications (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    user_id           INT NOT NULL,
    appointment_id    INT NULL,
    notification_type VARCHAR(20) NOT NULL,                  -- Confirmation/Update/Cancellation
    message           VARCHAR(255) NOT NULL,
    is_read           TINYINT(1) NOT NULL DEFAULT 0,
    created_at        DATETIME NOT NULL,
    FOREIGN KEY (user_id)        REFERENCES users(id),
    FOREIGN KEY (appointment_id) REFERENCES appointments(id)
);

-- Doctor consultation notes (from the doctor dashboard)
CREATE TABLE IF NOT EXISTS consultation_notes (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    doctor_id  INT NOT NULL,
    note       TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patient_profiles(id),
    FOREIGN KEY (doctor_id)  REFERENCES users(id)
);

-- E-prescriptions (one row per prescription, one item per medication)
CREATE TABLE IF NOT EXISTS prescriptions (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    patient_id     INT NOT NULL,
    doctor_id      INT NOT NULL,
    license_number VARCHAR(60) NOT NULL,
    allergies      VARCHAR(255),
    instructions   TEXT,
    issued_on      DATE NOT NULL,
    created_at     DATETIME NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patient_profiles(id),
    FOREIGN KEY (doctor_id)  REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS prescription_items (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    prescription_id INT NOT NULL,
    drug_name       VARCHAR(120) NOT NULL,
    strength        VARCHAR(60) NOT NULL,
    form            VARCHAR(30),
    frequency       VARCHAR(120) NOT NULL,
    duration        VARCHAR(60),
    quantity        VARCHAR(60),
    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
);
