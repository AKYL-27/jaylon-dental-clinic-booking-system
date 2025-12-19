from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv, find_dotenv
from datetime import datetime
from datetime import timedelta

import os
from io import BytesIO
import requests

# -----------------------------
# TIME FORMAT HELPER
# -----------------------------
def to_ampm(time_str):
    """Convert time string to 12-hour format with AM/PM."""
    try:
        # Try 24-hour format first
        dt = datetime.strptime(time_str, "%H:%M")
    except ValueError:
        try:
            # Try 12-hour format with AM/PM
            dt = datetime.strptime(time_str.strip(), "%I:%M %p")
        except ValueError:
            # If both fail, return original string
            return time_str
    return dt.strftime("%I:%M %p").lstrip("0")

def to_24h(time_str):
    """Convert 12-hour AM/PM format to 24-hour format for storage."""
    try:
        # Try 12-hour format with AM/PM
        dt = datetime.strptime(time_str.strip(), "%I:%M %p")
        return dt.strftime("%H:%M")
    except ValueError:
        # If it fails, assume it's already in 24-hour format
        return time_str

# Load .env
env_path = find_dotenv()
load_dotenv(dotenv_path=env_path, override=True)


# Messenger tokens (ADDED)
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
print("PAGE_ACCESS_TOKEN loaded:", bool(PAGE_ACCESS_TOKEN))


# Flask setup
app = Flask(__name__)
# ✅ Register filter
app.jinja_env.filters['to_ampm'] = to_ampm
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_secret")


# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

BASE_URL = os.getenv("BASE_URL", "https://jaylon-dental-clinic-booking-system.onrender.com")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

users_collection = db["users"]
appointments_collection = db["appointments"]
services_collection = db["services"]
payments_collection = db["payments"]
messages_collection = db["messages"]
conversations_collection = db["conversations"]
messenger_users_collection = db["messenger_users"]
schedules_collection = db["schedules"]
calendar_collection = db["calendar"]
blocked_collection = db["blocked_slots"]

print("Connected to:", DB_NAME)

# -----------------------------
# HOME PAGE
# -----------------------------
from datetime import date

@app.route("/privacy-policy")
def privacy_policy():
    return render_template("privacyAndpolicy.html")


@app.route("/profile")
def profile():
    """Display user profile page"""
    # Check if user is logged in
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    # Get user data from database
    user = users_collection.find_one({"_id": ObjectId(session["user_id"])})
    
    if not user:
        return redirect(url_for("logout"))
    
    return render_template("profile.html", user=user)


@app.route("/api/profile/update", methods=["POST"])
def update_profile():
    """Update user profile"""
    # Check if user is logged in
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    
    try:
        data = request.get_json()
        user_id = ObjectId(session["user_id"])
        
        # Get current user
        user = users_collection.find_one({"_id": user_id})
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404
        
        # Prepare update data
        update_data = {}
        
        # Update fullname if provided
        if "fullname" in data and data["fullname"].strip():
            update_data["fullname"] = data["fullname"].strip()
        
        # Update email if provided
        if "email" in data and data["email"].strip():
            email = data["email"].strip()
            
            # Check if email is already taken by another user
            existing_user = users_collection.find_one({
                "email": email,
                "_id": {"$ne": user_id}
            })
            
            if existing_user:
                return jsonify({
                    "success": False, 
                    "error": "Email already in use by another account"
                }), 400
            
            update_data["email"] = email
        
        # Handle password change
        if "current_password" in data and "new_password" in data:
            current_password = data["current_password"]
            new_password = data["new_password"]
            
            # Verify current password
            if not check_password_hash(user["password"], current_password):
                return jsonify({
                    "success": False, 
                    "error": "Current password is incorrect"
                }), 400
            
            # Hash and update new password
            update_data["password"] = generate_password_hash(new_password)
        
        # Update user in database
        if update_data:
            users_collection.update_one(
                {"_id": user_id},
                {"$set": update_data}
            )
            
            return jsonify({
                "success": True,
                "message": "Profile updated successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": "No changes to update"
            }), 400
            
    except Exception as e:
        print(f"Error updating profile: {str(e)}")
        return jsonify({
            "success": False,
            "error": "An error occurred while updating profile"
        }), 500



@app.route("/")
def index():
    # Redirect to login if not authenticated, otherwise to dashboard
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    # Require authentication
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    # Get today's date
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    
    # Date 7 days from today
    date_7days = (today + timedelta(days=7)).strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f"Dashboard Debug Info")
    print(f"{'='*50}")
    print(f"Today: {today_str}")
    print(f"7 Days: {date_7days}")

    # Fetch today's confirmed and rescheduled appointments
    today_appointments = list(appointments_collection.find({
        "date": today_str,
        "status": {"$in": ["confirmed", "rescheduled"]}  # Include both statuses
    }))
    print(f"Today's appointments: {len(today_appointments)}")

    # Fetch upcoming confirmed and rescheduled appointments within next 7 days
    upcoming_appointments = list(appointments_collection.find({
        "date": {"$gt": today_str, "$lte": date_7days},
        "status": {"$in": ["confirmed", "rescheduled"]}  # Include both statuses
    }).sort("date", 1))
    
    print(f"Upcoming appointments: {len(upcoming_appointments)}")
    for appt in upcoming_appointments:
        print(f"  - {appt.get('fullname')} on {appt.get('date')} at {appt.get('time')} [{appt.get('status')}]")
    print(f"{'='*50}\n")

    # Fetch cancelled appointments
    cancelled_appointments = list(appointments_collection.find({
        "status": "cancelled"
    }))

    # Fetch pending payments
    pending_payments = list(appointments_collection.find({
        "payment_status": "pending"
    }))

    # Fetch unread messages (optional)
    new_messages = list(messages_collection.find({"read": {"$ne": True}}))

    # Convert appointment times to 12-hour format
    for appt in today_appointments + upcoming_appointments:
        appt["time_display"] = to_ampm(appt["time"])

    return render_template(
        "index.html",
        today_appointments=today_appointments,
        upcoming_appointments=upcoming_appointments,
        cancelled_appointments=cancelled_appointments,
        pending_payments=pending_payments,
        new_messages=new_messages
    )

