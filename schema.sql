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
