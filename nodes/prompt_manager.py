"""Prompt Manager node.

Supplies a prompt to a workflow, keeps a local history of used prompts
(selectable from a dropdown on the node), and supports template placeholders
like {scene}, {environment}, {genre}, {character} that are shuffled between
runs via a dedicated shuffle seed.
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


def resolve_template(text, shuffle_seed, templates, current_page=1):
    """Replace {aspect} and inline {a|b|c} placeholders.

    Picks are deterministic for a given shuffle_seed, so a fixed seed keeps
    the same picks across runs and a randomized seed reshuffles them.
    """
    rng = random.Random(shuffle_seed)

    def replace(match):
        body = match.group(1)
        if body.strip().lower() == "page":
            return str(current_page)

        if "|" in body:
            options = [o.strip() for o in body.split("|") if o.strip()]
            return rng.choice(options) if options else ""
        key = body.strip().lower()
        options = templates.get(key)
        if options:
            valid_options = [o["text"] for o in options if isinstance(o, dict) and o.get("enabled", True)]
            if not valid_options:  # Fallback to all texts if all disabled
                valid_options = [o["text"] for o in options if isinstance(o, dict) and "text" in o]
            if valid_options:
                return str(rng.choice(valid_options))
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
        "{character}/{a|b|c} placeholders using the shuffle seed, and outputs "
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
                "shuffle_seed": ("INT", {
                    "default": 0, "min": 0, "max": 0xffffffffffffffff,
                    "control_after_generate": True,
                    "tooltip": "Controls template placeholder picks. Set to 'randomize' to reshuffle aspects each run, 'fixed' to keep the current picks.",
                }),
                "enhancer": ("STRING", {
                    "default": NONE_ENHANCER,
                    "tooltip": "Selected saved enhancer/system instruction (edit the list via the node's right-click menu). Output as 'enhancer_instruction'.",
                }),
                "debug_print": ("BOOLEAN", {"default": False, "tooltip": "Print final resolved prompt to terminal."}),
            }
        }

    def run(self, prompt, pages, shuffle_seed, enhancer=NONE_ENHANCER, debug_print=False):
        if not hasattr(self, "run_counter"):
            self.run_counter = 0
            self.locked_seed = shuffle_seed
            self.target_pages = pages

        if getattr(self, "target_pages", 1) != pages:
            self.run_counter = 0
            self.target_pages = pages
            self.locked_seed = shuffle_seed

        if self.run_counter >= self.target_pages:
            self.run_counter = 0
            self.locked_seed = shuffle_seed

        self.run_counter += 1
        current_page = self.run_counter

        templates = load_templates()
        resolved = resolve_template(prompt, self.locked_seed, templates, current_page=current_page)

        enhancers = load_enhancers()
        enhancer_instruction = enhancers.get(enhancer, "") if enhancer != NONE_ENHANCER else ""

        if debug_print:
            print(f"\n[PromptManager] Final Prompt (Page {current_page}/{pages}):\n{resolved}\n")
            if enhancer_instruction:
                print(f"[PromptManager] Enhancer ({enhancer}):\n{enhancer_instruction}\n")

        save_history_entry({
            "prompt": prompt,
            "resolved_prompt": resolved,
            "shuffle_seed": shuffle_seed,
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
