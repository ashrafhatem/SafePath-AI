let selectedCell = null;
let clickCounts = {};
let CELL_SIZE = 40;
let nodes = [];
let fireCells = new Set();
let dangerGrid = [];  // خطورة كل خلية
let selectedCellCorridor = undefined; // ← لتخزين الممر المحدد حالياً
const newFirePaths = {};
// تعبئة
firePaths = newFirePaths;
let selectedFireKey = null; // الحريق المختار حالياً
// ===== رسم الشبكة =====
let currentPath = [];
// تحديث العدد الكلي للأشخاص كل ثانية
// =========================
let warningCells = new Set();

let globalCorridors = {}; // Store /grid corridors setup
let corridorStatus = {}; // Store /get_corridors_data status

function pollCorridorsData() {
    fetch("/get_corridors_data")
        .then(res => res.json())
        .then(data => {
            if (data.status === "ok" && data.corridors) {
                corridorStatus = data.corridors;
                updateMapColors(); // Trigger visual update
                updateSelectedCorridorInfo(); // Continously update panel
            }
        })
        .catch(err => console.error("Error fetching corridors data:", err));
}

function getBaseColor(node, originalKey) {
    if (fireCells.has(originalKey)) return "#f70000ff";
    if (warningCells.has(originalKey)) return "#ff7b00ff";

    let color = node.value === 2 ? "#eeff00ff" :
                node.value === 0 ? "#879d86" :
                node.value === 1 ? "#2a3229" :
                node.value === 3 ? "#5d85c3" : "#879d86";

    // 🚦 Color Crowded Corridors
    if (node.value === 0 && node.corridor_id && node.corridor_id.length > 0) {
        let maxPeople = 0;
        node.corridor_id.forEach(cid => {
            const cName = globalCorridors[cid]?.name;
            if (cName && corridorStatus[cName] && typeof corridorStatus[cName].total_people === "number") {
                maxPeople = Math.max(maxPeople, corridorStatus[cName].total_people);
            }
        });
        
        if (maxPeople >= 45) {
            return "#7b241c"; // Extremely Crowded / Almost blocked
        } else if (maxPeople >= 20) {
            return "#9b59b6"; // Congested Purple
        } 
    }

    return color;
}

function updateMapColors() {
    nodes.forEach(n => {
        const key = `${n.row}-${n.col}`;
        // Skip path
        if (currentPath && currentPath.some(([r,c]) => r == n.row && c == n.col)) return;

        let baseColor = getBaseColor(n, key);
        d3.select(`#rect-${key}`).attr("fill", baseColor);
    });
}

function updateSelectedCorridorInfo() {
    if (selectedCellCorridor !== undefined && selectedCellCorridor.length > 0) {
        const corridorNames = selectedCellCorridor.map(cid => globalCorridors[cid]?.name || "Unknown").join(", ");
        
        let peopleSum = 0;
        let statuses = [];
        selectedCellCorridor.forEach(cid => {
            const cInfo = globalCorridors[cid];
            if (cInfo && cInfo.name) {
                const cName = cInfo.name;
                if (corridorStatus[cName]) {
                    peopleSum += corridorStatus[cName].total_people || 0;
                    statuses.push(corridorStatus[cName].fire_status ? "Fire Detected" : "Safe");
                }
            }
        });
        
        let combinedStatus = statuses.includes("Fire Detected") ? "<span style='color:#ff4d4d; font-weight:bold;'>Fire Detected</span>" : (statuses.length ? "<span style='color:#4caf50; font-weight:bold;'>Safe</span>" : "Unknown");

        const cellInfo = document.getElementById("cellInfo");
        if (cellInfo) {
            cellInfo.innerHTML = `
                <div style="margin-bottom:10px;"><b>Corridor ${corridorNames}</b></div>
                <div style="color:var(--text-muted); margin-bottom:5px;">Status: ${combinedStatus}</div>
                <div style="color:var(--text-muted);">People Count: <b style="color:#ffffff;">${peopleSum}</b></div>
            `;
        }
    }
}

