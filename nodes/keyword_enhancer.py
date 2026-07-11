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

import torch
import torch.nn.functional as F
import nltk

def get_pos_category(pos_tag):
    if pos_tag.startswith('NN'): return 'noun'
    elif pos_tag.startswith('VB'): return 'verb'
    elif pos_tag.startswith('JJ'): return 'adjective'
    elif pos_tag.startswith('RB'): return 'adverb'
    return 'other'

def lazy_load_nltk():
    try:
        nltk.data.find('taggers/averaged_perceptron_tagger')
    except LookupError:
        nltk.download('averaged_perceptron_tagger', quiet=True)
    try:
        nltk.data.find('taggers/averaged_perceptron_tagger_eng')
    except LookupError:
        nltk.download('averaged_perceptron_tagger_eng', quiet=True)

def extract_clip_vocab_and_embeddings(clip):
    vocab = None
    tokenizer_obj = None
    if hasattr(clip, "tokenizer"):
        tokenizer = clip.tokenizer
        tokenizer_obj = tokenizer
        if hasattr(tokenizer, "get_vocab"):
            vocab = tokenizer.get_vocab()
        elif hasattr(tokenizer, "tokenizer") and hasattr(tokenizer.tokenizer, "get_vocab"):
            vocab = tokenizer.tokenizer.get_vocab()
            tokenizer_obj = tokenizer.tokenizer
        elif hasattr(tokenizer, "clip_l") and hasattr(tokenizer.clip_l, "tokenizer") and hasattr(tokenizer.clip_l.tokenizer, "get_vocab"):
            vocab = tokenizer.clip_l.tokenizer.get_vocab()
            tokenizer_obj = tokenizer.clip_l.tokenizer
            
    # Try to find token embeddings matrix
    embeds = None
    try:
        model = clip.patcher.model
        if hasattr(model, "clip_l"):
            embeds = model.clip_l.transformer.text_model.embeddings.token_embedding.weight
        elif hasattr(model, "clip_g"):
            embeds = model.clip_g.transformer.text_model.embeddings.token_embedding.weight
        elif hasattr(model, "transformer") and hasattr(model.transformer, "text_model"):
            embeds = model.transformer.text_model.embeddings.token_embedding.weight
    except Exception:
        pass

    return vocab, embeds, tokenizer_obj

def get_semantic_clip_vocab(clip, prompt, top_k=100, pos_filter="any", semantic_search=True, threshold=-1.0):
    vocab, token_embeds, tokenizer_obj = extract_clip_vocab_and_embeddings(clip)
    
    # Fast path if we can't do semantic search: just return all clean words
    if not vocab or not isinstance(vocab, dict):
        return []
        
    if pos_filter != "any":
        lazy_load_nltk()
        
    def clean_word(w):
        if isinstance(w, bytes):
            try:
                w = w.decode("utf-8")
            except Exception:
                return None
        if w.endswith("</w>"):
            w = w[:-4]
        if len(w) > 2 and w.isalpha():
            return w
        return None

    if token_embeds is None or tokenizer_obj is None or not prompt.strip() or not semantic_search:
        # Fallback: return all valid words
        words = []
        for word in vocab.keys():
            cw = clean_word(word)
            if cw: words.append(cw)
        return list(set(words))
        
    # Semantic Search Path
    try:
        # 1. Tokenize prompt (just get the ids using whatever tokenizer callable is available)
        if callable(tokenizer_obj):
            try:
                # huggingface tokenizer usually returns a dict
                inputs = tokenizer_obj(prompt, truncation=True)
                input_ids = inputs.get("input_ids", [])
            except Exception:
                # ComfyUI tokenizer wrapper might just return list of ids or [[ids, weights]]
                try:
                    res = tokenizer_obj.tokenize_with_weights(prompt)
                    input_ids = []
                    for t_list in res:
                        for t, _ in t_list:
                            input_ids.append(t)
                except Exception:
                    input_ids = []
        else:
            input_ids = []
            
        # Ignore sot/eot and pad tokens if possible, roughly assuming extreme bounds
        valid_ids = [i for i in input_ids if i > 0 and i < token_embeds.shape[0] and i not in (49406, 49407)]
        
        if not valid_ids:
            # Fallback to random all
            words = [clean_word(w) for w in vocab.keys()]
            return list(set(w for w in words if w))
            
        valid_ids_tensor = torch.tensor(valid_ids, dtype=torch.long, device=token_embeds.device)
        prompt_embeds = token_embeds[valid_ids_tensor]
        prompt_avg = prompt_embeds.mean(dim=0, keepdim=True)
        
        # Calculate cosine similarity with all tokens
        similarity = F.cosine_similarity(prompt_avg, token_embeds, dim=1)
        
        # We need a large enough top_k to account for subwords and invalid tokens being filtered out
        search_k = min(top_k * 10, token_embeds.shape[0])
        top_indices = torch.topk(similarity, search_k).indices.tolist()
        
        id_to_token = {v: k for k, v in vocab.items()}
        
        results = []
        seen = set()
        for idx in top_indices:
            sim = similarity[idx].item()
            if sim < threshold:
                break # Since they are sorted, we can stop early
                
            token = id_to_token.get(idx)
            if token:
                cw = clean_word(token)
                if cw and cw not in seen:
                    if pos_filter != "any":
                        pos_tag = nltk.pos_tag([cw])[0][1]
                        category = get_pos_category(pos_tag)
                        if category != pos_filter:
                            continue
                    seen.add(cw)
                    results.append(cw)
                    if len(results) >= top_k:
                        break
        return results
    except Exception as e:
        print(f"[Random Keyword Enhancer] Semantic search failed: {e}. Falling back to random vocab.")
        words = [clean_word(w) for w in vocab.keys()]
        return list(set(w for w in words if w))

