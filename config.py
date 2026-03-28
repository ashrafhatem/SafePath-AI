import numpy as np
import time
from datetime import datetime

# ================= Twilio Configuration =================
TWILIO_SID = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # ضع SID الصحيح
TWILIO_AUTH = "your_real_auth_token"              # ضع Auth Token الصحيح
TWILIO_PHONE = "+12345678901"                     # رقم Twilio مسجل لديك

SUPERVISOR_NUMBERS = ["+97059XXXXXXX", "+97056XXXXXXX"]

CELL_SIZE = 40

grid_numeric = np.array([
    [1,1,1,3,1,3,1,3,1,3,1,3,1,3,1,1,1,1,1],
    [1,1,1,0,2,0,2,0,2,0,2,0,2,0,2,0,2,1,1],
    [1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1],
    [1,1,1,0,2,0,2,0,2,0,2,0,2,0,2,0,2,1,1],
    [1,1,2,0,2,0,2,0,2,0,2,0,2,0,2,0,2,1,1],
    [1,1,2,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1],
    [1,1,2,0,2,0,2,0,2,0,2,0,2,0,2,0,2,1,1],
    [1,1,2,0,2,0,2,0,2,0,2,0,2,0,2,0,2,1,1],
    [1,1,2,0,2,0,2,0,2,0,2,0,2,0,2,0,2,1,1],
    [1,1,2,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1],
    [1,1,1,0,2,0,2,0,2,0,2,0,2,0,2,0,1,1,1],
    [1,1,1,3,1,3,1,1,1,3,1,3,1,3,1,1,1,1,1]
])

# ========================= الممرات الثابتة =========================
corridors = {
    0: {"name": "Corridor A", "type":"vertical", "cells":[(1,3),(2,3),(3,3),(4,3),(5,3),(6,3),(7,3),(8,3),(9,3),(10,3)]},
    4: {"name": "Corridor B", "type":"vertical", "cells":[(1,5),(2,5),(3,5),(4,5),(5,5),(6,5),(7,5),(8,5),(9,5),(10,5)]},
    8: {"name": "Corridor C", "type":"vertical", "cells":[(1,7),(2,7),(3,7),(4,7),(5,7),(6,7),(7,7),(8,7),(9,7),(10,7)]},
    12: {"name": "Corridor D", "type":"vertical", "cells":[(1,9),(2,9),(3,9),(4,9),(5,9),(6,9),(7,9),(8,9),(9,9),(10,9)]},
    16: {"name": "Corridor E", "type":"vertical", "cells":[(1,11),(2,11),(3,11),(4,11),(5,11),(6,11),(7,11),(8,11),(9,11),(10,11)]},
    20: {"name": "Corridor F", "type":"vertical", "cells":[(1,13),(2,13),(3,13),(4,13),(5,13),(6,13),(7,13),(8,13),(9,13),(10,13)]},
    24: {"name": "Corridor G", "type":"vertical", "cells":[(1,15),(2,15),(3,15),(4,15),(5,15),(6,15),(7,15),(8,15),(9,15),(10,15)]},
}

# ========================= إنشاء corridor_map =========================
rows, cols = grid_numeric.shape
corridor_map = [[[] for _ in range(cols)] for _ in range(rows)]
for cid, info in corridors.items():
    for r,c in info["cells"]:
        corridor_map[r][c].append(cid)

# ========================= التسميات =========================
shop_labels = {
    (1,4): "Family primeurs",
    (1,6): "Patrick et Martine",
    (1,8): "La mare aux volailles |Greengrocer",
    (1,10): "Provibio",
    (1,12): "Greengrocer",
    (1,14): "Au veau d'or",
    (1,16): "Toilets",
    (3,4): "Le bidule",
    (3,6): "Traiteur antillais",
    (3,8): "Chastel",
    (3,10): "Anseur Fleur",
    (3,12): "Charcuterie Rabain",
    (3,14): "Greengrocer",
    (3,16): "Triperie A et L",
    (4,2): "Traiteur italien",
    (4,4): "Les 7 légumes",
    (4,6): "Greengrocer",
    (4,8): "Tonton Primeur |Le Borek",
    (4,10): "Seafood",
    (4,12): "Cordea",
    (4,14): "Navire des gourmands |Traiteur marocain",
    (4,16): "Triperie A et L",
    (6,4): "Poissonnerie Pointier",
    (6,6): "Philippe et Valérie",
    (6,8): "Sarthoise",
    (6,10): "La picholine",
    (6,12): "Remy Borel",
    (6,14): "Greengrocer",
    (6,16): "Chez Maria",
    (7,4): "Greengrocer",
    (7,6): "Aux délices de Montrouge",
    (7,8): "Sarthoise",
    (7,10): "Thaï Noy",
    (7,12): "Remy Borel",
    (7,14): "Lenoble",
    (8,4): "Traiteur libanais |Au petit primeur",
    (8,6): "Caterer",
    (8,8): "Verdot",
    (8,10): "Au bon accueil",
    (8,12): "Traiteur antillais|La sarladaise",
    (8,14): "Aux 4 saisons",
    (8,16): "Aux 4 saisons",
    (10,4): "Greengrocer",
    (10,6): "Aux Délices Du Marché | Traiteur asiatique",
    (10,8): "Greengrocer",
    (10,10): "Toyer",
    (10,12): "Neri Flore",
    (10,14): "Les fromages d'Alex"
}