function updateTotalPeople() {
    fetch("/get_people")
        .then(res => res.json())
        .then(data => {
            if (data && data.total_people !== undefined) {
                const tpEl = document.getElementById("totalPeople");
                if (tpEl) tpEl.innerText = data.total_people;
                const ftpEl = document.getElementById("footerTotalPeople");
                if (ftpEl) ftpEl.innerText = data.total_people;
            }
        })
        .catch(err => console.error("Error fetching total people:", err));
}




// استدعاء كل ثانية
setInterval(updateTotalPeople, 1000);
setInterval(pollFireSystem, 1000);
setInterval(pollCorridorsData, 1000);

function addFireToPanel(key, shopName) {

    const fireList = document.getElementById("fireList");

    if (fireList.innerText === "No active fires")
        fireList.innerHTML = "";

    const item = document.createElement("div");
    item.className = "fireItem";
    item.innerText = "🔥 " + shopName;
    item.style.cursor = "pointer";
    item.style.padding = "5px";

    item.onclick = () => {
        selectedFireKey = key;

        // رسم المسار الخاص بالحريق المختار
        colorSafestPath(firePaths[key]);
    };

    item.id = "fire-" + key;
    fireList.appendChild(item);
}
function colorSafestPath(path) {

    // 🧹 Restore old path cells to their correct base color
    if (currentPath && currentPath.length > 0) {
        currentPath.forEach(([r, c]) => {
            const key = `${r}-${c}`;
            const node = nodes.find(n => n.row == r && n.col == c);
            let restoreColor = getBaseColor(node, key);
            d3.select(`#rect-${r}-${c}`).attr("fill", restoreColor);
        });
    }

    // ⭐ Copy the new path (important!)
    currentPath = path ? [...path] : [];

    // 🎨 Paint new path green (skip fire cells)
    currentPath.forEach(([r, c]) => {
        const key = `${r}-${c}`;
        if (!fireCells.has(key)) {
            d3.select(`#rect-${r}-${c}`)
                .attr("fill", "#00ff22ff");
        }
    });
}
function removeFireFromPanel(key) {
    const item = document.getElementById("fire-" + key);
    if (item) item.remove();

    if (Object.keys(firePaths).length === 0) {
        document.getElementById("fireList").innerText =
            "No active fires";
    }
}

function removeFirePath(fireKey) {
    const path = firePaths[fireKey];
    if (!path) return;
    path.forEach(([r,c]) => {
        const node = nodes.find(n => n.row == r && n.col == c);
        if (!node) return;
        let baseColor = getBaseColor(node, `${r}-${c}`);
        d3.select(`#rect-${r}-${c}`).attr("fill", baseColor);
    });
    delete firePaths[fireKey];
}

