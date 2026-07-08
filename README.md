# ComfyUI Prompt Manager

A small node pack for ComfyUI:

- **Prompt Manager** — template/history-driven prompt supplier
- **Presentation Image Saver** — full-screen image grid viewer + save

Both nodes ship from this one repo/folder so ComfyUI only has to load a
single custom_nodes package.

## Node: `Prompt Manager` (utils/prompt)

**Output:** `prompt` (STRING)

Wire `prompt` into your CLIP Text Encode node to drive it from one place.

### Template placeholders

The prompt may contain placeholders:

- `{character}`, `{scene}`, `{environment}`, `{genre}`, `{style}` — replaced
  with a pick from the corresponding list in `templates.json` (in this node's
  folder). Add your own aspects by adding keys to that file; any `{key}`
  matching a key is resolved. Template entries may themselves contain
  placeholders (resolved up to 5 levels). Each entry can be disabled without
  deleting it — use the node's right-click **Edit Templates** dialog to
  toggle/add/remove entries per category.
- `{option a|option b|option c}` — inline options, one is picked.
- `{page}` — replaced with the current page counter (see **Pages** below).
- Unknown placeholders are left untouched.

Example:

```
{genre}, {character} in {scene}, {environment}, {highly detailed|minimalist}
```

### Shuffling

Picks are driven by the **`shuffle_seed`** widget, independent of any
generation seed elsewhere in the workflow:

- `shuffle_seed` → *randomize*: aspects reshuffle on every run.
- `shuffle_seed` → *fixed*: the current picks are kept exactly.

### Pages

Set **`pages`** to N to keep the same resolved template picks for N
consecutive runs (e.g. for a multi-page/panel sequence), using `{page}` in
the prompt to print the current counter (1..N). After N runs the counter
resets and picks reshuffle from `shuffle_seed`. Enable **`debug_print`** to
print the final resolved prompt to the console each run.

### History

Every executed run is saved to `history.json` (last 200, deduped, newest
first). The **`history`** dropdown on the node lists past prompts; selecting
an entry restores the prompt, pages and shuffle seed into the node.

### API

- `GET /prompt_manager/history` — list entries
- `POST /prompt_manager/history/delete` — body `{"timestamp": <ts>}` deletes
  one entry; `{}` clears all
- `GET` / `POST /prompt_manager/templates` — read/replace the aspect lists
  (`{aspect: [{"text": string, "enabled": bool}, ...]}`)

## Node: `Presentation Image Saver` (image)

**Input:** `images` (IMAGE batch), `layout` (1x1/2x1/2x2/3x3),
`save_mode` (auto/manual)

Adds a **Present (Full Screen)** button to the node that opens a full-screen
grid showing the images as they arrive. In `manual` save mode, each image
gets a **Save** button to copy it from the temp directory into the output
directory; in `auto` mode, images are saved to the output directory
immediately and marked as already saved.

### API

- `POST /presentation_node/save` — body
  `{"filename", "subfolder", "type"}`, copies a temp image into the output
  directory
