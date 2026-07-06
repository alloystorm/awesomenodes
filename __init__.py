"""ComfyUI Prompt Manager.

A single node that supplies prompt + key generation settings (size, seed) to a
workflow, keeps a local history of used prompts (selectable from a dropdown on
the node), and supports template placeholders like {scene}, {environment},
{genre}, {character} that are shuffled between runs via a dedicated shuffle
seed.
"""

import json
import os
import random
import re
import threading
import time

from aiohttp import web
from server import PromptServer

NODE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(NODE_DIR, "history.json")
TEMPLATES_FILE = os.path.join(NODE_DIR, "templates.json")
MAX_HISTORY = 200

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
        with _lock:
            _save_json(TEMPLATES_FILE, templates)
    return templates


def resolve_template(text, shuffle_seed, templates):
    """Replace {aspect} and inline {a|b|c} placeholders.

    Picks are deterministic for a given shuffle_seed, so a fixed seed keeps
    the same picks across runs and a randomized seed reshuffles them.
    """
    rng = random.Random(shuffle_seed)

    def replace(match):
        body = match.group(1)
        if "|" in body:
            options = [o.strip() for o in body.split("|") if o.strip()]
            return rng.choice(options) if options else ""
        key = body.strip().lower()
        options = templates.get(key)
        if options:
            return str(rng.choice(options))
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
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    DESCRIPTION = (
        "Supplies a prompt to a workflow. Keeps a local history "
        "selectable from the node, and resolves {scene}/{environment}/{genre}/"
        "{character}/{a|b|c} placeholders using the shuffle seed."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "dynamicPrompts": False,
                    "tooltip": "Positive prompt. Supports {character}, {scene}, {environment}, {genre}, {style} and inline {a|b|c} placeholders.",
                }),
                "shuffle_seed": ("INT", {
                    "default": 0, "min": 0, "max": 0xffffffffffffffff,
                    "control_after_generate": True,
                    "tooltip": "Controls template placeholder picks. Set to 'randomize' to reshuffle aspects each run, 'fixed' to keep the current picks.",
                }),
            }
        }

    def run(self, prompt, shuffle_seed):
        templates = load_templates()
        resolved = resolve_template(prompt, shuffle_seed, templates)

        save_history_entry({
            "prompt": prompt,
            "resolved_prompt": resolved,
            "shuffle_seed": shuffle_seed,
            "timestamp": time.time(),
        })

        return (resolved,)


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
        isinstance(v, list) and all(isinstance(o, str) for o in v)
        for v in data.values()
    ):
        return web.json_response({"error": "templates must be {aspect: [string, ...]}"}, status=400)
    with _lock:
        _save_json(TEMPLATES_FILE, {k.lower(): v for k, v in data.items()})
    return web.json_response({"ok": True})


NODE_CLASS_MAPPINGS = {"PromptManager": PromptManager}
NODE_DISPLAY_NAME_MAPPINGS = {"PromptManager": "Prompt Manager"}
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