exit_labels = {
    (0,3): "Exit 1",
    (0,5): "Exit 2",
    (0,7): "Exit 3",
    (0,9): "Exit 4",
    (0,11): "Exit 5",
    (0,13): "Exit 6",
    (11,3): "Exit 7",
    (11,5): "Exit 8",
    (11,9): "Exit 9",
    (11,11): "Exit 10",
    (11,13): "Exit 11",
}

columns_order = [
 'Temperature_C_','Humidity_','TVOC_ppb_','eCO2_ppm_',
 'Raw_H2','Raw_Ethanol','Pressure_hPa_',
 'PM1_0','PM2_5','NC0_5','NC1_0','NC2_5'
]

# ========================= Sensor Reading Templates =========================
noFire = [[20.1, 49.0, 50, 10, 100, 200, 940.2, 5, 8, 200, 200, 50]]
fire   = [[55.0, 22.0, 650, 1400, 17000, 26000, 930.5, 120, 200, 20000, 9000, 5000]]
sms    = [[22.0, 10.0, 11, 1400, 10, 20, 930.5, 120, 12, 12, 21, 10]]

# ========================= Fire Simulator =========================
class FireSimulator:
    """
    Time-based fire simulation.

    Each "fire event" is a dict with:
        start_time  : float  – simulation clock second when fire starts
        end_time    : float  – simulation clock second when fire ends
        cells       : dict   – {(row, col): sensor_readings}  cells affected by the event

    interval_sec : how many real seconds between each simulated tick
                   (used by get_current_sim_time to map wall-clock → sim-clock)
    """

    def __init__(self, interval_sec: float = 5.0):
        self.interval_sec  = interval_sec   # real seconds per simulated second
        self._start_wall   = time.time()    # wall-clock moment the sim was created
        self.events: list  = []             # list of fire-event dicts
        self._base_data    = dict.fromkeys(shop_labels, noFire)  # default: all safe
        self.running       = False
        self._last_time    = 0

    # ------------------------------------------------------------------
    def start_simulation(self):
        """Reset the wall clock so the simulation restarts from time 0."""
        self._start_wall = time.time()
        self.running = True
        self._last_time = 0

    def stop_simulation(self):
        """Manually stop the simulation timer without clearing events."""
        self.running = False

    def clear_events(self):
        """Clear all registered fire events."""
        self.events = []
        self.running = False
        self._last_time = 0
        global fire_cells
        fire_cells.clear()

    # ------------------------------------------------------------------
    def add_event(self, start_time: float, end_time: float, cells: dict):
        """
        Register a fire event.
        """
        self.events.append({
            "start_time": float(start_time),
            "end_time":   float(end_time),
            "cells":      cells,
        })

    # ------------------------------------------------------------------
    def get_current_sim_time(self) -> float:
        """Return simulated time (seconds) based on wall-clock elapsed, stopped at the last fire's end."""
        if not self.running:
            return self._last_time

        elapsed_real = time.time() - self._start_wall
        sim_t = elapsed_real * self.interval_sec
        
        # If there are events, don't let the clock run past the very last fire's end_time
        if self.events:
            max_end = max(e["end_time"] for e in self.events)
            if sim_t >= max_end:
                self.running = False
                self._last_time = max_end
                return max_end
                
        self._last_time = sim_t
        return sim_t

    # ------------------------------------------------------------------
    def get_sensor_data(self) -> dict:
        """
        Return a sensor-reading dict for every shop, reflecting which
        fire events are currently active based on the simulated time.
        """
        sim_t = self.get_current_sim_time()

        # Start from default (all safe)
        current = dict(self._base_data)  # shallow copy

        for event in self.events:
            if event["start_time"] <= sim_t < event["end_time"]:
                if sim_t < event["start_time"] + 10:
                    for r, c in event["cells"].keys():
                        current[(r,c)] = sms
                else:
                    current.update(event["cells"])

        return current

    # ------------------------------------------------------------------
    def status(self) -> str:
        """Human-readable snapshot of the current simulation state."""
        sim_t = self.get_current_sim_time()
        active = [e for e in self.events
                  if e["start_time"] <= sim_t < e["end_time"]]
        ts = datetime.now().strftime("%H:%M:%S")
        if active:
            affected = []
            for e in active:
                affected.extend(e["cells"].keys())
            return (f"[{ts}] SimTime={sim_t:.1f}s  "
                    f"FIRE ACTIVE at cells: {affected}")
        return (f"[{ts}] SimTime={sim_t:.1f}s  All clear")


# ========================= Configure the Simulation =========================
# interval_sec: every 1 real second = interval_sec simulated seconds
# e.g. interval_sec=1  → real-time simulation
#      interval_sec=10 → 10× speed
fire_sim = FireSimulator(interval_sec=1)

# --- Define fire events: (start_sim_sec, end_sim_sec, {cell: sensor_data}) ---
# (Simulation starts fully clear; adding fires will be driven by the user from the UI)

# Fire event 1: shops (1,4) and (1,6) catch fire at t=10s, extinguished at t=40s
# fire_sim.add_event(
#     start_time = 10,
#     end_time   = 40,
#     cells      = {(4, 4): fire,(8, 4): fire,(1, 6): fire}
# )

# Add more events below as needed, e.g.:
# fire_sim.add_event(start_time=50, end_time=80, cells={(3,8): fire})

# Convenience alias so ml_utils.py can still call `updated_dict` as before
# but now it is dynamically evaluated each time get_sensor_data() is called.
# ml_utils.py should use fire_sim.get_sensor_data() instead.
updated_dict = fire_sim.get_sensor_data()  # static snapshot at import time (for backward compat)

fire_cells = set()  # لتخزين مواقع الحريق
