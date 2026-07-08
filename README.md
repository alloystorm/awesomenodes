# ComfyUI Prompt Manager

A small node pack for ComfyUI:

- **Prompt Manager** — template/history-driven prompt supplier
- **Presentation Image Saver** — full-screen image grid viewer + save

Both nodes ship from this one repo/folder so ComfyUI only has to load a
single custom_nodes package.

## Node: `Prompt Manager` (utils/prompt)

**Outputs:** `prompt` (STRING), `enhancer_instruction` (STRING)

Wire `prompt` into your CLIP Text Encode node to drive it from one place.

### Template placeholders

The prompt may contain placeholders:

- `{character}`, `{scene}`, `{environment}`, `{genre}`, `{style}` — replaced
  with a pick from the corresponding list in `templates.json` (in this node's
  folder). Add your own aspects by adding keys to that file; any `{key}`
  matching a key is resolved. Template entries may themselves contain
  placeholders (resolved up to 5 levels). Click the node's **Edit Templates**
  button (also available via right-click) to open a spreadsheet-style
  table — one column per category, one row per item index: tick a checkbox
  to enable/disable an item, edit its text directly in its cell, drag the ⠿
  handle to reorder within a column, or add/delete whole categories/items.
- `{option a|option b|option c}` — inline options, one is picked.
- `{page}` — replaced with the current page counter (see **Pages** below).
- Unknown placeholders are left untouched.

Example:

```
{genre}, {character} in {scene}, {environment}, {highly detailed|minimalist}
```

### Shuffling

Picks are driven by the **`shuffle_seed`** widget, independent of any
generation seed elsewhere in the workflow. For each placeholder, the picked
item's index is `shuffle_seed % item count` (counting only enabled items) —
so item *order* controls the sequence (drag to reorder in the editor):

- `shuffle_seed` → *increment*: steps through each aspect's list in order,
  wrapping around — a predictable, repeatable sequence across runs.
- `shuffle_seed` → *randomize*: jumps to an arbitrary index each run.
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
an entry restores the prompt, pages, shuffle seed and enhancer into the node.

### Enhancers

The **`enhancer`** dropdown selects a saved system/enhancer instruction (e.g.
a prompt-rewriting instruction for an LLM text encoder) whose text is emitted
as the `enhancer_instruction` output — wire it together with `prompt` into a
"Generate Text" node to drive prompt enhancement. Manage the saved list (add,
edit, delete) via the node's **Edit Enhancers** button (also available via
right-click); entries are stored in `enhancers.json` (seeded with a "Comic
Page Art Director" example). Selecting `None` outputs an empty string.

Since `Generate Text`'s single `prompt` input expects the full chat-formatted
text, combine the two outputs into the model's chat template yourself, e.g.
for Qwen-style models via a `StringConcatenate`/`StringFormat` node chain
into:

```
<|im_start|>system
{enhancer_instruction}<|im_end|>
<|im_start|>user
{prompt}<|im_end|>
<|im_start|>assistant
```

### API

- `GET /prompt_manager/history` — list entries
- `POST /prompt_manager/history/delete` — body `{"timestamp": <ts>}` deletes
  one entry; `{}` clears all
- `GET` / `POST /prompt_manager/templates` — read/replace the aspect lists
  (`{aspect: [{"text": string, "enabled": bool}, ...]}`)
- `GET` / `POST /prompt_manager/enhancers` — read/replace the saved enhancer
  instructions (`{name: instruction_text}`)

## Node: `Presentation Image Saver` (image)

**Input:** `images` (IMAGE batch), `layout` (1x1/2x1/2x2/3x3),
`save_mode` (auto/manual), `prompt_text` (STRING, optional)

Adds a **Present (Full Screen)** button to the node that opens a full-screen
grid showing the images as they arrive. In `manual` save mode, each image
gets a **Save** button to copy it from the temp directory into the output
directory; in `auto` mode, images are saved to the output directory
immediately and marked as already saved.

If `prompt_text` is non-empty, it's saved as a `.txt` file next to each
image using the same filename (e.g. `ComfyUI_00001_.png` +
`ComfyUI_00001_.txt`) — written at save time, so in `manual` mode this
happens when you click **Save**, not when the image first appears. Wire
Prompt Manager's `prompt` output (or any STRING) into it to keep the actual
prompt alongside each saved image.

### API

- `POST /presentation_node/save` — body
  `{"filename", "subfolder", "type", "prompt_text"}`, copies a temp image
  into the output directory (and its `.txt` companion, if `prompt_text` is
  set)
