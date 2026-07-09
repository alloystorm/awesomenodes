"""Prompt Manager node.

Supplies a prompt to a workflow, keeps a local history of used prompts
(selectable from a dropdown on the node), and supports template placeholders
like {scene}, {environment}, {genre}, {character} whose picks advance between
runs according to a selectable shuffle mode (Freeze, Sequential, Sequential
Aligned, Iterate All, Random).
"""

import json
import os
import random
import re
import threading
import time

from aiohttp import web
from server import PromptServer

NODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE = os.path.join(NODE_DIR, "history.json")
TEMPLATES_FILE = os.path.join(NODE_DIR, "templates.json")
ENHANCERS_FILE = os.path.join(NODE_DIR, "enhancers.json")
MAX_HISTORY = 200
NONE_ENHANCER = "None"

_lock = threading.Lock()

DEFAULT_TEMPLATES = {
    "character": [
        "a weathered old sailor",
        "a young inventor with brass goggles",
        "an elegant sorceress in flowing robes",
        "a stoic android detective",
        "a cheerful street musician",
        "a battle-worn knight",
    ],
    "scene": [
        "a bustling marketplace",
        "a quiet library",
        "an abandoned factory",
        "a rooftop at sunset",
        "a misty harbor at dawn",
        "a neon-lit alleyway",
        "a grand ballroom",
        "a mountain summit",
    ],
    "environment": [
        "dense fog rolling in",
        "golden hour lighting",
        "heavy rain and wet reflections",
        "snow falling gently",
        "harsh midday sun",
        "moody overcast sky",
        "bioluminescent glow",
    ],
    "genre": [
        "cyberpunk",
        "dark fantasy",
        "retro sci-fi",
    ],
    "style": [
        "studio ghibli style",
        "baroque oil painting",
        "photorealistic",
        "watercolor illustration",
    ],
}

