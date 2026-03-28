from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import os
# Import modules
from config import CELL_SIZE, grid_numeric, corridor_map, shop_labels, corridors, fire_cells, exit_labels
from database import init_db, authenticate_user, get_all_supervisors, get_supervisor_stats, add_supervisor, update_supervisor, delete_supervisor, add_report, update_report, get_all_reports, clear_reports, get_reports_by_date, log_sms_sent, get_notified_users_by_date
from sms_utils import init_twilio, send_warning_sms, send_custom_sms
from ml_utils import init_models, get_grid_predictions, get_results_dict
from pathfinding import compute_danger_grid, find_nearest_walkable, get_all_exit_paths, choose_safest_path

app = Flask(__name__)
app.secret_key = "super_secret_fredt_key"  # Required for sessions

# Initialize modules
init_db()
init_twilio()
init_models()

people_counts = {}
camera_data_store = {}
corridor_aggregated = {f"Corridor {c}": {"name": f"Corridor {c}", "fire_status": False, "total_people": 0} for c in "ABCDEFG"}
logged_fires = {}  # Store tracking data: { "cell": "state_hash" }
sent_sms_records = set()
manual_alerted_user_ids = set()
manual_congestion_events = []
last_processed_time = 0

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        user_id = authenticate_user(username, password)
        if user_id:
            session['user_id'] = user_id
            session['username'] = username
            return redirect(url_for('index'))
        else:
            flash("Invalid username or password", "error")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route("/")
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("index.html", shops=shop_labels)

@app.route("/admin")
def admin():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    supervisors_data = get_all_supervisors()
    total_admins, active_roles, pending_approvals = get_supervisor_stats()
        
    return render_template("admin.html", 
                           supervisors=supervisors_data,
                           total_admins=total_admins,
                           active_roles=active_roles,
                           pending_approvals=pending_approvals)

@app.route("/add_supervisor", methods=["POST"])
def add_supervisor_route():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    full_name = request.form.get("full_name")
    email = request.form.get("email")
    password = request.form.get("password") or "123456"
    role = request.form.get("role")
    status = request.form.get("status")
    phone = request.form.get("phone") or ""
    
    data = {
        'full_name': full_name,
        'email': email,
        'password': password,
        'role': role,
        'status': status,
        'phone': phone,
        'corridor': request.form.get("corridor") or "None",
        'joined_date': datetime.now().strftime("%b %d, %Y"),
        'last_active': "Just now"
    }
    
    success, msg = add_supervisor(data)
    if not success:
        flash(msg, "error")
        
    return redirect(url_for('admin'))

