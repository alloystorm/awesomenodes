"""ComfyUI node pack: Prompt Manager + Presentation.

Aggregates each node's NODE_CLASS_MAPPINGS from nodes/ so they can be
developed as separate modules but ship as a single custom_nodes package.
"""

from .nodes import prompt_manager, presentation

NODE_CLASS_MAPPINGS = {
    **prompt_manager.NODE_CLASS_MAPPINGS,
    **presentation.NODE_CLASS_MAPPINGS,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    **prompt_manager.NODE_DISPLAY_NAME_MAPPINGS,
    **presentation.NODE_DISPLAY_NAME_MAPPINGS,
}
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
