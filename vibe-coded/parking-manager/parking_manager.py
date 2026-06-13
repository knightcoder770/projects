# ============================================================
#   PARKING SLOT MANAGER — CORE LOGIC (Part 1)
#   This file is the "brain" of the app.
#   No web, no UI — just pure Python logic.
# ============================================================

from datetime import datetime  # To track entry/exit times


# ============================================================
# THE MAIN CLASS — Think of a class as a blueprint.
# ParkingManager is the blueprint for our parking lot.
# ============================================================

class ParkingManager:    

    def __init__(self):
        """
        __init__ runs automatically when you create a ParkingManager object.
        It sets up empty/default values — like setting up before opening the lot.
        """

        # --- MANAGER SETUP (filled during setup phase) ---
        self.total_slots = 0              # How many slots in the lot
        self.priority_slots = []          # List of priority slot numbers e.g. [1, 2, 3]
        self.fields_to_collect = []       # e.g. ["name", "contact"] — chosen by manager
        self.rate_per_5min = 0.0          # Normal parking cost every 5 mins
        self.fine_per_10min = 0.0         # Fine for every 10 mins overtime

        self.is_setup_done = False        # Flag: has manager completed setup?

        # --- PARKING DATA ---
        # Dictionary: { slot_no (int) : parker_details (dict) or None }
        # None means the slot is empty/free
        # Example: { 1: None, 2: {"name": "Raj", ...}, 3: None }
        self.slots = {}


    # ============================================================
    # SETUP — Manager fills in all configuration
    # ============================================================

    def setup(self, total_slots, priority_slots, fields_to_collect, rate_per_5min, fine_per_10min):
        """
        Called once by the manager to configure the parking lot.

        Parameters:
        - total_slots       : int   → total number of parking slots
        - priority_slots    : list  → slot numbers that are priority e.g. [1, 2]
        - fields_to_collect : list  → which parker details to collect e.g. ["name", "contact"]
        - rate_per_5min     : float → parking charge per 5 minutes
        - fine_per_10min    : float → fine charge per 10 minutes overtime
        """

        self.total_slots = total_slots
        self.priority_slots = priority_slots
        self.fields_to_collect = fields_to_collect
        self.rate_per_5min = rate_per_5min
        self.fine_per_10min = fine_per_10min

        # Create the slots dictionary
        # All slots start as None (empty/free)
        # range(1, total_slots + 1) gives [1, 2, 3, ... total_slots]
        self.slots = {slot_no: None for slot_no in range(1, total_slots + 1)}

        self.is_setup_done = True

        return {"success": True, "message": f"Parking lot set up with {total_slots} slots!"}


    # ============================================================
    # ASSIGN SLOT — When a new parker arrives
    # ============================================================

    def assign_slot(self, parker_details, duration_minutes):
        """
        Assigns the best available slot to a new parker.
        Priority slots are given first.

        Parameters:
        - parker_details   : dict  → e.g. {"name": "Raj", "contact": "9876543210"}
        - duration_minutes : int   → how long they plan to park (in minutes)

        Returns a dict with success status and assigned slot number.
        """

        if not self.is_setup_done:
            return {"success": False, "message": "Setup not done yet!"}

        # --- STEP 1: Find the best available slot ---
        # First check priority slots, then normal slots
        assigned_slot = None

        # Check priority slots first (important slots near exit etc.)
        for slot_no in self.priority_slots:
            if self.slots[slot_no] is None:  # None means empty
                assigned_slot = slot_no
                break  # Stop as soon as we find one free priority slot

        # If no priority slot is free, check all other slots
        if assigned_slot is None:
            for slot_no in self.slots:
                if slot_no not in self.priority_slots and self.slots[slot_no] is None:
                    assigned_slot = slot_no
                    break

        # If still None, the lot is full
        if assigned_slot is None:
            return {"success": False, "message": "Parking lot is full!"}

        # --- STEP 2: Record entry time and store parker data ---
        entry_time = datetime.now()  # Current time when they enter

        # Store all parker details + extra tracking info
        self.slots[assigned_slot] = {
            **parker_details,                        # Unpack parker details (name, age etc.)
            "duration_minutes": duration_minutes,    # How long they booked
            "entry_time": entry_time,                # When they actually entered
            "payment_status": "unpaid"               # Default payment status
        }

        return {
            "success": True,
            "message": f"Slot {assigned_slot} assigned!",
            "slot_no": assigned_slot,
            "entry_time": entry_time.strftime("%H:%M:%S")  # Human readable time
        }


    # ============================================================
    # DASHBOARD — View all slots at once
    # ============================================================

    def get_dashboard(self):
        """
        Returns the status of ALL slots.
        Used to display the dashboard to the manager.
        """

        if not self.is_setup_done:
            return {"success": False, "message": "Setup not done yet!"}

        dashboard = []

        for slot_no, parker in self.slots.items():

            if parker is None:
                # Slot is free
                dashboard.append({
                    "slot_no": slot_no,
                    "status": "free",
                    "is_priority": slot_no in self.priority_slots,
                    "parker": None
                })
            else:
                # Slot is occupied — calculate time info
                time_info = self._calculate_time(slot_no)

                dashboard.append({
                    "slot_no": slot_no,
                    "status": "occupied",
                    "is_priority": slot_no in self.priority_slots,
                    "parker": parker,
                    "time_info": time_info
                })

        return {"success": True, "dashboard": dashboard}


    # ============================================================
    # SEARCH — Find parker by slot number or name
    # ============================================================

    def search(self, query):
        """
        Search for a parker by slot number or name.

        Parameters:
        - query : str or int → slot number (e.g. 3) or name (e.g. "Raj")
        """

        results = []

        for slot_no, parker in self.slots.items():
            if parker is None:
                continue  # Skip empty slots

            # Check if query matches slot number
            if str(query) == str(slot_no):
                results.append({"slot_no": slot_no, "parker": parker})

            # Check if query matches name (case insensitive)
            elif "name" in parker and query.lower() in parker["name"].lower():
                results.append({"slot_no": slot_no, "parker": parker})

        if results:
            return {"success": True, "results": results}
        else:
            return {"success": False, "message": "No parker found!"}


    # ============================================================
    # CHECKOUT — Parker is leaving
    # ============================================================

    def checkout(self, slot_no):
        """
        Handles checkout for a given slot.
        Calculates total bill + fine (if overtime).
        Does NOT free the slot yet — manager confirms payment first.

        Parameters:
        - slot_no : int → which slot is checking out
        """

        if slot_no not in self.slots:
            return {"success": False, "message": "Invalid slot number!"}

        if self.slots[slot_no] is None:
            return {"success": False, "message": "Slot is already empty!"}

        # Calculate bill and fine
        time_info = self._calculate_time(slot_no)

        return {
            "success": True,
            "slot_no": slot_no,
            "parker": self.slots[slot_no],
            "time_info": time_info
        }


    # ============================================================
    # FREE SLOT — After checkout is confirmed
    # ============================================================

    def free_slot(self, slot_no, payment_status):
        """
        Frees a slot after the car leaves.
        Also records final payment status.

        Parameters:
        - slot_no        : int → which slot to free
        - payment_status : str → "paid" or "unpaid"
        """

        if slot_no not in self.slots or self.slots[slot_no] is None:
            return {"success": False, "message": "Invalid or already empty slot!"}

        # Update payment status before freeing
        self.slots[slot_no]["payment_status"] = payment_status

        # Free the slot (set to None)
        self.slots[slot_no] = None

        return {"success": True, "message": f"Slot {slot_no} is now free!"}


    # ============================================================
    # UPDATE PAYMENT — Mark payment status later
    # ============================================================

    def update_payment(self, slot_no, payment_status):
        """
        Update the payment status of an occupied slot.

        Parameters:
        - slot_no        : int → which slot
        - payment_status : str → "paid" or "unpaid"
        """

        if slot_no not in self.slots or self.slots[slot_no] is None:
            return {"success": False, "message": "Slot is empty or invalid!"}

        self.slots[slot_no]["payment_status"] = payment_status

        return {"success": True, "message": f"Payment status updated to '{payment_status}'!"}


    # ============================================================
    # PRIVATE HELPER — Calculate time, bill, fine
    # (Private means it's used internally, not called from outside)
    # ============================================================

    def _calculate_time(self, slot_no):
        """
        Calculates how long a car has been parked,
        the parking bill, and any overtime fine.

        The underscore _ at the start means it's a private/internal method.
        """

        parker = self.slots[slot_no]

        entry_time = parker["entry_time"]
        duration_booked = parker["duration_minutes"]  # What they paid for
        now = datetime.now()

        # entry_time might be a string if it was already converted
        # Convert it back to datetime so we can do time math
        if not hasattr(entry_time, "strftime"):
            from datetime import datetime as dt
            entry_time = dt.strptime(str(entry_time), "%H:%M:%S").replace(
                year=now.year, month=now.month, day=now.day
            )

        # Total minutes parked so far
        elapsed_minutes = (now - entry_time).total_seconds() / 60

        # Parking bill = (elapsed time / 5) × rate per 5 mins
        # We use max(elapsed, 1) so minimum charge is 1 unit
        parking_bill = (elapsed_minutes / 5) * self.rate_per_5min

        # Overtime = how many minutes they went over their booked time
        overtime_minutes = max(0, elapsed_minutes - duration_booked)

        # Fine = (overtime / 10) × fine per 10 mins
        fine = (overtime_minutes / 10) * self.fine_per_10min

        # Is the car overtime?
        is_overtime = overtime_minutes > 0

        return {
            "elapsed_minutes": round(elapsed_minutes, 1),
            "duration_booked": duration_booked,
            "overtime_minutes": round(overtime_minutes, 1),
            "parking_bill": round(parking_bill, 2),
            "fine": round(fine, 2),
            "total_amount": round(parking_bill + fine, 2),
            "is_overtime": is_overtime,
            "entry_time": entry_time.strftime("%H:%M:%S") if hasattr(entry_time, "strftime") else str(entry_time)
        }