function pollFireSystem() {

    fetch("/update_fire")
        .then(res => res.json())
        .then(data => {

            console.log("=== POLL FIRE DATA ===", JSON.stringify(data).substring(0, 500));
            console.log("status:", data.status);
            console.log("fires:", data.fires);
            console.log("paths keys:", Object.keys(data.paths || {}));
            for (const k of Object.keys(data.paths || {})) {
                console.log(`path[${k}]:`, JSON.stringify(data.paths[k]).substring(0, 200));
            }

            let previousFires = new Set(Object.keys(firePaths));
            const currentFires = new Set(data.fires || []);

            previousFires.forEach(key => {
                if (!currentFires.has(key)) {
                    // This fire has ended
                    removeFirePath(key);

                    if (selectedFireKey === key) {
                        const remainingKeys = Object.keys(firePaths);
                        selectedFireKey = remainingKeys[0] || null;
                        colorSafestPath(selectedFireKey ? firePaths[selectedFireKey] : []);
                    }
                }
            });

            // 🧹 إعادة تعيين البيانات أولاً
            warningCells.clear();
            fireCells.clear();
            firePaths = {};
            document.getElementById("fireList").innerHTML = "";

            if (data.status === "safe") {
                // Clear the safe path before resetting colors
                currentPath = [];
                selectedFireKey = null;
            }

            // 🧱 إعادة كل الخلايا للونها الأساسي
            updateMapColors();

            // 🟢 لا يوجد شيء
            if (data.status === "safe") {
                document.getElementById("fireList").innerText = "No active fires";
                document.getElementById("fireCount").innerText = 0;
                document.getElementById("activeAlertsCount").innerText = "0";
                if (document.getElementById("globalStatus")) document.getElementById("globalStatus").innerText = "Safe";
                if (document.getElementById("footerFireDetected")) document.getElementById("footerFireDetected").innerText = "No";
                if (document.getElementById("footerSysStatus")) document.getElementById("footerSysStatus").innerHTML = "✔ Operational";
                document.getElementById("footerSysStatus").className = "text-success";
                if (document.getElementById("simTimeDisplay")) document.getElementById("simTimeDisplay").innerText = (data.sim_time || 0) + "s";
                
                // Clear all danger numbers from the grid explicitly when fire terminates
                nodes.forEach(n => {
                    const key = `${n.row}-${n.col}`;
                    d3.select(`#text-${key}`).text("");
                });

                // Clear the safe path explicitly
                colorSafestPath([]);
                currentPath = [];
                selectedFireKey = null;
                
                return;
            } else {
                if (document.getElementById("globalStatus")) document.getElementById("globalStatus").innerText = "Critical";
                if (document.getElementById("footerFireDetected")) document.getElementById("footerFireDetected").innerText = "Yes";
                if (document.getElementById("footerSysStatus")) document.getElementById("footerSysStatus").innerHTML = "⚠ Emergency";
                document.getElementById("footerSysStatus").className = "text-danger";
                document.getElementById("activeAlertsCount").innerText = data.fires ? data.fires.length : 0;
                if (document.getElementById("simTimeDisplay")) document.getElementById("simTimeDisplay").innerText = (data.sim_time || 0) + "s";
            }

            // Update danger scores on the grid to visibly show risk values
            nodes.forEach(n => {
                const key = `${n.row}-${n.col}`;
                const textEl = d3.select(`#text-${key}`);
                textEl.text("");
            });

            // 🔴 First: fire cells
            data.fires.forEach(key => {

                fireCells.add(key);

                const [r, c] = key.split("-");
                d3.select(`#rect-${r}-${c}`).attr("fill", "#f70000ff");

                firePaths[key] = data.paths[key];
                console.log(`firePaths[${key}] set to:`, firePaths[key], "length:", firePaths[key] ? firePaths[key].length : "null/undefined");

                const node = nodes.find(n => n.row == r && n.col == c);
                const shopName = node?.label || `Shop (${r},${c})`;

                addFireToPanel(key, shopName);
            });

            // 🟠 Second: warning cells
            data.warnings.forEach(key => {

                warningCells.add(key);

                const [r, c] = key.split("-");
                d3.select(`#rect-${r}-${c}`).attr("fill", "#ff7b00ff");
            });

            // Update fire count
            document.getElementById("fireCount").innerText = fireCells.size;

            console.log("selectedFireKey:", selectedFireKey, "firePaths:", JSON.stringify(firePaths).substring(0, 300));

            // 🎯 Determine which path to show (selected fire or first available)
            if (!selectedFireKey || !firePaths[selectedFireKey]) {
                const firstKey = Object.keys(firePaths)[0];
                if (firstKey) selectedFireKey = firstKey;
            }

            if (selectedFireKey && firePaths[selectedFireKey]) {
                colorSafestPath(firePaths[selectedFireKey]);
            } else {
                selectedFireKey = null;
                colorSafestPath([]);
            }

        })
        .catch(err => console.error("Fire system error:", err));
}
function drawGrid() {
    const svg = d3.select("#map");
    svg.selectAll("*").remove();

    fetch("/grid")
        .then(res => res.json())
        .then(data => {
            nodes = data.nodes;
            const rows = Math.max(...nodes.map(n => n.row)) + 1;
            const cols = Math.max(...nodes.map(n => n.col)) + 1;
            globalCorridors = data.corridors || {};
            const width = cols * CELL_SIZE;
            const height = rows * CELL_SIZE;
            svg.attr("viewBox", `0 0 ${width} ${height}`)
                .attr("preserveAspectRatio", "xMidYMid meet");

            const g = svg.append("g").attr("id", "gridLayer");

            g.selectAll("rect")
                .data(nodes)
                .enter()
                .append("rect")
                .attr("id", d => `rect-${d.row}-${d.col}`) // ← مهم جداً!
                .attr("x", d => d.x)
                .attr("y", d => d.y)
                .attr("width", CELL_SIZE)
                .attr("height", CELL_SIZE)
                .attr("stroke", "rgba(0,0,0,0.1)")
                .attr("stroke-width", 1)
                .attr("fill", d => getBaseColor(d, `${d.row}-${d.col}`))
                .on("click", (event, d) => {


                    const rect = d3.select(event.currentTarget);

                    // ==== إذا كانت خلية ممر أبيض ====
                    if (d.value === 0 && d.corridor_id.length > 0) {
                        // إزالة تلوين الممرات السابقة
                        if (selectedCellCorridor !== undefined) {
                            nodes.forEach(n => {
                                n.corridor_id.forEach(cid => {
                                    const key = `${n.row}-${n.col}`;
                                    d3.select(`#rect-${key}`).attr("fill", getBaseColor(n, key));
                                });
                            });
                        }

                        // تلوين كل الممرات للخلية المختارة
                        d.corridor_id.forEach(cid => {
                            nodes.filter(n => n.corridor_id.includes(cid)).forEach(n => {
                                const key = `${n.row}-${n.col}`;
                                d3.select(`#rect-${key}`).attr("fill", "#3cdce7");
                            });
                        });

                        selectedCellCorridor = d.corridor_id; // ← الآن مصفوفة

                        // ===== استدعاء دالة التحديث المباشرة =====
                        updateSelectedCorridorInfo();
                        
                        event.stopPropagation();
                        return;
                    }



                    // ===== الخلايا الأخرى تبقى كما كانت سابقًا =====
                    const key = `${d.row}-${d.col}`;

                    // If a shop is clicked, clear active corridor selection
                    if (selectedCellCorridor !== undefined) {
                        nodes.forEach(n => {
                            n.corridor_id.forEach(cid => {
                                const cKey = `${n.row}-${n.col}`;
                                d3.select(`#rect-${cKey}`).attr("fill", getBaseColor(n, cKey));
                            });
                        });
                        selectedCellCorridor = undefined;
                    }


                    if (selectedCell && selectedCell !== rect) {
                        const prevData = selectedCell.datum();
                        const prevKey = `${prevData.row}-${prevData.col}`;
                        selectedCell.attr("fill", getBaseColor(prevData, prevKey));
                    }

                    rect.attr("fill", "#3cdce7");
                    selectedCell = rect;

                    let typeText = d.value === 2 ? "Shop" : d.value === 0 ? "Road" : d.value === 1 ? "Wall" : d.value === 3 ? "Exit" : "Fire";
                    let html = `
        <div style="margin-bottom:10px;"><b>Type: ${typeText}</b></div>
    `;
                    if (d.value === 2 && d.label) html += `<div><b>Shop:</b> ${d.label}</div>`;
                    document.getElementById("cellInfo").innerHTML = html;
                    event.stopPropagation();
                });

            // Add text labels for danger values
            g.selectAll("text.danger-label")
                .data(nodes)
                .enter()
                .append("text")
                .attr("class", "danger-label")
                .attr("id", d => `text-${d.row}-${d.col}`)
                .attr("x", d => d.x + CELL_SIZE / 2)
                .attr("y", d => d.y + CELL_SIZE / 2)
                .attr("dy", ".35em")
                .attr("text-anchor", "middle")
                .attr("fill", "black")
                .style("font-size", "8px")
                .style("font-weight", "normal")
                .style("pointer-events", "none")
                .text("");


            d3.select("body").on("click", () => {
                if (selectedCell) {
                    const data = selectedCell.datum();
                    const key = `${data.row}-${data.col}`;
                    selectedCell.attr("fill", getBaseColor(data, key));
                    selectedCell = null;
                    document.getElementById("cellInfo").innerHTML = "<div class='placeholder-text'>Click a cell to see details</div>";
                }
                
                if (selectedCellCorridor !== undefined) {
                    nodes.forEach(n => {
                        n.corridor_id.forEach(cid => {
                            const cKey = `${n.row}-${n.col}`;
                            d3.select(`#rect-${cKey}`).attr("fill", getBaseColor(n, cKey));
                        });
                    });
                    selectedCellCorridor = undefined;
                    document.getElementById("cellInfo").innerHTML = "<div class='placeholder-text'>Click a cell to see details</div>";
                }
            });
        });
}


// ===== رسم أول مرة =====
drawGrid();