@app.route("/inbox")
def inbox():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    messages = list(messages_collection.find().sort("timestamp", -1))
    return render_template("inbox.html", messages=messages)



from datetime import datetime, date

@app.route("/appointments")
def appointments():
    if "user_id" not in session:
        return redirect(url_for("login"))

    appts = list(appointments_collection.find())
    today = date.today().strftime("%Y-%m-%d")

    for a in appts:
        a["_id"] = str(a["_id"])

        # Convert single service string to services array
        if "service" in a:
            a["services"] = [{"name": a["service"]}]
        else:
            a["services"] = []

        # Store the original time in 24-hour format
        a["time_24"] = a.get("time", "00:00")

        # Convert time to AM/PM
        if ":" in a["time"] and "AM" not in a["time"] and "PM" not in a["time"]:
            a["time_display"] = to_ampm(a["time"])
        else:
            a["time_display"] = a["time"]

        appt_date = a["date"]

        # Determine status
        if a.get("status") == "done" or appt_date < today:
            a["status_display"] = "Done"
            a["status_class"] = "table-success"
        elif a.get("status") == "cancelled":
            a["status_display"] = "Cancelled"
            a["status_class"] = "table-danger"
        elif appt_date == today:
            a["status_display"] = "Waiting"
            a["status_class"] = "table-warning"
        else:
            a["status_display"] = "Upcoming"
            a["status_class"] = "table-info"

        # Determine sort_rank
        if appt_date == today:
            a["sort_rank"] = 0
        elif a.get("status") in ["done", "cancelled"] or appt_date < today:
            a["sort_rank"] = 2
        else:
            a["sort_rank"] = 1

    # Sort by sort_rank, then date, then time
    appts.sort(key=lambda x: (x["sort_rank"], x["date"], x["time"]))

    return render_template(
        "appointments.html",
        appointments=appts,
        current_date=today
    )
@app.route("/api/appointments/mark-done", methods=["POST"])
def mark_appointment_done():
    data = request.get_json()
    appt_id = data.get("appointment_id")

    if not appt_id:
        return jsonify(success=False, error="Missing appointment ID"), 400

    result = appointments_collection.update_one(
        {"_id": ObjectId(appt_id)},
        {"$set": {
            "status": "done",
            "completed_at": datetime.now()
        }}
    )

    if result.modified_count == 1:
        return jsonify(success=True, message="Appointment marked as completed!")

    return jsonify(success=False, error="Appointment not found"), 404


@app.route("/appointments/<appt_id>/reschedule", methods=["GET", "POST"])
def reschedule_appointment(appt_id):
    appt = appointments_collection.find_one({"_id": ObjectId(appt_id)})

    if not appt:
        return "Appointment not found", 404

    if request.method == "POST":
        new_date = request.form.get("date")
        new_time = request.form.get("time")
        
        # Convert to 24-hour format for storage if needed
        new_time_24h = to_24h(new_time)

        # TODO: validate availability if needed
        appointments_collection.update_one(
            {"_id": ObjectId(appt_id)},
            {"$set": {
                "date": new_date,
                "time": new_time_24h,
                "status": "rescheduled"
            }}
        )

        # OPTIONAL: notify user via Messenger
        send_message(
            appt["user_id"],
            f"🔁 Your appointment has been rescheduled!\n\n"
            f"Service: {appt['service']}\n"
            f"New Date: {new_date}\n"
            f"New Time: {to_ampm(new_time_24h)}"
        )

        return redirect(url_for("appointments"))

    return render_template(
        "reschedule.html",
        appointment=appt,
        time_display=to_ampm(appt["time"])
    )

@app.route("/appointments/reschedule", methods=["POST"])
def reschedule_appointment_post():
    try:
        appt_id = request.form["appt_id"]
        new_date = request.form["date"]
        new_time = request.form["time"]
        
        # Store time in 24-hour format (assuming new_time is already in HH:MM format from time input)
        new_time_24h = new_time

        appt = appointments_collection.find_one({"_id": ObjectId(appt_id)})
        if not appt:
            return jsonify(success=False, error="Appointment not found"), 404

        appointments_collection.update_one(
            {"_id": ObjectId(appt_id)},
            {"$set": {
                "date": new_date,
                "time": new_time_24h,
                "status": "rescheduled"
            }}
        )

        # Messenger notify 
        try:
            send_message(
                appt["user_id"],
                f"🔁 Your appointment has been rescheduled!\n\n"
                f"Service: {appt['service']}\n"
                f"New Date: {new_date}\n"
                f"New Time: {to_ampm(new_time_24h)}"
            )
        except:
            pass  # Don't fail if messenger notification fails

        return jsonify(success=True, message="Appointment rescheduled successfully!")
    
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500



@app.route("/appointments/cancel", methods=["POST"])
def cancel_appointment_post():
    try:
        appt_id = request.form["appt_id"]

        appt = appointments_collection.find_one({"_id": ObjectId(appt_id)})
        if not appt:
            return jsonify(success=False, error="Appointment not found"), 404

        appointments_collection.update_one(
            {"_id": ObjectId(appt_id)},
            {"$set": {
                "status": "cancelled",
                "cancelled_at": datetime.now()
            }}
        )

        # Notify user on Messenger
        try:
            send_message(
                appt["user_id"],
                f"❌ Your appointment has been cancelled.\n\n"
                f"Service: {appt['service']}\n"
                f"Date: {appt['date']}\n"
                f"Time: {to_ampm(appt['time'])}\n\n"
                "If you'd like to book again, just type *book* 😊"
            )
        except:
            pass  # Don't fail if messenger notification fails

        return jsonify(success=True, message="Appointment cancelled successfully!")
    
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500


@app.route("/cancel-appointment/<appointment_id>", methods=["POST"])
def cancel_appointment(appointment_id):
    result = appointments_collection.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": {"status": "cancelled"}}
    )
    return jsonify({"success": result.modified_count > 0})


@app.route("/payments")
def payments():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    payments = list(appointments_collection.find({
        "payment_status": {"$exists": True}
    }).sort("created_at", -1))

    for p in payments:
        p["_id"] = str(p["_id"])

    return render_template("payments.html", payments=payments)


@app.route("/services")
def services():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    return render_template("services.html")

@app.route("/schedules")
def schedules():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    return render_template("schedules.html")