@app.route("/edit_supervisor/<int:id>", methods=["POST"])
def edit_supervisor_route(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    data = {
        'full_name': request.form.get("full_name"),
        'email': request.form.get("email"),
        'role': request.form.get("role"),
        'status': request.form.get("status"),
        'phone': request.form.get("phone") or "",
        'corridor': request.form.get("corridor") or "None"
    }
    
    success, msg = update_supervisor(id, data)
    if not success:
        flash(msg, "error")
        
    return redirect(url_for('admin'))

@app.route("/delete_supervisor/<int:id>", methods=["POST"])
def delete_supervisor_route(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    success, msg = delete_supervisor(id)
    if not success:
        flash(msg, "error")
    
    return redirect(url_for('admin'))

@app.route("/grid_status", methods=["GET"])
def grid_status():
    grid_results = get_grid_predictions()
    return jsonify(grid_results)

@app.route("/grid")
def grid_api():
    rows, cols = grid_numeric.shape
    nodes = []

    for r in range(rows):
        for c in range(cols):
            value = int(grid_numeric[r][c])
            label = shop_labels.get((r,c), "") if value in [2,3] else ""
            if value == 3:
                label = "Emergency Exit"
            nodes.append({
                "id": f"{r}-{c}",
                "row": r,
                "col": c,
                "x": c * CELL_SIZE + 10,
                "y": r * CELL_SIZE + 10,
                "value": value,
                "label": label,
                "corridor_id": corridor_map[r][c]
            })

    return jsonify({
        "nodes": nodes,
        "corridors": corridors
    })

def process_fire_data():
    global fire_cells, sent_sms_records, logged_fires, manual_alerted_user_ids

    # ── Guard: do nothing until the user presses Start ──
    from config import fire_sim as _fire_sim
    if not _fire_sim.running and _fire_sim._last_time == 0:
        fire_cells.clear()
        return "safe", [], [], {}, {}

    results_dict = get_results_dict()
    new_fire_cells = set()
    warning_cells = []
    
    supervisors = get_all_supervisors()

    def get_responsible_users(r, c):
        phones_set = set()
        user_ids_set = set()
        cell_corridors = []
        neighbors = [(r, c), (r-1, c), (r+1, c), (r, c-1), (r, c+1)]
        rows_count, cols_count = len(corridor_map), len(corridor_map[0])
        for nr, nc in neighbors:
            if 0 <= nr < rows_count and 0 <= nc < cols_count:
                for cid in corridor_map[nr][nc]:
                    if cid in corridors:
                        letter = corridors[cid]["name"].replace("Corridor ", "")
                        if letter not in cell_corridors:
                            cell_corridors.append(letter)
        
        for sup in supervisors:
            if sup['status'] == 'Active' and sup.get('phone') and sup.get('phone').strip():
                sc = sup.get('corridor', 'None')
                if sc == 'All':
                    phones_set.add(sup['phone'])
                    user_ids_set.add(sup['id'])
                elif sc in cell_corridors:
                    phones_set.add(sup['phone'])
                    user_ids_set.add(sup['id'])
        return list(phones_set), list(user_ids_set)

    for (r, c), probability in results_dict.items():
        if probability >= 0.70:
            new_fire_cells.add((r, c))
        elif 0.50 <= probability < 0.70:
            warning_cells.append((r, c))
            cell_key = f"{r}_{c}_alert_sent"
            if cell_key not in sent_sms_records:
                phones, u_ids = get_responsible_users(r, c)
                if phones:
                    location_name = shop_labels.get((r, c), f"Cell ({r},{c})")
                    send_warning_sms(location_name, probability, phones)
                    sent_sms_records.add(cell_key)
                    for uid in u_ids:
                        log_sms_sent(uid)

    fire_cells.clear()
    fire_cells.update(new_fire_cells)

    if not new_fire_cells and not warning_cells:
        manual_alerted_user_ids.clear()
        sent_sms_records.clear()
        logged_fires.clear()
        return "safe", [], [], {}, {}
        
    # Remove ended fires from logged_fires so future fires at the same spot create a new report
    active_fire_keys = {f"{fr}-{fc}" for fr, fc in fire_cells}
    for key in list(logged_fires.keys()):
        if key not in active_fire_keys:
            del logged_fires[key]

    live_corridors = get_live_corridors()
    from config import fire_sim
    current_sim_time = fire_sim.get_current_sim_time()
    
    # Hybrid Strategy: Combined Danger (Now + Future Prediction)
    danger_now = compute_danger_grid(grid_numeric, fire_cells, current_sim_time, live_corridors, corridor_map, corridors)
    danger_future = compute_danger_grid(grid_numeric, fire_cells, current_sim_time + 2.0, live_corridors, corridor_map, corridors)
    
    danger_grid = 0.7 * danger_now + 0.3 * danger_future
    
    all_fire_paths = {}

    for fr, fc in fire_cells:
        start = find_nearest_walkable((fr,fc), grid_numeric)
        if start is None:
            all_fire_paths[f"{fr}-{fc}"] = []
            continue
        all_paths = get_all_exit_paths(start, grid_numeric, danger_grid)
        safest = choose_safest_path(all_paths, danger_grid)
        # Convert tuples to lists so JSON serialization gives [[r,c], ...]
        all_fire_paths[f"{fr}-{fc}"] = [[r, c] for r, c in safest]
        
        exit_name = "None"
        corridor_str = "None"
        if safest:
            current_exit_tuple = safest[-1]
            exit_name = exit_labels.get(current_exit_tuple, f"Exit {current_exit_tuple}")
            corridor_names = set()
            for r, c in safest:
                for cid in corridor_map[r][c]:
                    if cid in corridors:
                        corridor_names.add(corridors[cid]["name"])
            corridor_str = ", ".join(sorted(list(corridor_names))) if corridor_names else "None"
            
        shop_name = shop_labels.get((fr, fc), f"Cell ({fr},{fc})")
        state_hash = f"{exit_name}|{corridor_str}"
        cell_key = f"{fr}-{fc}"
        existing = logged_fires.get(cell_key)

        if existing is None:
            # Calculate population metrics
            total_building_people = sum(d["total_people"] for d in live_corridors.values())
            
            # Estimate people near this specific shop by looking at matching corridors
            # (Finding the max people count among corridors this shop is in)
            shop_people = 0
            fr_int, fc_int = int(fr), int(fc)
            if fr_int < len(corridor_map) and fc_int < len(corridor_map[0]):
                for cid in corridor_map[fr_int][fc_int]:
                    if cid in corridors:
                        cName = corridors[cid]["name"]
                        if cName in live_corridors:
                            shop_people = max(shop_people, live_corridors[cName]["total_people"])

            report_id = add_report(shop_name, exit_name, corridor_str, total_building_people, shop_people)
            logged_fires[cell_key] = {'report_id': report_id, 'hash': state_hash}
            # Log which supervisors were notified for this fire cell
            _, u_ids = get_responsible_users(fr, fc)
            for uid in u_ids:
                log_sms_sent(uid)
        elif existing['hash'] != state_hash:
            # Path changed — update the SAME row in-place, no new entry
            update_report(existing['report_id'], exit_name, corridor_str)
            logged_fires[cell_key]['hash'] = state_hash

    danger_values = {}
    rows_d, cols_d = danger_grid.shape
    for r in range(rows_d):
        for c in range(cols_d):
            if danger_grid[r][c] > 0:
                danger_values[f"{r}-{c}"] = round(float(danger_grid[r][c]), 2)

    return "updated", list(new_fire_cells), warning_cells, all_fire_paths, danger_values

@app.route("/update_fire", methods=["GET"])
def update_fire():
    from config import fire_sim
    status, fires, warnings, paths, danger = process_fire_data()
    return jsonify({
        "status": status,
        "fires": [f"{r}-{c}" for r,c in fires],
        "warnings": [f"{r}-{c}" for r,c in warnings],
        "paths": paths,
        "danger_scores": danger,
        "sim_time": round(fire_sim.get_current_sim_time(), 1)
    })

@app.route("/update_camera_data", methods=["POST"])
def update_camera_data():
    global camera_data_store, corridor_aggregated
    data_json = request.json

    if not data_json:
        return jsonify({"status": "no data"}), 400

    camera_data_store = data_json

    # Reset aggregated totals
    for c in "ABCDEFG":
        corridor_aggregated[f"Corridor {c}"]["total_people"] = 0
        corridor_aggregated[f"Corridor {c}"]["fire_status"] = False
        
    for cam_id, cam_info in camera_data_store.items():
        corr = cam_info["corridor"]
        if corr in corridor_aggregated:
            corridor_aggregated[corr]["total_people"] += cam_info["people_count"]
            if cam_info["fire_status"]:
                corridor_aggregated[corr]["fire_status"] = True

    return jsonify({
        "status": "received",
        "data": corridor_aggregated
    })

def get_live_corridors():
    from config import fire_sim
    current_time = fire_sim.get_current_sim_time()
    
    live_data = {}
    for k, v in corridor_aggregated.items():
        live_data[k] = v.copy()
        
    for event in manual_congestion_events:
        if event["start"] <= current_time <= event["end"]:
            corr_key = str(event["corridor"])
            if corr_key in live_data:
                live_data[corr_key]["total_people"] = event["people"]
                
    return live_data

@app.route("/get_corridors_data", methods=["GET"])
def get_corridors_data():
    return jsonify({
        "status": "ok",
        "corridors": get_live_corridors()
    })

@app.route("/get_people", methods=["GET"])
def get_people():
    total = sum(d["total_people"] for d in get_live_corridors().values())
    return jsonify({
        "status": "ok",
        "total_people": total
    })

@app.route("/reports", methods=["GET"])
def reports():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    db_reports = get_all_reports()
    
    # Group reports by date
    from collections import OrderedDict
    grouped = OrderedDict()
    for r in db_reports:
        d = r['date']
        if d not in grouped:
            grouped[d] = {'date': d, 'fire_count': 0, 'fires': []}
        grouped[d]['fire_count'] += 1
        grouped[d]['fires'].append(r)
    
    # Convert to list sorted by date descending
    days = sorted(grouped.values(), key=lambda x: x['date'], reverse=True)
    return render_template("reports.html", days=days)

@app.route("/clear_reports", methods=["POST"])
def clear_reports_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    clear_reports()
    return jsonify({"success": True})

@app.route("/report_details/<date>")
def report_details(date):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    day_reports = get_reports_by_date(date)
    supervisors = get_all_supervisors()

    notified_uids = get_notified_users_by_date(date)

    notified = []
    seen_ids = set()
    for s in supervisors:
        if s['id'] in notified_uids and s['id'] not in seen_ids:
            notified.append(s)
            seen_ids.add(s['id'])

    return render_template("report_details.html",
                           date=date,
                           reports=day_reports,
                           notified=notified)

@app.route("/add_sim_fire", methods=["POST"])
def add_sim_fire():
    data = request.json
    row = int(data['row'])
    col = int(data['col'])
    start = float(data['start'])
    end = float(data['end'])
    from config import fire_sim, fire
    fire_sim.add_event(start, end, {(row, col): fire})
    return jsonify({"success": True})

@app.route("/add_sim_congestion", methods=["POST"])
def add_sim_congestion():
    global manual_congestion_events
    data = request.json
    corridor = str(data.get("corridor"))
    people = int(data.get("people", 0))
    start_t = float(data.get("start", 0))
    end_t = float(data.get("end", 9999))
    
    manual_congestion_events.append({
        "corridor": corridor,
        "people": people,
        "start": start_t,
        "end": end_t
    })
    return jsonify({"success": True})

@app.route("/clear_sim_congestion", methods=["POST"])
def clear_sim_congestion():
    global manual_congestion_events
    manual_congestion_events.clear()
    return jsonify({"success": True})

@app.route("/start_sim", methods=["POST"])
def start_sim():
    from config import fire_sim
    fire_sim.start_simulation()
    return jsonify({"success": True})

@app.route("/clear_sim", methods=["POST"])
def clear_sim():
    global sent_sms_records, manual_alerted_user_ids, logged_fires
    from config import fire_sim
    fire_sim.clear_events()
    sent_sms_records.clear()
    manual_alerted_user_ids.clear()
    logged_fires.clear()
    return jsonify({"success": True})

@app.route("/get_sim_events")
def get_sim_events():
    from config import fire_sim, shop_labels
    events_data = []
    for e in fire_sim.events:
        # Extract the first cell as the representant for the list
        cells_list = list(e['cells'].keys())
        if cells_list:
            r, c = cells_list[0]
            shop_name = shop_labels.get((r, c), f"Cell ({r},{c})")
            events_data.append({
                "shop_name": shop_name,
                "start": e['start_time'],
                "end": e['end_time']
            })
    return jsonify({"events": events_data})

@app.route("/send_sms", methods=["POST"])
def send_sms_route():
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
        
    phone = data.get("phone")
    message = data.get("message")
    user_id = data.get("user_id")
    
    if not phone:
        return jsonify({"success": False, "error": "No phone number provided"}), 400
        
    if user_id:
        try:
            global manual_alerted_user_ids
            manual_alerted_user_ids.add(int(user_id))
            log_sms_sent(int(user_id))
            print(f"[DEBUG] Manual SMS logged for User {user_id} in daily_sms.")
        except Exception as e:
            print(f"[ERROR] Failed to log manual SMS for user {user_id}: {e}")
        
    success = send_custom_sms(phone, message)
    return jsonify({"success": success})

@app.route("/admin/alerts_status")
def admin_alerts_status():
    global manual_alerted_user_ids, sent_sms_records

    # ── Guard: do nothing until the user presses Start ──
    from config import fire_sim as _fire_sim
    if not _fire_sim.running and _fire_sim._last_time == 0:
        return jsonify({"alerted_user_ids": []})

    # Process fire logic (including report generation) every time status is polled from Dashboard
    status, fires, warnings, paths, danger = process_fire_data()
    
    results_dict = get_results_dict()
    
    # If everything is safe, clear all alert history
    if status == "safe":
        manual_alerted_user_ids.clear()
        sent_sms_records.clear()
        return jsonify({"alerted_user_ids": []})

    alerted = set(manual_alerted_user_ids) # Include manually alerted first
    supervisors = get_all_supervisors()
    
    for (r, c), probability in results_dict.items():
        if probability >= 0.50:
            cell_corridors = []
            neighbors = [(r, c), (r-1, c), (r+1, c), (r, c-1), (r, c+1)]
            rows_count, cols_count = len(corridor_map), len(corridor_map[0])
            
            for nr, nc in neighbors:
                if 0 <= nr < rows_count and 0 <= nc < cols_count:
                    for cid in corridor_map[nr][nc]:
                        if cid in corridors:
                            letter = corridors[cid]["name"].replace("Corridor ", "")
                            if letter not in cell_corridors:
                                cell_corridors.append(letter)
            
            for sup in supervisors:
                if sup['status'] == 'Active' and sup.get('phone') and sup.get('phone').strip():
                    sc = sup.get('corridor', 'None')
                    if sc == 'All' or sc in cell_corridors:
                        alerted.add(sup['id'])
                            
    if alerted:
        print(f"[DEBUG] Dashboard Polling: Alerted User IDs = {list(alerted)}")
                            
    return jsonify({"alerted_user_ids": list(alerted)})

# report_details_page (old int-id route) removed — now using date-based route above

@app.route("/debug/sms_logs")
def debug_sms_logs():
    """Debug endpoint: shows everything stored in daily_sms table."""
    import sqlite3 as _sqlite3
    try:
        conn = _sqlite3.connect('users.db')
        conn.row_factory = _sqlite3.Row
        c = conn.cursor()
        # Check tables
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]
        rows = []
        if 'daily_sms' in tables:
            c.execute('SELECT * FROM daily_sms ORDER BY id DESC')
            rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify({"tables": tables, "daily_sms_rows": rows, "count": len(rows)})
    except Exception as e:
        return jsonify({"error": str(e)})
        
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