DEFAULT_ENHANCERS = {
    "Comic Page Art Director": (
        "You are a Comic Page Art Director. Given a user's raw idea for a comic page, expand it into a single, richly detailed image-generation prompt that describes one full comic PAGE containing multiple panels, to guide a text-to-image model.\n"
        "\n"
        "#### Panel Count Consistency (CRITICAL)\n"
        "- Decide the exact panel count first (typically 3-6), state it once in the layout summary, then describe EXACTLY that many panels — no more, no fewer. Count your panel descriptions before finishing.\n"
        "\n"
        "#### Art Style (choose per story, do not default to one look)\n"
        "- Infer a style that fits the genre/tone of THIS idea — do not reuse the same style for every page. Consider: noir mystery -> high-contrast black-and-white ink, deep shadows; comedic/food/slice-of-life -> bright flat colors, bold outlines, exaggerated expressions; epic fantasy/action -> painterly color, dramatic chiaroscuro; sci-fi -> clean linework, cool color grading; horror -> desaturated palette, jagged inking. If the user specifies a style, use it exactly.\n"
        "\n"
        "#### Panel Planning\n"
        "- Decide on a tier layout (rows of panels, e.g. \"3 tiers: a wide top panel, two panels in the middle tier, a tall panel on the right of the bottom tier\"). Plan every panel at the same importance first, then enlarge/merge specific panels for emphasis.\n"
        "- Reading order flows left-to-right, top-to-bottom (Western comics): panel 1 is top-left. If the user requests manga/right-to-left, MIRROR the actual panel positions so panel 1 is top-RIGHT and each tier proceeds right-to-left before dropping to the next tier — don't just relabel a left-to-right layout.\n"
        "- Describe each panel in reading order so the action and eye-line lead across the page and down to the next tier.\n"
        "- Always open with a \"Style: ...\" sentence and a \"Page layout: N panels in M tiers\" sentence, even if the user's raw idea already specifies a style — restate it there instead of skipping the summary.\n"
        "\n"
        "#### Panel Size & Shot Choice (match to story beat)\n"
        "- Close-up panels: character expressions, emotional reactions.\n"
        "- Inset panels (small panel overlapping a larger one): isolate a detail or object to imply importance.\n"
        "- Wide/establishing panels: setting, scale, group action.\n"
        "- Silhouette panels: drama, focus on shape/action over detail.\n"
        "- Splash panel (full page or near-full page): the single pivotal moment of the page.\n"
        "- Broken-border panels: figures/action bursting past the panel edge for intense movement.\n"
        "\n"
        "#### Gutters & Borders (pacing)\n"
        "- Standard thin gutters: smooth continuous transitions.\n"
        "- Wide gutters: a pause, a beat of reflection, time passing.\n"
        "- Borderless or overlapping panels: simultaneous or rapidly successive action.\n"
        "- Jagged/broken borders: shock or violent impact. Wavy or soft-edged borders: memory, flashback, dream.\n"
        "\n"
        "#### Dialogue & Lettering\n"
        "- If the user's idea implies speech, thought, or shouting, include the exact words in quotes inside a described speech bubble/thought bubble/shout burst, placed in the correct panel and positioned to match reading order.\n"
        "- Include sound effect lettering (SFX) as bold stylized text where impacts, action, or ambient sound would be drawn.\n"
        "- Do not invent dialogue the user did not imply.\n"
        "\n"
        "- Keep character appearance (clothing, hair, build) consistent across all panels within the page.\n"
        "\n"
        "#### Output Format (Strict)\n"
        "- Single continuous paragraph, natural language, English.\n"
        "- Describe panels in reading order, clearly separated (e.g. \"Panel 1 (top-left, wide shot): ... Panel 2 (top-right, close-up): ...\"), then gutter/border treatment, then any lettering.\n"
        "- NO titles, headings, code fences, or Markdown.\n"
        "- Never ask questions or request clarification; if the idea is thin, invent concrete, tasteful visual details to fill it out.\n"
        "- The two examples below show DIFFERENT genres using DIFFERENT styles and DIFFERENT gutter/border choices — pick what fits the CURRENT idea, don't copy either example's specific style or wording.\n"
        "\n"
        "#### Example 1\n"
        "Input: \"A student discovers she has superpowers in the school hallway\"\n"
        "Output:\n"
        "Style: dynamic ink-and-color American superhero comic, bold linework, halftone shading. Page layout: 4 panels in 3 tiers. Panel 1 (top, wide establishing shot): a crowded high school hallway between classes, lockers lining both walls, students in motion, fluorescent lighting overhead. Panel 2 (middle-left, medium shot): a teenage girl in a school uniform stumbles as her books float out of her arms, eyes wide in shock, a faint blue glow surrounding her hands. Panel 3 (middle-right, close-up, inset panel overlapping panel 2): her wide eyes reflected with sparks of light, sweat on her brow, mouth open mid-gasp. Panel 4 (bottom, full-width splash panel with a jagged broken border): she stands frozen as lockers bend and books hover frozen in mid-air around her, a shockwave of pale blue energy radiating outward in concentric rings, her hair whipping upward; a speech bubble near her face reads \"What... what is happening to me?!\" in bold jagged lettering, with \"FWOOM\" sound effect lettering bursting from the shockwave. Gutters: thin clean black gutters between panels 1-2-3, panel 4 breaks its border where the energy shockwave bursts past the frame edge to convey the force of the moment.\n"
        "\n"
        "#### Example 2\n"
        "Input: \"An old fisherman reels in a catch at dawn\"\n"
        "Output:\n"
        "Style: quiet watercolor and ink, muted blue-grey dawn palette, soft edges, minimal linework. Page layout: 3 panels in 2 tiers. Panel 1 (top, full-width wide shot): a small wooden boat adrift on a still, fog-covered sea, the first pale light of dawn breaking over distant hills, an old fisherman in an oilskin coat silhouetted against the pale sky, line taut in his weathered hands. Panel 2 (bottom-left, medium shot): his lined face in profile, calm and focused, water droplets catching the early light on his brow, the rod bending sharply as something pulls beneath the surface. Panel 3 (bottom-right, close-up): his hands, knuckles pale with effort, hauling the line as a silver fish breaks the surface in a spray of droplets frozen mid-air. Gutters: wide soft-edged gutters between all panels, unbroken by any jagged lines, to hold the unhurried, meditative pace of the scene; no dialogue, no sound effects — only the quiet ripple lines drawn radiating from the fish breaking the water."
    ),
}

PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_templates():
    templates = _load_json(TEMPLATES_FILE, None)
    if templates is None:
        templates = DEFAULT_TEMPLATES

    changed = False
    for k, v in templates.items():
        new_v = []
        for item in v:
            if isinstance(item, str):
                new_v.append({"text": item, "enabled": True})
                changed = True
            else:
                new_v.append(item)
        templates[k] = new_v

    if changed or not os.path.exists(TEMPLATES_FILE):
        with _lock:
            _save_json(TEMPLATES_FILE, templates)
    return templates


def load_enhancers():
    enhancers = _load_json(ENHANCERS_FILE, None)
    if enhancers is None:
        enhancers = dict(DEFAULT_ENHANCERS)
        with _lock:
            _save_json(ENHANCERS_FILE, enhancers)
    return enhancers


def discover_columns(text, templates):
    """Return an ordered list of (key, count) for each distinct placeholder in text.

    Order matches first appearance in the raw prompt text. "Iterate All" uses
    this order to treat the last-appearing placeholder as the fastest-changing
    column, like the least-significant digit of an odometer.
    """
    columns = []
    seen = set()
    for match in PLACEHOLDER_RE.finditer(text):
        body = match.group(1)
        if body.strip().lower() == "page":
            continue

        if "|" in body:
            options = [o.strip() for o in body.split("|") if o.strip()]
            if not options:
                continue
            key = "inline:" + "|".join(options)
            count = len(options)
        else:
            key = body.strip().lower()
            options = templates.get(key)
            if not options:
                continue
            valid_options = [o["text"] for o in options if isinstance(o, dict) and o.get("enabled", True)]
            if not valid_options:  # Fallback to all texts if all disabled
                valid_options = [o["text"] for o in options if isinstance(o, dict) and "text" in o]
            count = len(valid_options)
            if count == 0:
                continue

        if key not in seen:
            seen.add(key)
            columns.append((key, count))
    return columns


def resolve_template(text, index_map, templates, current_page=1):
    """Replace {aspect} and inline {a|b|c} placeholders.

    index_map maps each placeholder's key (aspect name, or "inline:a|b|c" for
    an inline pick list) to the index to use; it's resolved modulo the option
    count so it always lands on a valid choice.
    """
    def replace(match):
        body = match.group(1)
        if body.strip().lower() == "page":
            return str(current_page)

        if "|" in body:
            options = [o.strip() for o in body.split("|") if o.strip()]
            if not options:
                return match.group(0)
            key = "inline:" + "|".join(options)
            return str(options[index_map.get(key, 0) % len(options)])

        key = body.strip().lower()
        options = templates.get(key)
        if options:
            valid_options = [o["text"] for o in options if isinstance(o, dict) and o.get("enabled", True)]
            if not valid_options:  # Fallback to all texts if all disabled
                valid_options = [o["text"] for o in options if isinstance(o, dict) and "text" in o]
            if valid_options:
                return str(valid_options[index_map.get(key, 0) % len(valid_options)])
        return match.group(0)  # unknown aspect: leave untouched

    # Resolve repeatedly so template entries may themselves contain placeholders.
    for _ in range(5):
        new_text = PLACEHOLDER_RE.sub(replace, text)
        if new_text == text:
            break
        text = new_text
    return text


