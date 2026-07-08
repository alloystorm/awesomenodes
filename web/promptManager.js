import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NONE = "-- history --";
const NONE_ENHANCER = "None";

let historyCache = [];
let labelToEntry = new Map();
let enhancerCache = {};

function makeLabel(entry, index) {
    const date = new Date((entry.timestamp || 0) * 1000);
    const stamp = `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
    let text = (entry.prompt || "").replace(/\s+/g, " ").trim();
    if (text.length > 70) text = text.slice(0, 70) + "…";
    return `${index + 1}. [${stamp}] ${text}`;
}

async function refreshHistory() {
    try {
        const res = await api.fetchApi("/prompt_manager/history");
        historyCache = await res.json();
        labelToEntry = new Map();
        historyCache.forEach((entry, i) => labelToEntry.set(makeLabel(entry, i), entry));
    } catch (e) {
        console.error("[PromptManager] failed to fetch history", e);
    }
}

async function refreshEnhancers() {
    try {
        const res = await api.fetchApi("/prompt_manager/enhancers");
        enhancerCache = await res.json();
    } catch (e) {
        console.error("[PromptManager] failed to fetch enhancers", e);
    }
}

function applyEntry(node, entry) {
    const set = (name, value) => {
        const w = node.widgets?.find((w) => w.name === name);
        if (w !== undefined && value !== undefined) {
            w.value = value;
            w.callback?.(value, app.canvas, node);
        }
    };
    set("prompt", entry.prompt);
    set("shuffle_seed", entry.shuffle_seed);
    if (entry.pages !== undefined) set("pages", entry.pages);
    if (entry.enhancer !== undefined) set("enhancer", entry.enhancer);
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "comfyui.promptManager",
    async setup() {
        await refreshHistory();
        await refreshEnhancers();
        api.addEventListener("prompt_manager.history_updated", refreshHistory);
        api.addEventListener("prompt_manager.enhancers_updated", refreshEnhancers);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "PromptManager") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);

            const historyWidget = this.addWidget(
                "combo",
                "history",
                NONE,
                (value) => {
                    const entry = labelToEntry.get(value);
                    if (entry) applyEntry(this, entry);
                    // Reset so the same entry can be re-selected later.
                    historyWidget.value = NONE;
                },
                { values: () => [NONE, ...labelToEntry.keys()] },
            );
            historyWidget.serialize = false;

            // The "enhancer" input arrives as a plain text widget; mutating
            // its .type in place doesn't take effect in the current frontend
            // (widgets are rendered by the component bound at creation), so
            // remove it and add a real combo widget with the same name in
            // its place — same technique as the "history" widget above.
            const enhancerIndex = this.widgets?.findIndex((w) => w.name === "enhancer") ?? -1;
            if (enhancerIndex !== -1) {
                const oldValue = this.widgets[enhancerIndex].value || NONE_ENHANCER;
                this.widgets.splice(enhancerIndex, 1);
                this.addWidget(
                    "combo",
                    "enhancer",
                    oldValue,
                    () => {},
                    { values: () => [NONE_ENHANCER, ...Object.keys(enhancerCache)] },
                );
                // addWidget appends to the end; move it back to where the
                // original text widget was for a stable layout.
                this.widgets.splice(enhancerIndex, 0, this.widgets.pop());
            }

            const editTemplatesBtn = this.addWidget("button", "Edit Templates", "edit_templates", () => showTemplateEditor());
            editTemplatesBtn.serialize = false;

            const editEnhancersBtn = this.addWidget("button", "Edit Enhancers", "edit_enhancers", () => showEnhancerEditor());
            editEnhancersBtn.serialize = false;

            return result;
        };

        const getExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function(_, options) {
            getExtraMenuOptions?.apply(this, arguments);
            options.push({
                content: "Edit Templates",
                callback: () => {
                    showTemplateEditor();
                }
            });
            options.push({
                content: "Edit Enhancers",
                callback: () => {
                    showEnhancerEditor();
                }
            });
        };
    },
});

async function showTemplateEditor() {
    let templates = {};
    try {
        const res = await api.fetchApi("/prompt_manager/templates");
        templates = await res.json();
    } catch (e) {
        alert("Failed to load templates");
        return;
    }

    if (Object.keys(templates).length === 0) {
        templates = { "scene": [] };
    }

    const COL_WIDTH = 220;
    let dragSrc = null; // { category, index }

    const overlay = document.createElement("div");
    Object.assign(overlay.style, {
        position: "fixed", top: "0", left: "0", width: "100%", height: "100%",
        backgroundColor: "rgba(0,0,0,0.7)", display: "flex", justifyContent: "center", alignItems: "center",
        zIndex: "1000",
    });

    const dialog = document.createElement("div");
    Object.assign(dialog.style, {
        backgroundColor: "#222", color: "#fff", padding: "20px", borderRadius: "8px",
        display: "flex", flexDirection: "column", width: "min(95vw, 1200px)", height: "min(85vh, 700px)",
        fontFamily: "sans-serif", boxShadow: "0 4px 14px rgba(0,0,0,0.5)",
    });

    const title = document.createElement("h3");
    title.innerText = "Edit Templates";
    title.style.margin = "0 0 4px 0";
    const subtitle = document.createElement("div");
    subtitle.innerText = "Drag ⠿ to reorder within a column — the row number is the index the shuffle seed picks (index = seed % count).";
    Object.assign(subtitle.style, { color: "#888", fontSize: "11px", margin: "0 0 12px 0" });

    const tableWrap = document.createElement("div");
    Object.assign(tableWrap.style, {
        flex: "1", overflow: "auto", border: "1px solid #444", borderRadius: "4px", backgroundColor: "#111",
    });

    const table = document.createElement("table");
    Object.assign(table.style, { borderCollapse: "collapse", width: "100%" });

    function styleCell(el, extra) {
        Object.assign(el.style, {
            border: "1px solid #333", padding: "4px 6px", verticalAlign: "top", boxSizing: "border-box",
            ...extra,
        });
        return el;
    }

    function render() {
        table.innerHTML = "";
        const categories = Object.keys(templates);
        const maxLen = Math.max(0, ...categories.map((c) => templates[c].length));

        // Header row: category name + delete-category, plus a trailing "+ column" cell.
        const thead = document.createElement("thead");
        const headRow = document.createElement("tr");

        const cornerTh = document.createElement("th");
        styleCell(cornerTh, {
            position: "sticky", top: "0", left: "0", zIndex: "3", backgroundColor: "#1a1a1a",
            width: "34px", minWidth: "34px",
        });
        headRow.appendChild(cornerTh);

        for (const cat of categories) {
            const th = document.createElement("th");
            styleCell(th, {
                position: "sticky", top: "0", zIndex: "2", backgroundColor: "#1a1a1a",
                width: COL_WIDTH + "px", minWidth: COL_WIDTH + "px", textAlign: "left",
            });

            const headInner = document.createElement("div");
            Object.assign(headInner.style, { display: "flex", alignItems: "center", gap: "6px" });

            const nameSpan = document.createElement("span");
            nameSpan.innerText = cat;
            Object.assign(nameSpan.style, {
                flex: "1", fontWeight: "bold", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            });

            const delCatBtn = document.createElement("span");
            delCatBtn.innerText = "×";
            Object.assign(delCatBtn.style, { color: "#ff5555", cursor: "pointer", fontWeight: "bold", padding: "0 4px" });
            delCatBtn.onclick = () => {
                if (confirm(`Delete category '${cat}' and all its items?`)) {
                    delete templates[cat];
                    render();
                }
            };

            headInner.appendChild(nameSpan);
            headInner.appendChild(delCatBtn);
            th.appendChild(headInner);
            headRow.appendChild(th);
        }

        const addCatTh = document.createElement("th");
        styleCell(addCatTh, {
            position: "sticky", top: "0", zIndex: "2", backgroundColor: "#1a1a1a",
            width: "48px", minWidth: "48px",
        });
        const addCatBtn = document.createElement("button");
        addCatBtn.innerText = "+";
        addCatBtn.title = "New category";
        Object.assign(addCatBtn.style, {
            width: "100%", padding: "4px", backgroundColor: "#2196F3", color: "#fff",
            border: "none", borderRadius: "3px", cursor: "pointer", fontWeight: "bold",
        });
        addCatBtn.onclick = () => {
            const name = prompt("Category name (e.g. 'style'):");
            if (name && !templates[name]) {
                templates[name] = [];
                render();
            }
        };
        addCatTh.appendChild(addCatBtn);
        headRow.appendChild(addCatTh);

        thead.appendChild(headRow);
        table.appendChild(thead);

        // Body rows: one per index position, aligned across all category columns.
        const tbody = document.createElement("tbody");

        for (let i = 0; i < maxLen; i++) {
            const tr = document.createElement("tr");

            const rowNumTd = document.createElement("td");
            styleCell(rowNumTd, {
                position: "sticky", left: "0", zIndex: "1", backgroundColor: "#1a1a1a",
                color: "#666", textAlign: "center", fontSize: "11px",
            });
            rowNumTd.innerText = String(i);
            tr.appendChild(rowNumTd);

            for (const cat of categories) {
                const items = templates[cat];
                const td = document.createElement("td");
                styleCell(td, {});

                if (i < items.length) {
                    const item = items[i];
                    const cellRow = document.createElement("div");
                    Object.assign(cellRow.style, { display: "flex", alignItems: "center", gap: "6px" });

                    td.ondragover = (e) => {
                        if (!dragSrc || dragSrc.category !== cat) return;
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "move";
                        td.style.boxShadow = "inset 0 2px 0 #2196F3";
                    };
                    td.ondragleave = () => { td.style.boxShadow = ""; };
                    td.ondrop = (e) => {
                        e.preventDefault();
                        td.style.boxShadow = "";
                        if (!dragSrc || dragSrc.category !== cat || dragSrc.index === i) return;
                        const [moved] = items.splice(dragSrc.index, 1);
                        items.splice(i, 0, moved);
                        dragSrc = null;
                        render();
                    };

                    const dragHandle = document.createElement("span");
                    dragHandle.innerText = "⠿";
                    dragHandle.draggable = true;
                    Object.assign(dragHandle.style, { color: "#666", cursor: "grab" });
                    dragHandle.ondragstart = (e) => {
                        dragSrc = { category: cat, index: i };
                        e.dataTransfer.effectAllowed = "move";
                        cellRow.style.opacity = "0.4";
                    };
                    dragHandle.ondragend = () => {
                        dragSrc = null;
                        cellRow.style.opacity = "1";
                    };

                    const checkbox = document.createElement("input");
                    checkbox.type = "checkbox";
                    checkbox.checked = item.enabled !== false; // default true
                    checkbox.onchange = (e) => { item.enabled = e.target.checked; };

                    const textInput = document.createElement("input");
                    textInput.type = "text";
                    textInput.value = item.text || item; // fallback if somehow still string
                    Object.assign(textInput.style, {
                        flex: "1", minWidth: "0", padding: "3px 5px", backgroundColor: "#1a1a1a", color: "#fff",
                        border: "1px solid #333", borderRadius: "3px", outline: "none", fontSize: "12px",
                    });
                    textInput.oninput = (e) => { item.text = e.target.value; };

                    const delBtn = document.createElement("span");
                    delBtn.innerText = "×";
                    Object.assign(delBtn.style, { color: "#ff5555", cursor: "pointer", fontWeight: "bold", padding: "0 2px" });
                    delBtn.onclick = () => {
                        items.splice(i, 1);
                        render();
                    };

                    cellRow.appendChild(dragHandle);
                    cellRow.appendChild(checkbox);
                    cellRow.appendChild(textInput);
                    cellRow.appendChild(delBtn);
                    td.appendChild(cellRow);
                }

                tr.appendChild(td);
            }

            tr.appendChild(styleCell(document.createElement("td"), {}));
            tbody.appendChild(tr);
        }

        // Trailing "add item" row, one input per category column.
        const addTr = document.createElement("tr");
        addTr.appendChild(styleCell(document.createElement("td"), { position: "sticky", left: "0", backgroundColor: "#1a1a1a" }));

        for (const cat of categories) {
            const td = document.createElement("td");
            styleCell(td, {});
            const input = document.createElement("input");
            input.type = "text";
            input.placeholder = "+ add item";
            Object.assign(input.style, {
                width: "100%", padding: "3px 5px", backgroundColor: "#111", color: "#fff",
                border: "1px dashed #444", borderRadius: "3px", outline: "none", fontSize: "12px", boxSizing: "border-box",
            });
            input.onkeydown = (e) => {
                if (e.key === "Enter") {
                    const val = input.value.trim();
                    if (val) {
                        templates[cat].push({ text: val, enabled: true });
                        render();
                    }
                }
            };
            td.appendChild(input);
            addTr.appendChild(td);
        }
        addTr.appendChild(styleCell(document.createElement("td"), {}));
        tbody.appendChild(addTr);

        table.appendChild(tbody);
    }

    const btnRow = document.createElement("div");
    Object.assign(btnRow.style, {
        display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "15px",
    });

    const baseBtnStyle = {
        padding: "8px 16px", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "14px", fontWeight: "bold"
    };

    const closeBtn = document.createElement("button");
    closeBtn.innerText = "Cancel";
    Object.assign(closeBtn.style, baseBtnStyle, { backgroundColor: "#555", color: "#fff" });
    closeBtn.onclick = () => document.body.removeChild(overlay);

    const saveBtn = document.createElement("button");
    saveBtn.innerText = "Save";
    Object.assign(saveBtn.style, baseBtnStyle, { backgroundColor: "#4CAF50", color: "#fff" });
    saveBtn.onclick = async () => {
        try {
            const res = await api.fetchApi("/prompt_manager/templates", {
                method: "POST",
                body: JSON.stringify(templates),
            });
            if (res.status === 200) {
                document.body.removeChild(overlay);
            } else {
                const err = await res.json();
                alert("Error saving: " + (err.error || "Unknown"));
            }
        } catch (e) {
            alert("Network error: " + e.message);
        }
    };

    btnRow.appendChild(closeBtn);
    btnRow.appendChild(saveBtn);

    tableWrap.appendChild(table);

    dialog.appendChild(title);
    dialog.appendChild(subtitle);
    dialog.appendChild(tableWrap);
    dialog.appendChild(btnRow);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    render();
}

async function showEnhancerEditor() {
    let enhancers = {};
    try {
        const res = await api.fetchApi("/prompt_manager/enhancers");
        enhancers = await res.json();
    } catch (e) {
        alert("Failed to load enhancers");
        return;
    }

    let activeName = Object.keys(enhancers)[0];

    const overlay = document.createElement("div");
    Object.assign(overlay.style, {
        position: "fixed", top: "0", left: "0", width: "100%", height: "100%",
        backgroundColor: "rgba(0,0,0,0.7)", display: "flex", justifyContent: "center", alignItems: "center",
        zIndex: "1000",
    });

    const dialog = document.createElement("div");
    Object.assign(dialog.style, {
        backgroundColor: "#222", color: "#fff", padding: "20px", borderRadius: "8px",
        display: "flex", flexDirection: "column", width: "820px", height: "600px",
        fontFamily: "sans-serif", boxShadow: "0 4px 14px rgba(0,0,0,0.5)",
    });

    const title = document.createElement("h3");
    title.innerText = "Edit Enhancers";
    title.style.margin = "0 0 15px 0";

    const workspace = document.createElement("div");
    Object.assign(workspace.style, {
        display: "flex", flex: "1", border: "1px solid #444", borderRadius: "4px", overflow: "hidden"
    });

    // Left side: enhancer names
    const sidebar = document.createElement("div");
    Object.assign(sidebar.style, {
        width: "200px", backgroundColor: "#1a1a1a", borderRight: "1px solid #444",
        display: "flex", flexDirection: "column", overflowY: "auto"
    });

    // Right side: instruction textarea for the selected enhancer
    const content = document.createElement("div");
    Object.assign(content.style, {
        flex: "1", backgroundColor: "#111", display: "flex", flexDirection: "column",
        padding: "10px", gap: "8px"
    });

    const nameLabel = document.createElement("div");
    Object.assign(nameLabel.style, { color: "#aaa", fontSize: "12px" });

    const textarea = document.createElement("textarea");
    Object.assign(textarea.style, {
        flex: "1", padding: "10px", backgroundColor: "#1a1a1a", color: "#fff",
        border: "1px solid #444", borderRadius: "4px", outline: "none", resize: "none",
        fontFamily: "monospace", fontSize: "12px", lineHeight: "1.4",
    });
    textarea.oninput = () => {
        if (activeName) enhancers[activeName] = textarea.value;
    };

    const addNameBtn = document.createElement("button");
    addNameBtn.innerText = "+ New Enhancer";
    Object.assign(addNameBtn.style, {
        padding: "10px", backgroundColor: "#222", color: "#ccc", border: "none",
        borderTop: "1px solid #444", cursor: "pointer", textAlign: "left", fontSize: "12px",
        marginTop: "auto"
    });
    addNameBtn.onclick = () => {
        const name = prompt("Enhancer name:");
        if (name && name !== "None" && !enhancers[name]) {
            enhancers[name] = "";
            activeName = name;
            render();
            textarea.focus();
        } else if (name === "None") {
            alert("'None' is reserved and can't be used as an enhancer name.");
        }
    };

    function render() {
        sidebar.innerHTML = "";
        for (const name of Object.keys(enhancers)) {
            const nameBtn = document.createElement("div");
            Object.assign(nameBtn.style, {
                padding: "10px", cursor: "pointer", borderBottom: "1px solid #333",
                backgroundColor: activeName === name ? "#333" : "transparent",
                color: activeName === name ? "#fff" : "#aaa",
                fontWeight: activeName === name ? "bold" : "normal",
                display: "flex", justifyContent: "space-between", alignItems: "center"
            });

            const nameSpan = document.createElement("span");
            nameSpan.innerText = name;
            nameSpan.style.flex = "1";
            nameSpan.style.overflow = "hidden";
            nameSpan.style.textOverflow = "ellipsis";
            nameSpan.style.whiteSpace = "nowrap";
            nameBtn.appendChild(nameSpan);

            const delBtn = document.createElement("span");
            delBtn.innerText = "×";
            Object.assign(delBtn.style, {
                color: "#ff5555", padding: "0 5px", fontSize: "16px", fontWeight: "bold"
            });
            delBtn.onclick = (e) => {
                e.stopPropagation();
                if (confirm(`Delete enhancer '${name}'?`)) {
                    delete enhancers[name];
                    if (activeName === name) activeName = Object.keys(enhancers)[0];
                    render();
                }
            };
            nameBtn.appendChild(delBtn);

            nameBtn.onclick = () => {
                activeName = name;
                render();
            };
            sidebar.appendChild(nameBtn);
        }
        sidebar.appendChild(addNameBtn);

        if (activeName) {
            nameLabel.innerText = activeName;
            textarea.value = enhancers[activeName] || "";
            textarea.disabled = false;
        } else {
            nameLabel.innerText = "No enhancers yet";
            textarea.value = "";
            textarea.disabled = true;
        }
    }

    const btnRow = document.createElement("div");
    Object.assign(btnRow.style, {
        display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "15px",
    });

    const baseBtnStyle = {
        padding: "8px 16px", border: "none", borderRadius: "4px", cursor: "pointer", fontSize: "14px", fontWeight: "bold"
    };

    const closeBtn = document.createElement("button");
    closeBtn.innerText = "Cancel";
    Object.assign(closeBtn.style, baseBtnStyle, { backgroundColor: "#555", color: "#fff" });
    closeBtn.onclick = () => document.body.removeChild(overlay);

    const saveBtn = document.createElement("button");
    saveBtn.innerText = "Save";
    Object.assign(saveBtn.style, baseBtnStyle, { backgroundColor: "#4CAF50", color: "#fff" });
    saveBtn.onclick = async () => {
        try {
            const res = await api.fetchApi("/prompt_manager/enhancers", {
                method: "POST",
                body: JSON.stringify(enhancers),
            });
            if (res.status === 200) {
                document.body.removeChild(overlay);
            } else {
                const err = await res.json();
                alert("Error saving: " + (err.error || "Unknown"));
            }
        } catch (e) {
            alert("Network error: " + e.message);
        }
    };

    content.appendChild(nameLabel);
    content.appendChild(textarea);

    workspace.appendChild(sidebar);
    workspace.appendChild(content);

    btnRow.appendChild(closeBtn);
    btnRow.appendChild(saveBtn);

    dialog.appendChild(title);
    dialog.appendChild(workspace);
    dialog.appendChild(btnRow);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    render();
}