@app.route("/calendar")
def calendar():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    return render_template("calendar.html")

# -----------------------------
# USER REGISTRATION (ADMIN ONLY)
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    # Check if user is logged in and is an admin
    if "user_id" not in session:
        flash("Please login to access this page.", "danger")
        return redirect(url_for("login"))
    
    if session.get("role") != "admin":
        flash("Access denied. Only admins can create new accounts.", "danger")
        return redirect(url_for("dashboard"))
    
    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", "admin")  # Get role from form

        # Validation
        if not fullname or not email or not password:
            flash("All fields are required!", "danger")
            return redirect(url_for("register"))

        if len(fullname) < 3:
            flash("Full name must be at least 3 characters!", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters!", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect(url_for("register"))

        # Check if email already exists
        if users_collection.find_one({"email": email}):
            flash("Email already registered! Please use a different email.", "danger")
            return redirect(url_for("register"))

        # Hash password and save user
        hashed_pw = generate_password_hash(password)

        users_collection.insert_one({
            "fullname": fullname,
            "email": email,
            "password": hashed_pw,
            "role": role,  # admin or staff
            "created_at": datetime.now(),
            "created_by": session.get("user_id")
        })

        flash(f"Admin account created successfully for {fullname}!", "success")
        return redirect(url_for("register"))  # Stay on page to create more accounts

    return render_template("page-register.html")

# -----------------------------
# USER LOGIN
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in, redirect to dashboard
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password", "danger")
            return redirect(url_for("login"))

        user = users_collection.find_one({"email": email})

        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            session["role"] = user.get("role", "admin")
            session["fullname"] = user["fullname"]
            session["email"] = user["email"]

            flash(f"Welcome back, {user['fullname']}!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password. Please try again.", "danger")
        return redirect(url_for("login"))

    return render_template("page-login.html")

# -----------------------------
# DASHBOARD
# -----------------------------


#payments
@app.route("/api/payments/approve", methods=["POST"])
def approve_payment():
    data = request.json
    appointment_id = data["appointment_id"]

    appt = appointments_collection.find_one({"_id": ObjectId(appointment_id)})
    if not appt:
        return {"success": False}

    appointments_collection.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": {
            "payment_status": "approved",
            "status": "confirmed"
        }}
    )

    # Notify user via Messenger
    send_message(
        appt["user_id"],
        f"✅ Payment Approved! Your appointment is booked!\n\n"
        f"Fullname: {appt['fullname']}\n"
        f"Service: {appt['service']}\n"
        f"Date: {appt['date']}\n"
        f"Time: {to_ampm(appt['time'])}\n"
        f"Payment Method: {appt['payment_method']}"
    )

    return {"success": True}


# -----------------------------
# BOOK APPOINTMENT
# -----------------------------
@app.route("/book", methods=["GET", "POST"])
def book():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        service = request.form["service"]
        date = request.form["date"]
        time = request.form["time"]
        
        # Convert to 24-hour format for storage
        time_24h = to_24h(time)

        appointments_collection.insert_one({
            "user_id": session["user_id"],
            "fullname": session["fullname"],
            "service": service,
            "date": date,
            "time": time_24h,
            "status": "pending",
            "created_at": datetime.now()
        })

        flash("Appointment submitted!", "success")
        return redirect(url_for("my_appointments"))

    services = list(services_collection.find())
    return render_template("appointments.html", services=services)


# -----------------------------
# VIEW MY APPOINTMENTS
# -----------------------------
@app.route("/my-appointments")
def my_appointments():
    if "user_id" not in session:
        return redirect(url_for("login"))

    appts = list(appointments_collection.find({
        "user_id": session["user_id"]
    }))

    return render_template("tables-basic.html", appointments=appts)

# -----------------------------
# PAYMENT (GCash / PayMaya Placeholder)
# -----------------------------
@app.route("/pay/<appointment_id>")
def pay(appointment_id):
    appointment = appointments_collection.find_one({"_id": ObjectId(appointment_id)})

    if not appointment:
        flash("Appointment not found!", "danger")
        return redirect(url_for("my_appointments"))

    amount = 500  # example

    payments_collection.insert_one({
        "appointment_id": appointment_id,
        "amount": amount,
        "method": "pending",
        "status": "pending",
        "created_at": datetime.now()
    })

    return render_template("payments.html", appointment=appointment, amount=amount)

# Temporary in-memory session for each Messenger user
user_state = {}

# -----------------------------
# SEND MESSAGE TO MESSENGER USER
# -----------------------------
def send_message(recipient_id, text, quick_replies=None, attachment=None):
    """
    Send a text message, optional quick replies or attachment (e.g., carousel) to Messenger.
    """
    url = "https://graph.facebook.com/v17.0/me/messages"
    payload = {"recipient": {"id": recipient_id}}

    if attachment:
        payload["message"] = {"attachment": attachment}
    else:
        payload["message"] = {"text": text}

    if quick_replies:
        payload["message"]["quick_replies"] = quick_replies

    requests.post(url, params={"access_token": PAGE_ACCESS_TOKEN}, json=payload)


# -----------------------------
# SEND SERVICES CAROUSEL
# -----------------------------
def send_services_carousel(recipient_id):
    services = list(services_collection.find())
    if not services:
        send_message(recipient_id, "No services available at the moment.")
        return

    elements = []
    for s in services:
        elements.append({
            "title": s["name"],
            "subtitle": f"Price: ₱{s['price']} | Duration: {s['duration']} mins",
            "buttons": [
                {
                    "type": "postback",
                    "title": "Select",
                    "payload": f"SERVICE_{s['_id']}"
                }
            ]
        })

    attachment = {
        "type": "template",
        "payload": {
            "template_type": "generic",
            "elements": elements
        }
    }

    send_message(recipient_id, "Please choose a service:", attachment=attachment)


# -----------------------------
# SEND DATE QUICK REPLIES
# -----------------------------
def send_date_quick_replies(recipient_id):
    quick_replies = [
        {"content_type": "text", "title": "Tomorrow", "payload": "DATE_TOMORROW"},
        {"content_type": "text", "title": "Next Monday", "payload": "DATE_NEXT_MONDAY"},
        {"content_type": "text", "title": "Pick a Date", "payload": "DATE_PICK"}
    ]
    send_message(recipient_id, "When would you like your appointment?", quick_replies=quick_replies)


