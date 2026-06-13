# ============================================================
#   PARKING SLOT MANAGER — FLASK API (Part 2)
#   This file connects the core logic to the web.
#   Frontend sends requests here → we call parking_manager.py
# ============================================================

from flask import Flask, request, jsonify  # Flask tools
from flask_cors import CORS                # Allows frontend to talk to backend
from parking_manager import ParkingManager # Our core logic from Part 1

# ============================================================
# APP SETUP
# ============================================================

app = Flask(__name__)   # Create the Flask app
CORS(app)               # Allow cross-origin requests (frontend on different port)

# Create ONE instance of ParkingManager — this lives in memory
# Think of it as turning the lights on in the parking lot
manager = ParkingManager()


# ============================================================
# WHAT IS A ROUTE?
# A route is a URL that the frontend can call. 
# Example: frontend calls "/api/setup" → Flask runs setup()
#
# WHAT IS jsonify()?
# Converts Python dict → JSON so frontend can read it
#
# WHAT IS request.get_json()?
# Reads the data that frontend SENT to us
# ============================================================


# ============================================================
# ROUTE 1 — SETUP
# POST /api/setup
# Manager sends configuration → we set up the lot
# ============================================================

@app.route("/api/setup", methods=["POST"])
def setup():
    data = request.get_json()  # Get data sent from frontend

    # Extract each field from the data
    total_slots        = data.get("total_slots")
    priority_slots     = data.get("priority_slots", [])     # Default empty list
    fields_to_collect  = data.get("fields_to_collect", [])
    rate_per_5min      = data.get("rate_per_5min")
    fine_per_10min     = data.get("fine_per_10min")

    # Basic validation — make sure required fields are present
    if not total_slots or not rate_per_5min or not fine_per_10min:
        return jsonify({"success": False, "message": "Missing required fields!"}), 400

    # Call the core logic
    result = manager.setup(
        total_slots=int(total_slots),   
        priority_slots=[int(s) for s in priority_slots],  # Convert to integers
        fields_to_collect=fields_to_collect,
        rate_per_5min=float(rate_per_5min),
        fine_per_10min=float(fine_per_10min)
    )

    return jsonify(result)


# ============================================================
# ROUTE 2 — GET SETUP INFO
# GET /api/setup
# Frontend asks "what fields should I collect from parker?"
# ============================================================

@app.route("/api/setup", methods=["GET"])
def get_setup():
    if not manager.is_setup_done:
        return jsonify({"success": False, "message": "Setup not done yet!"})

    return jsonify({
        "success": True,
        "total_slots": manager.total_slots,
        "priority_slots": manager.priority_slots,
        "fields_to_collect": manager.fields_to_collect,
        "rate_per_5min": manager.rate_per_5min,
        "fine_per_10min": manager.fine_per_10min
    })


# ============================================================
# ROUTE 3 — ASSIGN SLOT (Parker Entry)
# POST /api/assign
# Frontend sends parker details → we assign best slot
# ============================================================

@app.route("/api/assign", methods=["POST"])
def assign():
    data = request.get_json()

    # Duration is required always
    duration_minutes = data.get("duration_minutes")
    if not duration_minutes:
        return jsonify({"success": False, "message": "Duration is required!"}), 400

    # Build parker_details dict from only the fields manager configured
    # This respects the manager's setup choices
    parker_details = {}
    for field in manager.fields_to_collect:
        parker_details[field] = data.get(field, "")  # Empty string if not provided

    # Call core logic
    result = manager.assign_slot(
        parker_details=parker_details,
        duration_minutes=int(duration_minutes)
    )

    return jsonify(result)


# ============================================================
# ROUTE 4 — DASHBOARD
# GET /api/dashboard
# Frontend asks for all slot statuses
# ============================================================

@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    result = manager.get_dashboard()

    # datetime objects can't be sent as JSON directly
    # We use a COPY so we don't mutate the real data in memory!
    import copy
    if result["success"]:
        safe_result = copy.deepcopy(result)
        for slot in safe_result["dashboard"]:
            if slot["parker"]:
                parker = slot["parker"]
                if "entry_time" in parker and hasattr(parker["entry_time"], "strftime"):
                    parker["entry_time"] = parker["entry_time"].strftime("%H:%M:%S")
        return jsonify(safe_result)

    return jsonify(result)


# ============================================================
# ROUTE 5 — SEARCH
# GET /api/search?query=Raj   OR   /api/search?query=3
# Frontend passes a search term in the URL
# ============================================================

@app.route("/api/search", methods=["GET"])
def search():
    # "query" comes from the URL: /api/search?query=something
    query = request.args.get("query", "")

    if not query:
        return jsonify({"success": False, "message": "Please provide a search query!"})

    result = manager.search(query)

    # Use deepcopy so we don't mutate real data
    import copy
    if result["success"]:
        safe_result = copy.deepcopy(result)
        for item in safe_result["results"]:
            parker = item["parker"]
            if "entry_time" in parker and hasattr(parker["entry_time"], "strftime"):
                parker["entry_time"] = parker["entry_time"].strftime("%H:%M:%S")
        return jsonify(safe_result)

    return jsonify(result)


# ============================================================
# ROUTE 6 — CHECKOUT
# GET /api/checkout/<slot_no>
# Frontend asks for bill details of a slot
# <slot_no> is a variable in the URL e.g. /api/checkout/3
# ============================================================

@app.route("/api/checkout/<int:slot_no>", methods=["GET"])
def checkout(slot_no):
    result = manager.checkout(slot_no)

    if result["success"]:
        # Fix 1: Convert entry_time in parker dict (raw datetime object)
        parker = result["parker"]
        if "entry_time" in parker and hasattr(parker["entry_time"], "strftime"):
            parker["entry_time"] = parker["entry_time"].strftime("%H:%M:%S")

        # Fix 2: entry_time inside time_info is already a string (from _calculate_time)
        # but double-check just in case
        time_info = result.get("time_info", {})
        if "entry_time" in time_info and hasattr(time_info["entry_time"], "strftime"):
            time_info["entry_time"] = time_info["entry_time"].strftime("%H:%M:%S")

    return jsonify(result)


# ============================================================
# ROUTE 7 — FREE SLOT
# POST /api/free/<slot_no>
# After checkout confirmed → free the slot
# ============================================================

@app.route("/api/free/<int:slot_no>", methods=["POST"])
def free_slot(slot_no):
    data = request.get_json()
    payment_status = data.get("payment_status", "unpaid")

    result = manager.free_slot(slot_no, payment_status)
    return jsonify(result)


# ============================================================
# ROUTE 8 — UPDATE PAYMENT
# POST /api/payment/<slot_no>
# Update payment status anytime
# ============================================================

@app.route("/api/payment/<int:slot_no>", methods=["POST"])
def update_payment(slot_no):
    data = request.get_json()
    payment_status = data.get("payment_status")

    if not payment_status:
        return jsonify({"success": False, "message": "Payment status required!"}), 400

    result = manager.update_payment(slot_no, payment_status)
    return jsonify(result)


# ============================================================
# ROUTE 9 — HEALTH CHECK
# GET /api/health
# Just to confirm the server is running
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "success": True,
        "message": "Server is running!",
        "setup_done": manager.is_setup_done
    })


# ============================================================
# START THE SERVER
# This runs when you do: python app.py
# debug=True → auto restarts when you save changes (great for dev!)
# ============================================================

if __name__ == "__main__":
    app.run(debug=True, port=5000)