def save_history_entry(entry):
    with _lock:
        history = _load_json(HISTORY_FILE, [])
        # Dedupe on the raw prompt; move duplicates to the front.
        history = [
            h for h in history
            if not (
                h.get("prompt") == entry["prompt"]
            )
        ]
        history.insert(0, entry)
        del history[MAX_HISTORY:]
        _save_json(HISTORY_FILE, history)
    try:
        PromptServer.instance.send_sync("prompt_manager.history_updated", {})
    except Exception:
        pass


class PromptManager:
    CATEGORY = "utils/prompt"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "enhancer_instruction")
    DESCRIPTION = (
        "Supplies a prompt to a workflow. Keeps a local history "
        "selectable from the node, resolves {scene}/{environment}/{genre}/"
        "{character}/{a|b|c} placeholders using the selected shuffle mode, and outputs "
        "a selectable saved enhancer/system instruction for a text-generation node."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "dynamicPrompts": False,
                    "tooltip": "Positive prompt. Supports {character}, {scene}, {environment}, {genre}, {style}, {page}, and inline {a|b|c} placeholders.",
                }),
                "pages": ("INT", {
                    "default": 1, "min": 1, "max": 10000,
                    "tooltip": "Keep the same templates for N runs. Use {page} in your prompt to print the current counter.",
                }),
                "shuffle_mode": (["Freeze", "Sequential", "Sequential Aligned", "Iterate All", "Random"], {
                    "default": "Sequential",
                    "tooltip": (
                        "Controls how template placeholder picks advance between runs (once per `pages` group):\n"
                        "Freeze: keep the current picks.\n"
                        "Sequential: each column advances from its own current position, independently.\n"
                        "Sequential Aligned: all columns advance together, using the same index.\n"
                        "Iterate All: step through every combination (rightmost placeholder changes fastest).\n"
                        "Random: pick a random index per column each group."
                    ),
                }),
                "enhancer": ("STRING", {
                    "default": NONE_ENHANCER,
                    "tooltip": "Selected saved enhancer/system instruction (edit the list via the node's right-click menu). Output as 'enhancer_instruction'.",
                }),
                "debug_print": ("BOOLEAN", {"default": False, "tooltip": "Print final resolved prompt to terminal."}),
            }
        }

    def advance_index_map(self, mode, columns):
        """Compute the next per-column pick index for `mode`, persisted on self.

        Called once per `pages` group (see run()), and only for the columns
        found in the current prompt (see discover_columns()) — placeholders
        not present in the prompt this run are left untouched and ignored.

        self.column_indices is the single shared "current position" per
        column: every mode reads it as its starting point and writes its
        result back, so switching modes mid-workflow continues from wherever
        the columns currently sit (e.g. Random landing on a2-b3-c1, then
        switching to Sequential, advances to a3-b4-c2) rather than resetting.
        """
        if not hasattr(self, "column_indices"):
            self.column_indices = {}

        if not columns:
            return {}

        if mode == "Freeze":
            for key, _ in columns:
                self.column_indices.setdefault(key, 0)
            return {key: self.column_indices[key] % count for key, count in columns}

        if mode == "Sequential":
            # Each column advances independently from its own current index.
            for key, count in columns:
                self.column_indices[key] = (self.column_indices.get(key, -1) + 1) % count
            return {key: self.column_indices[key] for key, _ in columns}

        if mode == "Sequential Aligned":
            # A single shared step advances every column together, wrapping
            # at the size of the largest column (not each column's own
            # size), so columns re-sync to row 1 in lockstep once the
            # largest column would wrap — e.g. counts 5/8/5 give a1-b1-c1,
            # ... a1-b6-c1 at step 6, then back to a1-b1-c1 at step 9 —
            # instead of drifting apart via independent per-column wraps.
            max_count = max(count for _, count in columns)
            self.aligned_counter = getattr(self, "aligned_counter", -1) + 1
            step = self.aligned_counter % max_count
            index_map = {key: step % count for key, count in columns}
            self.column_indices.update(index_map)
            return index_map

        if mode == "Iterate All":
            self.combo_counter = getattr(self, "combo_counter", -1) + 1
            index_map = {}
            remaining = self.combo_counter
            for key, count in reversed(columns):  # rightmost placeholder changes fastest
                index_map[key] = remaining % count
                remaining //= count
            self.column_indices.update(index_map)
            return index_map

        # Random (and any unrecognized mode)
        index_map = {key: random.randrange(count) for key, count in columns}
        self.column_indices.update(index_map)
        return index_map

    def run(self, prompt, pages, shuffle_mode, enhancer=NONE_ENHANCER, debug_print=False):
        if not hasattr(self, "run_counter"):
            self.run_counter = 0
            self.target_pages = pages
            self.locked_index_map = None

        if getattr(self, "target_pages", 1) != pages:
            self.run_counter = 0
            self.target_pages = pages

        templates = load_templates()

        if self.locked_index_map is None or self.run_counter >= self.target_pages:
            self.run_counter = 0
            columns = discover_columns(prompt, templates)
            self.locked_index_map = self.advance_index_map(shuffle_mode, columns)

        self.run_counter += 1
        current_page = self.run_counter

        resolved = resolve_template(prompt, self.locked_index_map, templates, current_page=current_page)

        enhancers = load_enhancers()
        enhancer_instruction = enhancers.get(enhancer, "") if enhancer != NONE_ENHANCER else ""

        if debug_print:
            print(f"\n[PromptManager] Final Prompt (Page {current_page}/{pages}):\n{resolved}\n")
            if enhancer_instruction:
                print(f"[PromptManager] Enhancer ({enhancer}):\n{enhancer_instruction}\n")

        save_history_entry({
            "prompt": prompt,
            "resolved_prompt": resolved,
            "shuffle_mode": shuffle_mode,
            "pages": pages,
            "enhancer": enhancer,
            "timestamp": time.time(),
        })

        return (resolved, enhancer_instruction)


