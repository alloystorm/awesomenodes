import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NONE = "-- history --";

let historyCache = [];
let labelToEntry = new Map();

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

function applyEntry(node, entry) {
    const set = (name, value) => {
        const w = node.widgets?.find((w) => w.name === name);
        if (w !== undefined && value !== undefined) {
            w.value = value;
            w.callback?.(value, app.canvas, node);
        }
    };
    set("prompt", entry.prompt);
    set("negative_prompt", entry.negative_prompt);
    set("width", entry.width);
    set("height", entry.height);
    set("seed", entry.seed);
    set("shuffle_seed", entry.shuffle_seed);
    node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "comfyui.promptManager",
    async setup() {
        await refreshHistory();
        api.addEventListener("prompt_manager.history_updated", refreshHistory);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "PromptManager") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);

            const widget = this.addWidget(
                "combo",
                "history",
                NONE,
                (value) => {
                    const entry = labelToEntry.get(value);
                    if (entry) applyEntry(this, entry);
                    // Reset so the same entry can be re-selected later.
                    widget.value = NONE;
                },
                { values: () => [NONE, ...labelToEntry.keys()] },
            );
            widget.serialize = false;

            return result;
        };
    },
});