# -----------------------------
# SEND TIME QUICK REPLIES
# -----------------------------
def send_time_quick_replies(recipient_id):
    quick_replies = [
        {"content_type": "text", "title": "9:00 AM", "payload": "TIME_09"},
        {"content_type": "text", "title": "1:00 PM", "payload": "TIME_13"},
        {"content_type": "text", "title": "3:00 PM", "payload": "TIME_15"}
    ]
    send_message(recipient_id, "At what time?", quick_replies=quick_replies)


# -----------------------------
# SEND PAYMENT QUICK REPLIES
# -----------------------------
def send_payment_options(recipient_id):
    quick_replies = [
        {"content_type": "text", "title": "PayMaya", "payload": "PAYMENT_PAYMAYA"},
        {"content_type": "text", "title": "GCash", "payload": "PAYMENT_GCASH"},
        {"content_type": "text", "title": "Over the Counter", "payload": "PAYMENT_COUNTER"}
    ]
    send_message(recipient_id, "Choose a payment method for your down payment:", quick_replies=quick_replies)

def send_confirm_cancel(recipient_id):
    quick_replies = [
        {"content_type": "text", "title": "Confirm", "payload": "CONFIRM_BOOKING"},
        {"content_type": "text", "title": "Cancel", "payload": "CANCEL_BOOKING"}
    ]
    send_message(recipient_id, "Do you want to confirm your appointment?", quick_replies=quick_replies)





def parse_date_payload(payload):
    today = datetime.now().date()
    if payload == "DATE_TOMORROW":
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif payload == "DATE_NEXT_MONDAY":
        days_ahead = (0 - today.weekday() + 7) % 7
        if days_ahead == 0:  # If today is Monday, get next Monday
            days_ahead = 7
        return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    else:
        return payload  # For custom date picker

def get_or_create_messenger_user(sender_id):
    user = messenger_users_collection.find_one({"sender_id": sender_id})
    if not user:
        messenger_users_collection.insert_one({
            "sender_id": sender_id,
            "fullname": "Messenger User",
            "state": {"step": None, "service_id": None, "service_name": None, "date": None, "time": None},
            "created_at": datetime.now()
        })
        user = messenger_users_collection.find_one({"sender_id": sender_id})
    return user

def update_user_state(sender_id, state):
    messenger_users_collection.update_one(
        {"sender_id": sender_id},
        {"$set": {"state": state}}
    )



# -----------------------------
# HANDLE USER MESSAGE
# -----------------------------
from datetime import datetime

