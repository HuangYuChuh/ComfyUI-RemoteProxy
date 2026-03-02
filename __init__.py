"""
ComfyUI-RemoteProxy: 远程 ComfyUI 代理节点。

将图片生成任务转发到远程 ComfyUI 服务器执行。
"""
from pathlib import Path
import importlib.util
import sys

# Initialize mappings
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# Auto-load all nodes from nodes/ directory
nodes_dir = Path(__file__).parent / "nodes"

if nodes_dir.exists():
    for py_file in sorted(nodes_dir.glob("*.py")):
        if py_file.stem.startswith("_"):
            continue
        
        try:
            # Load module
            module_name = f"ComfyUI-RemoteProxy.nodes.{py_file.stem}"
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            sys.modules[py_file.stem] = module
            spec.loader.exec_module(module)
            
            # Register node mappings
            if hasattr(module, "NODE_CLASS_MAPPINGS"):
                NODE_CLASS_MAPPINGS.update(module.NODE_CLASS_MAPPINGS)
            
            if hasattr(module, "NODE_DISPLAY_NAME_MAPPINGS"):
                NODE_DISPLAY_NAME_MAPPINGS.update(module.NODE_DISPLAY_NAME_MAPPINGS)
                
        except Exception as e:
            print(f"[RemoteProxy] Failed to load {py_file.stem}: {e}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
