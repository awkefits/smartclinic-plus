# SmartClinic+
# Member 2 - Online Appointment Booking and Automated Notifications

appointments = []
notifications = []

doctors = [
    "Dr. Smith",
    "Dr. Johnson",
    "Dr. Brown"
]

available_times = [
    "9:00 AM",
    "10:00 AM",
    "11:00 AM",
    "1:00 PM",
    "2:00 PM"
]


def create_notification(appointment_id, notification_type, message):
    notification = {
        "notification_id": len(notifications) + 1,
        "appointment_id": appointment_id,
        "notification_type": notification_type,
        "message": message,
        "status": "Sent"
    }

    notifications.append(notification)
    print("\nNotification:", message)


def check_availability(doctor, date):
    booked_times = []

    for appointment in appointments:
        if (
            appointment["doctor"] == doctor
            and appointment["date"] == date
            and appointment["status"] == "Scheduled"
        ):
            booked_times.append(appointment["time"])

    return [
        time for time in available_times
        if time not in booked_times
    ]


def book_appointment():
    print("\n--- Book Appointment ---")

    for index, doctor in enumerate(doctors, 1):
        print(index, doctor)

    choice = int(input("Choose doctor: "))
    doctor = doctors[choice - 1]

    date = input("Enter date (DD/MM/YYYY): ")

    free_times = check_availability(doctor, date)

    if not free_times:
        print("No available time slots.")
        return

    print("\nAvailable Times:")

    for index, time in enumerate(free_times, 1):
        print(index, time)

    time_choice = int(input("Choose time: "))
    selected_time = free_times[time_choice - 1]

    reason = input("Reason for visit: ")

    appointment = {
        "appointment_id": len(appointments) + 1,
        "patient_id": 1,
        "doctor": doctor,
        "date": date,
        "time": selected_time,
        "reason": reason,
        "status": "Scheduled"
    }

    appointments.append(appointment)

    print("\nAppointment successfully booked.")

    create_notification(
        appointment["appointment_id"],
        "Confirmation",
        "Your appointment has been successfully booked."
    )


def view_appointments():
    print("\n--- Upcoming Appointments ---")

    if not appointments:
        print("No appointments found.")
        return

    for appointment in appointments:
        print(
            f'ID: {appointment["appointment_id"]} | '
            f'Doctor: {appointment["doctor"]} | '
            f'Date: {appointment["date"]} | '
            f'Time: {appointment["time"]} | '
            f'Status: {appointment["status"]}'
        )


def reschedule_appointment():
    view_appointments()

    appointment_id = int(
        input("\nEnter appointment ID to reschedule: ")
    )

    for appointment in appointments:

        if (
            appointment["appointment_id"] == appointment_id
            and appointment["status"] == "Scheduled"
        ):

            new_date = input("Enter new date: ")

            free_times = check_availability(
                appointment["doctor"],
                new_date
            )

            print("\nAvailable Times:")

            for index, time in enumerate(free_times, 1):
                print(index, time)

            choice = int(input("Choose new time: "))

            appointment["date"] = new_date
            appointment["time"] = free_times[choice - 1]

            print("Appointment successfully rescheduled.")

            create_notification(
                appointment_id,
                "Update",
                "Your appointment schedule has been updated."
            )

            return

    print("Appointment not found.")


def cancel_appointment():
    view_appointments()

    appointment_id = int(
        input("\nEnter appointment ID to cancel: ")
    )

    for appointment in appointments:

        if appointment["appointment_id"] == appointment_id:

            appointment["status"] = "Cancelled"

            print("Appointment successfully cancelled.")

            create_notification(
                appointment_id,
                "Cancellation",
                "Your scheduled appointment has been cancelled."
            )

            return

    print("Appointment not found.")


def view_notifications():
    print("\n--- Notifications ---")

    if not notifications:
        print("No notifications.")
        return

    for notification in notifications:
        print(
            f'{notification["notification_type"]}: '
            f'{notification["message"]}'
        )


def main():
    while True:

        print("\n==========================")
        print("       SmartClinic+")
        print("==========================")
        print("1. Book Appointment")
        print("2. View Appointments")
        print("3. Reschedule Appointment")
        print("4. Cancel Appointment")
        print("5. View Notifications")
        print("6. Exit")

        choice = input("\nChoose an option: ")

        if choice == "1":
            book_appointment()

        elif choice == "2":
            view_appointments()

        elif choice == "3":
            reschedule_appointment()

        elif choice == "4":
            cancel_appointment()

        elif choice == "5":
            view_notifications()

        elif choice == "6":
            print("Thank you for using SmartClinic+.")
            break

        else:
            print("Invalid option. Please try again.")


main()