def handle_user_message(sender, text):
    if sender not in user_state:
        user_state[sender] = {
            "step": None,
            "fullname": None,
            "service_id": None,
            "service_name": None,
            "downpayment": None,
            "date": None,
            "time": None,
            "payment_method": None,
            "payment_proof": None,
            "last_activity": datetime.now()
        }

    state = user_state[sender]
    state["last_activity"] = datetime.now()  # Track activity

    # -------------------------
    # STEP 1: CHOOSE SERVICE
    # -------------------------
    if state["step"] == "choose_service":
        if text.startswith("SERVICE_"):
            service_id = text.replace("SERVICE_", "")
            
            try:
                service = services_collection.find_one({"_id": ObjectId(service_id)})
            except Exception as e:
                print(f"Database error: {e}")
                send_message(sender, "❌ Sorry, there was an error. Please try again.")
                return

            if not service:
                send_message(sender, "Invalid service. Please choose again.")
                send_services_carousel(sender)
                return

            state["service_id"] = str(service["_id"])
            state["service_name"] = service["name"]
            state["downpayment"] = service.get("downpayment", 0)
            state["step"] = "choose_date"

            send_message(sender, f"✅ You selected: {service['name']}")
            send_date_quick_replies(sender)
            return

        send_services_carousel(sender)
        return

    # -------------------------
    # STEP 2: CHOOSE DATE - WITH TIMEOUT FIX
    # -------------------------
    if state["step"] == "choose_date":

        # Handle "Pick a Date" option - ask user to type date manually
        if text in ["DATE_PICK", "date_manual"]:
            send_message(sender, "📅 Please type your preferred date in this format:\nYYYY-MM-DD\n\nExample: 2025-12-25")
            state["step"] = "awaiting_manual_date"
            return

        # Validate date format
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            send_message(sender, "❌ Invalid date format.\nPlease use YYYY-MM-DD (e.g., 2025-12-25)")
            return

        state["date"] = text

        # ✅ FIX: Add timeout and error handling for API call
        try:
            print(f"Fetching free times for {text}...")  # Debug log
            resp = requests.get(
                f"{BASE_URL}/api/free-times/{text}",
                timeout=10  # 10 second timeout
            )
            resp.raise_for_status()  # Raise error for bad status codes
            free_times = resp.json()
            print(f"Got {len(free_times)} free times")  # Debug log
            
        except requests.exceptions.Timeout:
            print(f"Timeout fetching free times for {text}")
            send_message(
                sender, 
                "⚠️ The server is taking too long to respond. Please try again in a moment."
            )
            send_date_quick_replies(sender)
            return
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching free times: {e}")
            send_message(
                sender,
                "❌ Sorry, there was an error checking availability.\n\nPlease try selecting a different date."
            )
            send_date_quick_replies(sender)
            return
            
        except Exception as e:
            print(f"Unexpected error: {e}")
            send_message(sender, "❌ An unexpected error occurred. Please try again.")
            return

        # Check if any times are available
        if not free_times or len(free_times) == 0:
            send_message(sender, "❌ No available times on this date.\n\nPlease choose another date.")
            send_date_quick_replies(sender)
            return

        # ✅ Times are already in AM/PM format from API
        quick_replies = [
            {"content_type": "text", "title": time_ampm, "payload": f"TIME_{time_ampm}"}
            for time_ampm in free_times[:13]  # Limit to 13 options (Messenger limit)
        ]

        send_message(sender, "⏰ Select from these available times:", quick_replies=quick_replies)
        state["step"] = "choose_time"
        return

    # -------------------------
    # STEP 2B: AWAITING MANUAL DATE ENTRY
    # -------------------------
    if state["step"] == "awaiting_manual_date":
        # Validate date format
        try:
            parsed_date = datetime.strptime(text, "%Y-%m-%d")
            
            # Check if date is in the past
            if parsed_date.date() < datetime.now().date():
                send_message(sender, "❌ Cannot book appointments in the past.\n\nPlease enter a future date.")
                return
                
        except ValueError:
            send_message(sender, "❌ Invalid date format.\nPlease use YYYY-MM-DD (e.g., 2025-12-25)")
            return

        state["date"] = text
        
        # Process the date immediately with timeout protection
        try:
            print(f"Fetching free times for manual date {text}...")
            resp = requests.get(
                f"{BASE_URL}/api/free-times/{text}",
                timeout=10
            )
            resp.raise_for_status()
            free_times = resp.json()
            print(f"Got {len(free_times)} free times")
            
        except requests.exceptions.Timeout:
            print(f"Timeout fetching free times for manual date {text}")
            send_message(
                sender,
                "⚠️ The server is taking too long to respond. Please try again in a moment."
            )
            state["step"] = "choose_date"
            send_date_quick_replies(sender)
            return
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching free times for manual date: {e}")
            send_message(
                sender,
                "❌ Sorry, there was an error checking availability.\n\nPlease try a different date."
            )
            state["step"] = "choose_date"
            send_date_quick_replies(sender)
            return

        if not free_times or len(free_times) == 0:
            send_message(sender, "❌ No available times on this date.\n\nPlease choose another date.")
            state["step"] = "choose_date"
            send_date_quick_replies(sender)
            return

        # ✅ Times are already in AM/PM format from API
        quick_replies = [
            {"content_type": "text", "title": time_ampm, "payload": f"TIME_{time_ampm}"}
            for time_ampm in free_times[:13]  # Limit to 13 options
        ]

        send_message(sender, "⏰ Select from these available times:", quick_replies=quick_replies)
        state["step"] = "choose_time"
        return

    # -------------------------
    # STEP 3: CHOOSE TIME
    # -------------------------
    if state["step"] == "choose_time":
        # Store time in 24-hour format
        try:
            state["time"] = to_24h(text)
        except Exception as e:
            print(f"Error converting time: {e}")
            send_message(sender, "❌ Invalid time format. Please select a time from the options.")
            return
            
        state["step"] = "ask_name"
        send_message(sender, "📝 Please type your full name for the appointment:")
        return
        
    if state["step"] == "ask_name":
        state["fullname"] = text
        
        try:
            service = services_collection.find_one(
                {"_id": ObjectId(state["service_id"])}
            )
        except Exception as e:
            print(f"Database error fetching service: {e}")
            send_message(sender, "❌ Sorry, there was an error. Please try booking again.")
            user_state[sender] = {"step": None}
            return

        if not service:
            send_message(sender, "❌ Service not found. Please start over.")
            user_state[sender] = {"step": None}
            return

        downpayment = service.get("downpayment", 0)
        state["downpayment"] = downpayment
        state["step"] = "confirm_downpayment"

        send_message(
            sender,
            f"Hi {state['fullname']}! 😊\n\n"
            f"The service **{state['service_name']}** requires a ₱{downpayment:,.2f} downpayment.\n\n"
            f"Do you want to continue?",
            quick_replies=[
                {"content_type": "text", "title": "Yes", "payload": "DP_YES"},
                {"content_type": "text", "title": "No", "payload": "DP_NO"}
            ]
        )
        return

    if state["step"] == "confirm_downpayment":

        if text == "DP_NO":
            send_message(sender, "No problem! 😊 Feel free to reach out when you're ready.")
            user_state[sender] = {"step": None}
            return

        if text == "DP_YES":
            state["step"] = "choose_payment"
            send_payment_options(sender)
            return

    # -------------------------
    # STEP 4: CHOOSE PAYMENT METHOD
    # -------------------------
    if state["step"] == "choose_payment" and text.startswith("PAYMENT_"):
        method = text.replace("PAYMENT_", "")
        state["payment_method"] = method
        state["step"] = "send_proof"

        payment_info = {
            "GCASH": "📱 **GCASH PAYMENT**\n\n💰 Amount: ₱{:.2f}\n📞 Send to: 0912 345 6789\n👤 Name: Jaylon Dental Clinic".format(state["downpayment"]),
            "PAYMAYA": "💳 **PAYMAYA PAYMENT**\n\n💰 Amount: ₱{:.2f}\n📞 Send to: 0912 345 6789\n👤 Name: Jaylon Dental Clinic".format(state["downpayment"]),
            "COUNTER": "🏥 **OVER THE COUNTER**\n\n💰 Amount: ₱{:.2f}\n📍 Pay directly at:\nJaylon Dental Clinic\nStall 13 Bldg. 06 Public Market, Makilala".format(state["downpayment"])
        }

        send_message(
            sender,
            f"{payment_info.get(method, 'Payment details')}\n\n📸 After payment, please send a screenshot or photo of the receipt here."
        )
        return

    # -------------------------
    # STEP 5: RECEIVE PAYMENT PROOF
    # -------------------------
    if state["step"] == "send_proof":
        state["payment_proof"] = text

        try:
            appointment_id = appointments_collection.insert_one({
                "fullname": state["fullname"],
                "user_id": sender,
                "service": state["service_name"],
                "date": state["date"],
                "time": state["time"],  # Stored in 24-hour format
                "downpayment": state["downpayment"],
                "payment_method": state["payment_method"],
                "payment_proof": text,
                "payment_status": "pending",
                "status": "pending",
                "created_at": datetime.now()
            }).inserted_id

            state["appointment_id"] = str(appointment_id)
            state["step"] = "waiting_admin"

            send_message(
                sender,
                "✅ **Proof received!**\n\n⏳ Please wait while the admin confirms your down payment.\n\n"
                "You'll receive a notification once confirmed."
            )
        except Exception as e:
            print(f"Error saving appointment: {e}")
            send_message(sender, "❌ Sorry, there was an error saving your appointment. Please try again.")
        
        return

    # -------------------------
    # RESCHEDULE
    # -------------------------
    if state["step"] == "choose_new_date":
        # Validate date format
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            send_message(sender, "❌ Invalid date format.\nPlease use YYYY-MM-DD")
            return
            
        state["new_date"] = text
        
        try:
            resp = requests.get(f"{BASE_URL}/api/free-times/{text}", timeout=10)
            resp.raise_for_status()
            free_times = resp.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching times for reschedule: {e}")
            send_message(sender, "❌ Error checking availability. Please try again.")
            return

        if not free_times:
            send_message(sender, "❌ No available times on this date.")
            send_date_quick_replies(sender)
            return

        quick_replies = [
            {"content_type": "text", "title": time_ampm, "payload": f"TIME_{time_ampm}"}
            for time_ampm in free_times[:13]
        ]

        send_message(sender, "⏰ Select a new time:", quick_replies=quick_replies)
        state["step"] = "choose_new_time"
        return

    if state["step"] == "choose_new_time":
        try:
            new_time_24h = to_24h(text)
            
            appointments_collection.update_one(
                {"_id": ObjectId(state["appointment_id"])},
                {
                    "$set": {
                        "date": state["new_date"],
                        "time": new_time_24h,
                        "status": "rescheduled",
                        "updated_at": datetime.now()
                    }
                }
            )

            send_message(
                sender,
                f"✅ **Appointment Rescheduled!**\n\n📅 New Date: {state['new_date']}\n⏰ New Time: {text}"
            )

            user_state[sender] = {"step": None}
        except Exception as e:
            print(f"Error rescheduling: {e}")
            send_message(sender, "❌ Error rescheduling appointment. Please try again.")
        
        return
    
    # -------------------------
    # CONFIRM CANCEL FLOW
    # -------------------------
    if state["step"] == "confirm_cancel":

        if text == "CANCEL_NO":
            send_message(sender, "👍 No problem! Your appointment is still active.")
            user_state[sender] = {"step": None}
            return

        if text == "CANCEL_YES":
            try:
                appointments_collection.update_one(
                    {"_id": ObjectId(state["appointment_id"])},
                    {
                        "$set": {
                            "status": "cancelled",
                            "updated_at": datetime.now()
                        }
                    }
                )

                send_message(sender, "❌ Your appointment has been cancelled.")
                user_state[sender] = {"step": None}
            except Exception as e:
                print(f"Error cancelling appointment: {e}")
                send_message(sender, "❌ Error cancelling appointment. Please try again.")
            
            return

    # -------------------------
    # FALLBACK
    # -------------------------
    send_message(sender, "Hi! 👋 Tap **Book Appointment** from the menu to get started 😊")


