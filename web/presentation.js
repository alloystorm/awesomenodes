import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

let overlay = null;
let gridContainer = null;
let currentImages = [];
let maxImages = 1; // updated based on layout
let currentIndex = 0;
let isPresenting = false;

function parseLayout(layoutStr) {
    if (layoutStr === "2x1") return { rows: 1, cols: 2, max: 2 };
    if (layoutStr === "2x2") return { rows: 2, cols: 2, max: 4 };
    if (layoutStr === "3x3") return { rows: 3, cols: 3, max: 9 };
    return { rows: 1, cols: 1, max: 1 }; // default 1x1
}

function ensureOverlay() {
    if (overlay) return;
    
    overlay = document.createElement("div");
    Object.assign(overlay.style, {
        position: "fixed", top: "0", left: "0", width: "100%", height: "100%",
        backgroundColor: "#050505", zIndex: "9999", display: "none",
        flexDirection: "column", boxSizing: "border-box"
    });

    const header = document.createElement("div");
    Object.assign(header.style, {
        display: "flex", justifyContent: "flex-end", padding: "10px",
        backgroundColor: "rgba(0,0,0,0.5)", position: "absolute", top: "0", right: "0", zIndex: "10"
    });

    const closeBtn = document.createElement("button");
    closeBtn.innerText = "Exit Full Screen [Esc]";
    Object.assign(closeBtn.style, {
        padding: "8px 16px", backgroundColor: "#333", color: "#fff", border: "1px solid #555",
        borderRadius: "4px", cursor: "pointer", fontWeight: "bold"
    });
    closeBtn.onclick = () => stopPresentation();
    
    header.appendChild(closeBtn);
    overlay.appendChild(header);

    gridContainer = document.createElement("div");
    Object.assign(gridContainer.style, {
        flex: "1", display: "grid", gap: "10px", padding: "10px",
        width: "100%", height: "100%", boxSizing: "border-box",
        alignItems: "center", justifyItems: "center"
    });
    
    overlay.appendChild(gridContainer);
    document.body.appendChild(overlay);

    // Close on escape key
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && isPresenting) stopPresentation();
    });
}

function startPresentation(layoutStr) {
    ensureOverlay();
    const layout = parseLayout(layoutStr);
    
    // If layout changes, we might want to resize currentImages array, but we can just let it overwrite or clear
    if (maxImages !== layout.max) {
        currentImages = currentImages.slice(0, layout.max);
        if (currentIndex >= layout.max) currentIndex = 0;
    }
    
    maxImages = layout.max;
    
    Object.assign(gridContainer.style, {
        gridTemplateColumns: `repeat(${layout.cols}, 1fr)`,
        gridTemplateRows: `repeat(${layout.rows}, 1fr)`,
    });
    
    overlay.style.display = "flex";
    isPresenting = true;
    renderGrid();
}

function stopPresentation() {
    if (overlay) overlay.style.display = "none";
    isPresenting = false;
}

function saveImage(imageInfo, btnElement) {
    btnElement.innerText = "Saving...";
    btnElement.disabled = true;
    
    api.fetchApi("/presentation_node/save", {
        method: "POST",
        body: JSON.stringify({
            filename: imageInfo.filename,
            subfolder: imageInfo.subfolder,
            type: imageInfo.type
        })
    }).then(res => res.json()).then(data => {
        if (data.ok) {
            btnElement.innerText = "Saved!";
            btnElement.style.backgroundColor = "#4CAF50";
        } else {
            alert("Save failed: " + data.error);
            btnElement.innerText = "Save 💾";
            btnElement.disabled = false;
        }
    }).catch(err => {
        alert("Network error: " + err);
        btnElement.innerText = "Save 💾";
        btnElement.disabled = false;
    });
}

