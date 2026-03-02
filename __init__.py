"""
ComfyUI-RemoteProxy: 远程 ComfyUI 代理节点。

将图片生成任务转发到远程 ComfyUI 服务器执行。
"""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
