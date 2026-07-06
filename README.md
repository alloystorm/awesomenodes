# ComfyUI Prompt Manager

One node that centralizes the prompt and key generation settings for any workflow,
with local prompt history and template-based shuffling.

## Node: `Prompt Manager` (utils/prompt)

**Outputs:** `prompt` (STRING), `negative_prompt` (STRING), `width` (INT), `height` (INT), `seed` (INT)

Wire `prompt`/`negative_prompt` into your CLIP Text Encode nodes, `width`/`height`
into an Empty Latent Image, and `seed` into your sampler — then drive the whole
workflow from this one node.

## Template placeholders

The prompt (and negative prompt) may contain placeholders:

- `{scene}`, `{environment}`, `{genre}`, `{character}` — replaced with a pick from
  the corresponding list in `templates.json` (in this node's folder). Add your own
  aspects by adding keys to that file; any `{key}` matching a key is resolved.
  Template entries may themselves contain placeholders (resolved up to 5 levels).
- `{option a|option b|option c}` — inline options, one is picked.
- Unknown placeholders are left untouched.

Example:

```
{genre}, {character} in {scene}, {environment}, {highly detailed|minimalist}
```

### Shuffling

Picks are driven by the **`shuffle_seed`** widget, independent of the generation
seed:

- `shuffle_seed` → *randomize*: aspects reshuffle on every run (generation seed
  can stay fixed).
- `shuffle_seed` → *fixed*: the current picks are kept exactly.

## History

Every executed run is saved to `history.json` (last 200, deduped). The
**`history`** dropdown on the node lists past prompts (newest first); selecting an
entry restores the prompt, negative prompt, size and seeds into the node.

### API

- `GET /prompt_manager/history` — list entries
- `POST /prompt_manager/history/delete` — body `{"timestamp": <ts>}` deletes one
  entry; `{}` clears all
- `GET` / `POST /prompt_manager/templates` — read/replace the aspect lists