# -------------------------
# IMPROVED SEND MESSAGE WITH TIMEOUT
# -------------------------
def send_message(recipient_id, text, quick_replies=None, attachment=None):
    """
    Send a text message, optional quick replies or attachment to Messenger.
    """
    url = "https://graph.facebook.com/v17.0/me/messages"
    payload = {"recipient": {"id": recipient_id}}

    if attachment:
        payload["message"] = {"attachment": attachment}
    else:
        payload["message"] = {"text": text}

    if quick_replies:
        payload["message"]["quick_replies"] = quick_replies

    try:
        response = requests.post(
            url, 
            params={"access_token": PAGE_ACCESS_TOKEN}, 
            json=payload,
            timeout=5  # 5 second timeout
        )
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending message to {recipient_id}: {e}")
        return False



# MESSENGER WEBHOOK
# -----------------------------
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        verify_token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if verify_token == VERIFY_TOKEN:
            return challenge
        return "Invalid verification token", 403

    data = request.get_json()
    if "entry" in data:
        for entry in data["entry"]:
            for event in entry.get("messaging", []):
                sender = event["sender"]["id"]

                # -----------------------------
                # HANDLE POSTBACKS (CAROUSEL & MENU)
                # -----------------------------
                if "postback" in event:
                    payload = event["postback"]["payload"]

                    if payload == "BOOK_APPT":
                        send_message(sender, "Sure! Let's book your appointment. What service do you need?")
                        user_state[sender] = {"step": "choose_service", "service_id": None, "service_name": None,
                                              "date": None, "time": None, "payment_method": None}
                        send_services_carousel(sender)
                        continue

                    if payload == "MY_APPOINTMENTS":
                        send_my_appointments_carousel(sender)
                        user_state[sender] = {"step": "manage_appointment"}
                        continue


                    if payload == "VIEW_SERVICES":
                        send_services_carousel(sender)
                        continue

                    if payload == "CONTACT_US":
                        send_message(sender, "📍 Jaylon Dental Clinic\nStall 13 Bldg. 06 Public Market, Makilala, Philippines\n📞 +639950027408\n 📧 jaylondentalclinic.makilala@gmail.com")
                        continue

                    if payload.startswith("SERVICE_"):
                        handle_user_message(sender, payload)
                        continue

                    if payload.startswith("RESCHED_"):
                        appointment_id = payload.replace("RESCHED_", "")
                        user_state[sender] = {
                            "step": "choose_new_date",
                            "appointment_id": appointment_id
                        }
                        send_date_quick_replies(sender)
                        continue

                    if payload.startswith("CANCEL_"):
                        appointment_id = payload.replace("CANCEL_", "")
                        user_state[sender] = {
                            "step": "confirm_cancel",
                            "appointment_id": appointment_id
                        }

                        send_message(
                            sender,
                            "⚠️ Are you sure you want to cancel this appointment?",
                            quick_replies=[
                                {"content_type": "text", "title": "Yes, Cancel", "payload": "CANCEL_YES"},
                                {"content_type": "text", "title": "No", "payload": "CANCEL_NO"}
                            ]
                        )
                        continue
                    





                # -----------------------------
                # HANDLE MESSAGES
                # -----------------------------
                if "message" in event:
                    message = event["message"]

                    # Handle quick replies
                    if "quick_reply" in message and "payload" in message["quick_reply"]:
                        payload = message["quick_reply"]["payload"]

                        # -----------------------------
                        # MANUAL DATE ENTRY
                        # -----------------------------
                        if payload == "DATE_MANUAL":
                            handle_user_message(sender, "date_manual")
                            continue

                        # -----------------------------
                        # PREDEFINED DATE QUICK REPLIES
                        # -----------------------------
                        if payload.startswith("DATE_"):
                            date_value = parse_date_payload(payload)
                            handle_user_message(sender, date_value)
                            continue

                        # -----------------------------
                        # TIME SELECTION
                        # -----------------------------
                        if payload.startswith("TIME_"):
                            # Time is already in AM/PM format from quick reply
                            time_value = payload.replace("TIME_", "")
                            handle_user_message(sender, time_value)
                            continue

                        # -----------------------------
                        # DOWNPAYMENT CONFIRMATION
                        # -----------------------------
                        if payload in ["DP_YES", "DP_NO"]:
                            handle_user_message(sender, payload)
                            continue


                        # -----------------------------
                        # PAYMENT METHODS
                        # -----------------------------
                        if payload.startswith("PAYMENT_"):
                            handle_user_message(sender, payload)
                            continue

                        # -----------------------------
                        # CONFIRM / CANCEL BOOKING
                        # -----------------------------
                        if payload in ["CONFIRM_BOOKING", "CANCEL_BOOKING"]:
                            handle_user_message(sender, payload)
                            continue

                        # -----------------------------
                        # CONFIRM CANCEL QUICK REPLIES
                        # -----------------------------
                        if payload in ["CANCEL_YES", "CANCEL_NO"]:
                            handle_user_message(sender, payload)
                            continue


                    # USER TYPED TEXT OR ATTACHMENTS
                    # Inside /webhook
                    if "attachments" in message:
                        for att in message["attachments"]:
                            if att["type"] == "image":
                                image_url = att["payload"]["url"]
                                # Send to handle_user_message to treat as payment proof
                                handle_user_message(sender, image_url)


                    elif "text" in message:
                        text = message["text"].strip()
                        handle_user_message(sender, text)

    return "OK", 200