class RandomKeywordAppender:
    CATEGORY = "utils/prompt"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("enhanced_prompt",)
    DESCRIPTION = "Appends random keywords from keywords.json or semantically samples from CLIP vocab to increase generation variety."

    @classmethod
    def INPUT_TYPES(cls):
        keywords_data = load_keywords()
        categories = ["all", "clip_vocab"] + list(keywords_data.keys())
        return {
            "required": {
                "prompt": ("STRING", {"forceInput": True}),
                "category": (categories, {"default": "clip_vocab"}),
                "num_keywords": ("INT", {"default": 3, "min": 1, "max": 20}),
                "semantic_search": ("BOOLEAN", {"default": True, "label_on": "enabled", "label_off": "disabled", "tooltip": "If enabled, finds words semantically related to the prompt. If disabled, picks purely random words from the vocabulary."}),
                "similarity_threshold": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "Minimum cosine similarity score. If greater than -1.0, only words with at least this similarity will be included."}),
                "top_k_pool": ("INT", {"default": 100, "min": 10, "max": 1000, "step": 10, "tooltip": "When using clip_vocab, samples from the closest K semantically related words."}),
                "pos_filter": (["any", "noun", "verb", "adjective", "adverb"], {"default": "any", "tooltip": "Filter the sampled words by part of speech using NLTK."}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
            "optional": {
                "clip": ("CLIP",),
            }
        }
    
    def run(self, prompt, category, num_keywords, semantic_search, similarity_threshold, top_k_pool, pos_filter, seed, clip=None):
        keywords_data = load_keywords()
        
        pool = []
        if category == "clip_vocab":
            if clip is not None:
                pool = get_semantic_clip_vocab(clip, prompt, top_k=top_k_pool, pos_filter=pos_filter, semantic_search=semantic_search, threshold=similarity_threshold)
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
                pool.extend(get_semantic_clip_vocab(clip, prompt, top_k=500, pos_filter=pos_filter, semantic_search=semantic_search, threshold=similarity_threshold)) # Larger pool for 'all'
            else:
                try:
                    clip_vocab_path = os.path.join(NODE_DIR, "clip_vocab.json")
                    with open(clip_vocab_path, "r", encoding="utf-8") as f:
                        pool.extend(json.load(f))
                except Exception:
                    pass
        else:
            pool = keywords_data.get(category, [])
            
        if pos_filter != "any" and category != "clip_vocab":
            lazy_load_nltk()
            filtered_pool = []
            for w in pool:
                ptag = nltk.pos_tag([w])[0][1]
                if get_pos_category(ptag) == pos_filter:
                    filtered_pool.append(w)
            pool = filtered_pool
            
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
