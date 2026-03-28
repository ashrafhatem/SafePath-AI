from collections import deque
import heapq
import numpy as np
import joblib
import pandas as pd

def compute_danger_grid(grid, fire_cells, current_time, corridor_aggregated=None, corridor_map=None, corridors=None):
    """
    1️⃣ Integrate the model output into the danger grid
    2️⃣ Normalize and scale the risk values
    6️⃣ Handle extremely dangerous cells
    """
    rows, cols = grid.shape
    danger = np.zeros((rows, cols), dtype=float)

    if not fire_cells:
        return danger

    from ml_utils import get_fire_risk_model
    model = get_fire_risk_model()
    if not model:
        print("GradientBoosting model is not loaded yet")

    raw_risks = np.zeros((rows, cols), dtype=float)
    max_risk = 0.0001  # Prevent division by zero

    # Get raw predictions for walkable cells
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] not in [0, 3]:
                continue
                
            if model:
                try:
                    X = [{'fire_row': fr, 'fire_col': fc, 'time': current_time, 'cell_row': r, 'cell_col': c} for fr, fc in fire_cells]
                    predictions = model.predict(pd.DataFrame(X))
                    val = float(predictions.sum())
                    raw_risks[r][c] = val
                    if val > max_risk:
                        max_risk = val
                except:
                    pass

    # Normalize, Scale, and heavily Penalize
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] not in [0, 3]:
                continue
                
            # Normalize between 0 and 1
            norm_val = raw_risks[r][c] / max_risk
            
            # Squaring to amplify high risk and reduce low risk
            scaled_risk = norm_val ** 2
            
            # Ensure cells near the fire are heavily penalized ("higher higher")
            # We SUM the decay of all fires so passing between multiple fires is mathematically impossible
            proximity_risk = 0.0
            if fire_cells:
                for fr, fc in fire_cells:
                    d = abs(r - fr) + abs(c - fc)
                    if d > 0:
                        proximity_risk += 12.0 / (d ** 2)

            # Combine model's temporal risk with the spatial proximity penalty
            final_risk = scaled_risk + proximity_risk
                
            danger[r][c] = round(final_risk, 2)

    # Integrate congestion costs dynamically into the danger grid
    if corridor_aggregated and corridor_map and corridors:
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] not in [0, 3]:
                    continue
                
                c_ids = corridor_map[r][c]
                if not c_ids:
                    continue
                
                max_congestion_cost = 0.0
                for cid in c_ids:
                    if cid in corridors:
                        cName = corridors[cid]["name"]
                        if cName in corridor_aggregated:
                            people = corridor_aggregated[cName].get("total_people", 0)
                            
                            # Normalize counts relative to sensible capacity (e.g. 50 per corridor)
                            congestion_cost = people / 50.0
                            
                            # Extreme congestion threshold -> corridor becomes practically blocked
                            if people >= 50:
                                congestion_cost = 5000.0
                                
                            if congestion_cost > max_congestion_cost:
                                max_congestion_cost = congestion_cost
                                
                danger[r][c] += max_congestion_cost

    # 6️⃣ Handle extremely dangerous cells
    for (fr, fc) in fire_cells:
        if 0 <= fr < rows and 0 <= fc < cols:
            danger[fr][fc] = 9999.0  # Blocked / extremely high cost

    return danger

def is_walkable(r, c, grid):
    rows, cols = grid.shape
    if r < 0 or r >= rows or c < 0 or c >= cols:
        return False
    return grid[r][c] in [0, 3]

def a_star_all_paths(start, grid, danger):
    """
    3️⃣ A* Algorithm with Time Awareness
    Modified cost: f = g + h * (1 + risk)
    """
    rows, cols = grid.shape
    directions = [(-1,0), (1,0), (0,-1), (0,1)]
    
    exits = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == 3]

    def heuristic(r, c):
        if not exits: return 0.0
        return min(abs(r - er) + abs(c - ec) for er, ec in exits)

    pq = []
    # priority queue based on (f_cost, g_cost, (r, c))
    heapq.heappush(pq, (heuristic(start[0], start[1]), 0.0, start))
    
    cost_so_far: dict = {start: 0.0}
    parents: dict = {start: None}

    while pq:
        f_cost, current_cost, (r, c) = heapq.heappop(pq)
        
        # Optimization: if we already found a much better path, skip
        if current_cost > cost_so_far.get((r, c), float('inf')):
            continue
            
        for dr, dc in directions:
            nr, nc = r+dr, c+dc
            if not is_walkable(nr, nc, grid):
                continue
                
            cell_risk = danger[nr][nc]
            if cell_risk >= 5000.0: # Extremely dangerous blocked threshold
                continue

            # Reduce over-penalization: let final path evaluation handle strict safety
            movement_cost = 1.0 + (cell_risk ** 2) * 10.0
            
            new_cost = current_cost + movement_cost
            
            if new_cost < cost_so_far.get((nr, nc), float('inf')):
                cost_so_far[(nr, nc)] = new_cost
                parents[(nr, nc)] = (r, c)
                
                # A* Heuristic modified with risk awareness
                h = heuristic(nr, nc)
                f_cost_new = new_cost + h * (1.0 + cell_risk)
                
                heapq.heappush(pq, (f_cost_new, new_cost, (nr, nc)))

    return parents, cost_so_far, exits

def find_nearest_walkable(start, grid):
    queue = deque([start])
    visited = {start}
    directions = [(-1,0), (1,0), (0,-1), (0,1)]

    while queue:
        r, c = queue.popleft()
        if is_walkable(r, c, grid):
            return (r, c)
        for dr, dc in directions:
            nr, nc = r+dr, c+dc
            if (nr, nc) not in visited:
                if 0 <= nr < grid.shape[0] and 0 <= nc < grid.shape[1]:
                    visited.add((nr, nc))
                    queue.append((nr, nc))
    return None

def get_all_exit_paths(start, grid, danger):
    """Backtrack from all reached exits to construct the path."""
    parents, cost_so_far, exits = a_star_all_paths(start, grid, danger)
    all_paths = []
    
    for ex in exits:
        if ex in parents:
            path = []
            curr = ex
            while curr is not None:
                path.append(curr)
                if curr == start:
                    break
                curr = parents.get(curr)
                
            if curr == start:
                path.reverse()
                all_paths.append(path)
                
    return all_paths

def compute_path_risk(path, danger):
    if not path:
        return float('inf')
    
    risks = [danger[r][c] for r, c in path]
    max_r = max(risks)
    avg_r = sum(risks) / len(risks)
    
    # Hybrid Strategy: Avoid danger at all costs, then minimize distance
    return (max_r * 1000.0) + (avg_r * 100.0) + len(path)

def choose_safest_path(paths, danger):
    if not paths: 
        return []
    best_path = []
    best_cost = float("inf")
    for path in paths:
        cost = compute_path_risk(path, danger)
        if cost < best_cost:
            best_cost = cost
            best_path = path
    return best_path