def notify_payment_approved(appointment):
    send_message(
        appointment["user_id"],
        f"✅ Payment Approved! Your appointment is booked!\n\n"
        f"Service: {appointment['service']}\n"
        f"Date: {appointment['date']}\n"
        f"Time: {to_ampm(appointment['time'])}\n"
        f"Payment Method: {appointment['payment_method']}"
    )

def send_user_appointments_carousel(sender_id):
    appointments = list(
        appointments_collection.find({
            "user_id": sender_id,
            "status": {"$in": ["pending", "approved", "rescheduled"]}
        })
    )

    if not appointments:
        send_message(sender_id, "❌ You don't have any appointments to reschedule.")
        return

    elements = []
    for appt in appointments:
        elements.append({
            "title": appt["service"],
            "subtitle": f"📅 {appt['date']} ⏰ {to_ampm(appt['time'])}",
            "buttons": [
                {
                    "type": "postback",
                    "title": "Reschedule",
                    "payload": f"RESCHED_{appt['_id']}"
                }
            ]
        })

    attachment = {
        "type": "template",
        "payload": {
            "template_type": "generic",
            "elements": elements
        }
    }

    send_message(sender_id, "Select an appointment to reschedule:", attachment=attachment)

def send_my_appointments_carousel(sender_id):
    appointments = list(
        appointments_collection.find({
            "user_id": sender_id,
            "status": {"$in": ["pending", "approved", "rescheduled"]}
        })
    )

    if not appointments:
        send_message(sender_id, "📭 You don't have any active appointments.")
        return

    elements = []
    for appt in appointments:
        elements.append({
            "title": appt["service"],
            "subtitle": f"📅 {appt['date']} ⏰ {to_ampm(appt['time'])}",
            "buttons": [
                {
                    "type": "postback",
                    "title": "🔄 Reschedule",
                    "payload": f"RESCHED_{appt['_id']}"
                },
                {
                    "type": "postback",
                    "title": "❌ Cancel",
                    "payload": f"CANCEL_{appt['_id']}"
                }
            ]
        })

    attachment = {
        "type": "template",
        "payload": {
            "template_type": "generic",
            "elements": elements
        }
    }

    send_message(sender_id, "Here are your appointments:", attachment=attachment)


# -----------------------------
# PERSISTENT MENU
# -----------------------------

def setup_persistent_menu():
    url = f"https://graph.facebook.com/v17.0/me/messenger_profile?access_token={PAGE_ACCESS_TOKEN}"

    menu = {
        "persistent_menu": [
            {
                "locale": "default",
                "composer_input_disabled": False,
                "call_to_actions": [
                    {"type": "postback", "title": "🗓 Book Appointment", "payload": "BOOK_APPT"},
                    {"type": "postback", "title": "📋 My Appointments", "payload": "MY_APPOINTMENTS"},
                    {"type": "postback", "title": "🦷 View Services", "payload": "VIEW_SERVICES"},
                    {"type": "postback", "title": "📞 Contact Us", "payload": "CONTACT_US"},
                ]
            },
            {
                "locale": "en_US", 
                "composer_input_disabled": False,
                "call_to_actions": [
                    {"type": "postback", "title": "🗓 Book Appointment", "payload": "BOOK_APPT"},
                    {"type": "postback", "title": "📋 My Appointments", "payload": "MY_APPOINTMENTS"},
                    {"type": "postback", "title": "🦷 View Services", "payload": "VIEW_SERVICES"},
                    {"type": "postback", "title": "📞 Contact Us", "payload": "CONTACT_US"},
                ]
            }
        ]
    }

    res = requests.post(url, json=menu)
    print("MENU RESPONSE:", res.json())

def notify_payment_declined(appointment, reason):
    """
    Notify the user via Messenger that their payment was declined.
    """
    try:
        user_id = appointment.get("user_id")
        fullname = appointment.get("fullname")
        service = appointment.get("service")
        date = appointment.get("date")
        time = appointment.get("time")
        payment_method = appointment.get("payment_method")

        # Optional: send Messenger notification
        if user_id:
            send_message(
                user_id,
                f"❌ Your payment for {service} on {date} at {to_ampm(time)} has been declined.\n"
                f"Reason: {reason}\n"
                "Please contact the clinic if you have questions."
            )
        print(f"Payment declined for {fullname} ({appointment['_id']}): {reason}")
    except Exception as e:
        print("Error notifying user about declined payment:", e)


