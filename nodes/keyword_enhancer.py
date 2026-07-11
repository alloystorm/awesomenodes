"""Random Keyword Enhancer node.

Appends random keywords from a dictionary to the prompt to enhance variety.
"""

import json
import os
import random

NODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYWORDS_FILE = os.path.join(NODE_DIR, "keywords.json")
DEFAULT_KEYWORDS = {
    "mixed": [
        "cinematic lighting", "highly detailed", "masterpiece", "trending on artstation", 
        "8k resolution", "sharp focus", "intricate details", "volumetric lighting",
        "concept art", "vibrant colors", "photorealistic"
    ],
    "styles": [
        "oil painting", "watercolor", "digital illustration", "anime style", "comic book art",
        "cyberpunk", "steampunk", "dark fantasy", "retro sci-fi"
    ]
}

def load_keywords():
    try:
        with open(KEYWORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(KEYWORDS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_KEYWORDS, f, indent=2)
        return DEFAULT_KEYWORDS

def extract_clip_vocab(clip):
    vocab = None
    if hasattr(clip, "tokenizer"):
        tokenizer = clip.tokenizer
        if hasattr(tokenizer, "get_vocab"):
            vocab = tokenizer.get_vocab()
        elif hasattr(tokenizer, "tokenizer") and hasattr(tokenizer.tokenizer, "get_vocab"):
            vocab = tokenizer.tokenizer.get_vocab()
        elif hasattr(tokenizer, "clip_l") and hasattr(tokenizer.clip_l, "tokenizer") and hasattr(tokenizer.clip_l.tokenizer, "get_vocab"):
            vocab = tokenizer.clip_l.tokenizer.get_vocab()
            
    if vocab and isinstance(vocab, dict):
        words = []
        for word in vocab.keys():
            if isinstance(word, bytes):
                try:
                    word = word.decode("utf-8")
                except Exception:
                    continue
            if word.endswith("</w>"):
                word = word[:-4]
            if len(word) > 2 and word.isalpha():
                words.append(word)
        return list(set(words))
    return []

class RandomKeywordAppender:
    CATEGORY = "utils/prompt"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("enhanced_prompt",)
    DESCRIPTION = "Appends random keywords from keywords.json or CLIP vocab to increase generation variety."

    @classmethod
    def INPUT_TYPES(cls):
        keywords_data = load_keywords()
        categories = ["all", "clip_vocab"] + list(keywords_data.keys())
        return {
            "required": {
                "prompt": ("STRING", {"forceInput": True}),
                "category": (categories, {"default": "all"}),
                "num_keywords": ("INT", {"default": 3, "min": 1, "max": 20}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": {
                "clip": ("CLIP",),
            }
        }
    
    def run(self, prompt, category, num_keywords, seed, clip=None):
        keywords_data = load_keywords()
        
        pool = []
        if category == "clip_vocab":
            if clip is not None:
                pool = extract_clip_vocab(clip)
            else:
                try:
                    clip_vocab_path = os.path.join(NODE_DIR, "clip_vocab.json")
                    with open(clip_vocab_path, "r", encoding="utf-8") as f:
                        pool = json.load(f)
                except Exception:
                    print("[Random Keyword Enhancer] Warning: category is 'clip_vocab' but no CLIP model was provided, and clip_vocab.json not found.")
        elif category == "all":
            for klist in keywords_data.values():
                pool.extend(klist)
            if clip is not None:
                pool.extend(extract_clip_vocab(clip))
            else:
                try:
                    clip_vocab_path = os.path.join(NODE_DIR, "clip_vocab.json")
                    with open(clip_vocab_path, "r", encoding="utf-8") as f:
                        pool.extend(json.load(f))
                except Exception:
                    pass
        else:
            pool = keywords_data.get(category, [])
            
        if not pool:
            return (prompt,)
            
        random.seed(seed)
        
        picks_count = min(num_keywords, len(pool))
        picks = random.sample(pool, picks_count)
        
        if picks:
            append_str = ", ".join(picks)
            if prompt.strip():
                new_prompt = prompt.rstrip()
                if new_prompt.endswith(","):
                    new_prompt = new_prompt + " " + append_str
                else:
                    new_prompt = new_prompt + ", " + append_str
            else:
                new_prompt = append_str
            return (new_prompt,)
        
        return (prompt,)

NODE_CLASS_MAPPINGS = {"RandomKeywordAppender": RandomKeywordAppender}
NODE_DISPLAY_NAME_MAPPINGS = {"RandomKeywordAppender": "Random Keyword Enhancer"}