function renderGrid() {
    if (!gridContainer) return;
    
    if (gridContainer.children.length !== maxImages) {
        gridContainer.innerHTML = "";
        for (let i = 0; i < maxImages; i++) {
            const cell = document.createElement("div");
            Object.assign(cell.style, {
                width: "100%", height: "100%", display: "flex", 
                justifyContent: "center", alignItems: "center",
                position: "relative", backgroundColor: "#1a1a1a", borderRadius: "8px", overflow: "hidden"
            });
            cell.id = `presentation-cell-${i}`;
            gridContainer.appendChild(cell);
            
            if (currentImages[i]) {
                updateCell(i, currentImages[i]);
            } else {
                const placeholder = document.createElement("div");
                placeholder.innerText = "Waiting for image...";
                placeholder.style.color = "#555";
                placeholder.style.fontFamily = "sans-serif";
                cell.appendChild(placeholder);
            }
        }
    } else {
        for (let i = 0; i < maxImages; i++) {
            if (currentImages[i]) updateCell(i, currentImages[i]);
        }
    }
}

function updateCell(index, imageInfo) {
    const cell = document.getElementById(`presentation-cell-${index}`);
    if (!cell) return;
    
    cell.innerHTML = ""; // clear previous contents
    
    const img = document.createElement("img");
    img.src = api.apiURL(`/view?filename=${encodeURIComponent(imageInfo.filename)}&type=${imageInfo.type}&subfolder=${encodeURIComponent(imageInfo.subfolder)}&t=${Date.now()}`);
    Object.assign(img.style, {
        maxWidth: "100%", maxHeight: "100%", objectFit: "contain"
    });
    cell.appendChild(img);
    
    // Render save button if it's a temporary image (manual mode)
    if (imageInfo.type === "temp") {
        const saveBtn = document.createElement("button");
        saveBtn.innerText = "Save 💾";
        Object.assign(saveBtn.style, {
            position: "absolute", bottom: "10px", right: "10px",
            padding: "10px 15px", backgroundColor: "rgba(0,0,0,0.8)", color: "#fff",
            border: "1px solid #555", borderRadius: "4px", cursor: "pointer",
            fontWeight: "bold", zIndex: "20",
            transition: "all 0.2s ease"
        });
        
        saveBtn.onclick = () => saveImage(imageInfo, saveBtn);
        
        // Add hover effect
        saveBtn.onmouseover = () => { if (!saveBtn.disabled) saveBtn.style.backgroundColor = "#333"; };
        saveBtn.onmouseout = () => { if (!saveBtn.disabled) saveBtn.style.backgroundColor = "rgba(0,0,0,0.8)"; };
        
        cell.appendChild(saveBtn);
    } else if (imageInfo.type === "output") {
        // For auto mode, show a small indicator that it's already saved
        const badge = document.createElement("div");
        badge.innerText = "Auto Saved ✔";
        Object.assign(badge.style, {
            position: "absolute", bottom: "10px", right: "10px",
            padding: "5px 10px", backgroundColor: "rgba(76, 175, 80, 0.8)", color: "#fff",
            borderRadius: "4px", fontSize: "12px", fontWeight: "bold", zIndex: "20"
        });
        cell.appendChild(badge);
    }
}

app.registerExtension({
    name: "comfyui.presentationNode",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "PresentationNode") {
            
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                
                // Add a "Present" button to the node UI
                const presentBtn = this.addWidget("button", "Present (Full Screen)", "present", () => {
                    const layoutWidget = this.widgets.find(w => w.name === "layout");
                    const layoutStr = layoutWidget ? layoutWidget.value : "1x1";
                    startPresentation(layoutStr);
                });
                presentBtn.serialize = false;
                
                return result;
            };

            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                onExecuted?.apply(this, arguments);
                
                if (message && message.images) {
                    const layoutWidget = this.widgets.find(w => w.name === "layout");
                    const layoutStr = layoutWidget ? layoutWidget.value : "1x1";
                    const layout = parseLayout(layoutStr);
                    
                    // ensure layout constraints match current node setting
                    if (maxImages !== layout.max && isPresenting) {
                        maxImages = layout.max;
                        Object.assign(gridContainer.style, {
                            gridTemplateColumns: `repeat(${layout.cols}, 1fr)`,
                            gridTemplateRows: `repeat(${layout.rows}, 1fr)`,
                        });
                        renderGrid();
                    }
                    
                    // Add new images, overriding circularly based on max layout
                    for (const img of message.images) {
                        currentImages[currentIndex] = img;
                        if (isPresenting) {
                            updateCell(currentIndex, img);
                        }
                        currentIndex = (currentIndex + 1) % layout.max;
                    }
                }
            };
        }
    }
});