@app.route("/api/payments/decline", methods=["POST"])
def decline_payment():
    try:
        data = request.get_json()
        appointment_id = data.get("appointment_id")
        reason = data.get("reason")

        if not appointment_id or not reason:
            return jsonify({"success": False, "error": "Missing appointment_id or reason"}), 400

        appointment = appointments_collection.find_one({"_id": ObjectId(appointment_id)})
        if not appointment:
            return jsonify({"success": False, "error": "Appointment not found"}), 404

        # Update payment status in DB
        appointments_collection.update_one(
            {"_id": ObjectId(appointment_id)},
            {
                "$set": {
                    "payment_status": "declined",
                    "status": "declined",
                    "decline_reason": reason,
                    "updated_at": datetime.now()
                }
            }
        )

        # Notify user
        notify_payment_declined(appointment, reason)

        return jsonify({"success": True})

    except Exception as e:
        print("DECLINE PAYMENT ERROR:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/setup-menu")
def setup_menu():
    setup_persistent_menu()
    return "Persistent menu installed!"



# -----------------------------
# SERVICES
# -----------------------------

@app.route("/get-services")
def get_services():
    services = list(services_collection.find())
    for s in services:
        s["_id"] = str(s["_id"])
    return jsonify(services)


@app.route("/add-service", methods=["POST"])
def add_service():
    data = request.json
    services_collection.insert_one({
        "name": data["name"],
        "price": float(data["price"]),
        "downpayment": float(data["downpayment"]),
        "duration": int(data["duration"])
    })
    return {"success": True}


@app.route("/update-service", methods=["POST"])
def update_service():
    data = request.json
    services_collection.update_one(
        {"_id": ObjectId(data["id"])},
        {"$set": {
            "name": data["name"],
            "price": float(data["price"]),
            "downpayment": float(data["downpayment"]),
            "duration": int(data["duration"])
        }}
    )
    return {"success": True}


@app.route("/delete-service/<id>", methods=["DELETE"])
def delete_service(id):
    services_collection.delete_one({"_id": ObjectId(id)})
    return {"success": True}



# -----------------------------
# CALENDAR EVENTS
# -----------------------------

@app.route("/api/calendar")
def get_calendar_events():
    events = []

    slots = list(calendar_collection.find())
    for s in slots:
        color = "#28a745" if s["status"] == "available" else "#dc3545"
        events.append({
            "id": str(s["_id"]),
            "title": s["status"].upper(),
            "start": f"{s['date']}T{s['time']}",
            "color": color
        })

    return jsonify(events)

@app.route("/api/blocked-slots")
def blocked_slots():
    events = []
    blocks = blocked_collection.find()


    for b in blocks:
        start = f"{b['date']}T{b['start']}"
        end = f"{b['date']}T{b['end']}"


        events.append({
            "id": str(b['_id']),
            "title": "Blocked",
            "start": start,
            "end": end,
            "color": "#6c757d", # gray
            "editable": False
        })


    return jsonify(events)

@app.route("/api/block", methods=["POST"])
def create_block():
    data = request.json


    blocked_collection.insert_one({
        "date": data["date"],
        "start": data["start"],
        "end": data["end"],
        "reason": data.get("reason", "Blocked")
    })


    return {"success": True}

@app.route("/api/calendar/add", methods=["POST"])
def add_calendar_slot():
    data = request.json

    calendar_collection.insert_one({
        "date": data["date"],
        "time": data["time"],
        "status": "available",
        "appointment_id": None
    })
    return jsonify({"success": True})

@app.route("/api/calendar/delete", methods=["POST"])
def delete_calendar_slot():
    data = request.json
    calendar_collection.delete_one({"_id": ObjectId(data["id"])})
    return jsonify({"success": True})

@app.route("/api/calendar-events")
def calendar_events():
    events = []
    appointments = appointments_collection.find()


    for a in appointments:
        start = f"{a['date']}T{a['time']}"
        events.append({
            "id": str(a['_id']),
            "title": f"{a['fullname']} - {a['service']}",
            "start": start,
            "color": "#dc3545" # red = booked
        })


    return jsonify(events)

@app.route("/api/free-times/<date>")
def free_times(date):
    """
    Return a list of available time slots in 12-hour AM/PM format for a given date.
    """
    # All possible clinic times in 24-hour format
    all_times_24h = ["09:00", "10:00", "11:00", "13:00", "14:00", "15:00", "16:00"]

    # Get booked slots
    booked = appointments_collection.find({"date": date})
    booked_times = [b["time"] for b in booked]

    # Get blocked slots
    blocked = blocked_collection.find({"date": date})
    blocked_times = []
    for b in blocked:
        start_hour = int(b["start"].split(":")[0])
        end_hour = int(b["end"].split(":")[0])
        for h in range(start_hour, end_hour):
            blocked_times.append(f"{h:02d}:00")

    # Compute free times in 24-hour format
    free_24h = [t for t in all_times_24h if t not in booked_times and t not in blocked_times]
    
    # ✅ Convert to 12-hour AM/PM format for display
    free_12h = [to_ampm(t) for t in free_24h]

    return jsonify(free_12h)


@app.route("/api/unblock", methods=["POST"])
def api_unblock():
    data = request.get_json()
    event_id = data.get("eventId")
    result = blocked_collection.delete_one({"_id": ObjectId(event_id)})
    if result.deleted_count == 0:
        return jsonify({"success": False, "message": "Event not found"})
    return jsonify({"success": True, "message": "Blocked slot removed"})

@app.route("/unblock/<slot_id>", methods=["GET"])
def unblock_slot_browser(slot_id):
    """
    Remove a blocked slot by its ID via a browser link.
    Example: /unblock/64b8f0a2e1f3c9d123456789
    """
    result = blocked_collection.delete_one({"_id": ObjectId(slot_id)})

    if result.deleted_count == 0:
        flash("Blocked slot not found.", "danger")
    else:
        flash("Blocked slot removed successfully.", "success")

    return redirect(url_for("calendar"))  # redirect back to your calendar page


# -----------------------------
# LOGOUT
# -----------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/admin/refresh-menu")
def admin_refresh_menu():
    if request.args.get("key") != app.config["SECRET_KEY"]:
        return "Unauthorized", 401

    setup_persistent_menu()
    return "Menu refreshed"




# -----------------------------
# RUN SERVER
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)