routes = PromptServer.instance.routes


@routes.get("/prompt_manager/history")
async def get_history(request):
    return web.json_response(_load_json(HISTORY_FILE, []))


@routes.post("/prompt_manager/history/delete")
async def delete_history(request):
    data = await request.json()
    timestamp = data.get("timestamp")
    with _lock:
        history = _load_json(HISTORY_FILE, [])
        if timestamp is None:
            history = []
        else:
            history = [h for h in history if h.get("timestamp") != timestamp]
        _save_json(HISTORY_FILE, history)
    return web.json_response({"ok": True})


@routes.get("/prompt_manager/templates")
async def get_templates(request):
    return web.json_response(load_templates())


@routes.post("/prompt_manager/templates")
async def set_templates(request):
    data = await request.json()
    if not isinstance(data, dict) or not all(
        isinstance(v, list) and all(isinstance(o, dict) and "text" in o for o in v)
        for v in data.values()
    ):
        return web.json_response({"error": "templates must be {aspect: [{'text': string, 'enabled': bool}, ...]}"}, status=400)
    with _lock:
        _save_json(TEMPLATES_FILE, {k.lower(): v for k, v in data.items()})
    return web.json_response({"ok": True})


@routes.get("/prompt_manager/enhancers")
async def get_enhancers(request):
    return web.json_response(load_enhancers())


@routes.post("/prompt_manager/enhancers")
async def set_enhancers(request):
    data = await request.json()
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        return web.json_response({"error": "enhancers must be {name: instruction_text}"}, status=400)
    if any(k == NONE_ENHANCER for k in data):
        return web.json_response({"error": f"'{NONE_ENHANCER}' is reserved and cannot be used as an enhancer name"}, status=400)
    with _lock:
        _save_json(ENHANCERS_FILE, data)
    try:
        PromptServer.instance.send_sync("prompt_manager.enhancers_updated", {})
    except Exception:
        pass
    return web.json_response({"ok": True})


NODE_CLASS_MAPPINGS = {"PromptManager": PromptManager}
NODE_DISPLAY_NAME_MAPPINGS = {"PromptManager": "Prompt Manager"}
