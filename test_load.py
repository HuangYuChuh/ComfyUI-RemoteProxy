import sys
import os

# Add custom nodes directory to path to simulate ComfyUI import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import importlib
    ComfyUI_RemoteProxy = importlib.import_module("ComfyUI-RemoteProxy")
    print("SUCCESS: Module loaded")
    print("NODE_CLASS_MAPPINGS:", ComfyUI_RemoteProxy.NODE_CLASS_MAPPINGS)
except Exception as e:
    print("FAILED:", e)
