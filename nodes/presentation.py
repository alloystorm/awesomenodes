"""Presentation node.

Displays a batch of images in a full-screen presentation grid and optionally
saves them to the output directory.
"""

import os
import json
import shutil
import random

from PIL import Image
import numpy as np
from aiohttp import web
from server import PromptServer
import folder_paths


class PresentationNode:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.temp_dir = folder_paths.get_temp_directory()
        self.prefix_append = "_temp_" + ''.join(random.choice("abcdefghijklmnopqrstupvxyz") for x in range(5))
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "The images to present."}),
                "layout": (["1x1", "2x1", "2x2", "3x3"], {"default": "1x1"}),
                "save_mode": (["auto", "manual"], {"default": "manual"}),
            },
            "hidden": {
                "prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "present_images"
    OUTPUT_NODE = True
    CATEGORY = "image"
    DESCRIPTION = "Displays images in a full-screen presentation grid and optionally saves them."

    def present_images(self, images, layout="1x1", save_mode="manual", prompt=None, extra_pnginfo=None):
        results = list()

        # Determine target directory and type based on save_mode
        if save_mode == "auto":
            target_dir = self.output_dir
            target_type = "output"
            filename_prefix = "ComfyUI"
        else:
            target_dir = self.temp_dir
            target_type = "temp"
            filename_prefix = self.prefix_append

        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(filename_prefix, target_dir, images[0].shape[1], images[0].shape[0])

        for (batch_number, image) in enumerate(images):
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            metadata = None
            try:
                import comfy.args as args
                if not args.args.disable_metadata:
                    from PIL.PngImagePlugin import PngInfo
                    metadata = PngInfo()
                    if prompt is not None:
                        metadata.add_text("prompt", json.dumps(prompt))
                    if extra_pnginfo is not None:
                        for x in extra_pnginfo:
                            metadata.add_text(x, json.dumps(extra_pnginfo[x]))
            except ImportError:
                pass

            filename_with_batch_num = filename.replace("%batch_num%", str(batch_number))
            file = f"{filename_with_batch_num}_{counter:05}_.png"
            filepath = os.path.join(full_output_folder, file)
            img.save(filepath, pnginfo=metadata, compress_level=self.compress_level)

            results.append({
                "filename": file,
                "subfolder": subfolder,
                "type": target_type
            })
            counter += 1

        return {"ui": {"images": results}}


routes = PromptServer.instance.routes


@routes.post("/presentation_node/save")
async def save_presentation_image(request):
    data = await request.json()
    filename = data.get("filename")
    subfolder = data.get("subfolder", "")
    type = data.get("type", "temp")

    if not filename:
        return web.json_response({"error": "No filename provided"}, status=400)

    temp_dir = folder_paths.get_directory_by_type(type)
    if temp_dir is None:
        return web.json_response({"error": "Invalid type"}, status=400)

    source_path = os.path.join(temp_dir, subfolder, filename)
    if not os.path.exists(source_path):
        return web.json_response({"error": "File not found"}, status=404)

    output_dir = folder_paths.get_output_directory()

    # Generate a new unique filename in output_dir
    full_output_folder, out_filename, counter, out_subfolder, _ = folder_paths.get_save_image_path("ComfyUI", output_dir)
    dest_file = f"{out_filename}_{counter:05}_.png"
    dest_path = os.path.join(full_output_folder, dest_file)

    try:
        shutil.copy2(source_path, dest_path)
        return web.json_response({"ok": True, "saved_to": dest_file})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


NODE_CLASS_MAPPINGS = {"PresentationNode": PresentationNode}
NODE_DISPLAY_NAME_MAPPINGS = {"PresentationNode": "Presentation Image Saver"}
