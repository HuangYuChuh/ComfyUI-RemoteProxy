"""
RemoteComfyUIExecutor - 远程 ComfyUI 执行节点。

将 workflow 发送到远程 ComfyUI 服务器执行，返回生成的图片。
支持 workflow 模板参数替换和 img2img 图片上传。
"""

import json
import logging
import os

import torch

from ..remote_executor import (
    RemoteComfyUIClient,
    RemoteComfyUIError,
    apply_template_params,
)

logger = logging.getLogger(__name__)

# 内置 workflow 模板目录
WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows")


def _get_builtin_templates() -> list[str]:
    """获取内置 workflow 模板列表。"""
    templates = ["custom"]  # 始终有 custom 选项
    if os.path.isdir(WORKFLOWS_DIR):
        for f in sorted(os.listdir(WORKFLOWS_DIR)):
            if f.endswith(".json"):
                templates.append(f[:-5])  # 去掉 .json 后缀
    return templates


class RemoteComfyUIExecutor:
    """远程 ComfyUI 执行节点。"""

    CATEGORY = "Remote"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        templates = _get_builtin_templates()
        return {
            "required": {
                "server_url": ("STRING", {
                    "default": "http://127.0.0.1:8188",
                    "tooltip": "远程 ComfyUI 服务器地址",
                }),
                "template": (templates, {
                    "default": templates[1] if len(templates) > 1 else "custom",
                    "tooltip": "选择内置 workflow 模板，或选 'custom' 使用自定义 JSON",
                }),
                "positive_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "正向提示词，替换模板中的 {{positive_prompt}}",
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "负向提示词，替换模板中的 {{negative_prompt}}",
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xFFFFFFFFFFFFFFFF,
                    "tooltip": "随机种子，替换模板中的 {{seed}}",
                }),
                "width": ("INT", {
                    "default": 1024,
                    "min": 64,
                    "max": 8192,
                    "step": 64,
                    "tooltip": "图片宽度，替换模板中的 {{width}}",
                }),
                "height": ("INT", {
                    "default": 1024,
                    "min": 64,
                    "max": 8192,
                    "step": 64,
                    "tooltip": "图片高度，替换模板中的 {{height}}",
                }),
                "timeout": ("INT", {
                    "default": 300,
                    "min": 10,
                    "max": 3600,
                    "tooltip": "执行超时秒数",
                }),
            },
            "optional": {
                "custom_workflow": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "自定义 workflow JSON（仅当 template 选择 'custom' 时使用）",
                }),
                "input_images": ("IMAGE", {
                    "tooltip": "输入图片（用于 img2img，上传到远程服务器）",
                }),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """每次都重新执行（因为远程状态可能变化）。"""
        return float("nan")

    def execute(self, server_url, template, positive_prompt, negative_prompt,
                seed, width, height, timeout, custom_workflow="",
                input_images=None):
        """执行远程 workflow 并返回生成的图片。"""

        # 1. 加载 workflow
        workflow = self._load_workflow(template, custom_workflow)

        # 2. 创建远程客户端
        client = RemoteComfyUIClient(server_url, timeout=timeout)

        # 3. 如果有输入图片，先上传到远程服务器
        uploaded_filename = None
        if input_images is not None:
            uploaded_filename = client.upload_image(input_images)

        # 4. 替换模板参数
        params = {
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt,
            "seed": seed,
            "width": width,
            "height": height,
        }
        if uploaded_filename:
            params["input_image"] = uploaded_filename

        workflow = apply_template_params(workflow, params)

        # 5. 提交并等待执行
        logger.info(f"正在向远程服务器 {server_url} 提交 workflow...")
        images = client.execute_workflow(workflow)

        # 6. 合并所有图片到一个 batch
        if len(images) == 1:
            result = images[0]
        else:
            result = torch.cat(images, dim=0)

        return (result,)

    def _load_workflow(self, template: str, custom_workflow: str) -> dict:
        """加载 workflow JSON。"""
        if template == "custom":
            if not custom_workflow.strip():
                raise RemoteComfyUIError(
                    "选择了 'custom' 模板但未提供自定义 workflow JSON。\n"
                    "请在 custom_workflow 输入框中粘贴 workflow JSON，\n"
                    "或选择一个内置模板。"
                )
            try:
                # 清理尾逗号（JS 风格 JSON 常见问题）
                import re
                cleaned = re.sub(r',\s*([}\]])', r'\1', custom_workflow)
                return json.loads(cleaned)
            except json.JSONDecodeError as e:
                raise RemoteComfyUIError(f"自定义 workflow JSON 解析失败: {e}")

        # 加载内置模板
        template_path = os.path.join(WORKFLOWS_DIR, f"{template}.json")
        if not os.path.isfile(template_path):
            raise RemoteComfyUIError(f"找不到 workflow 模板: {template_path}")

        with open(template_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise RemoteComfyUIError(f"模板 {template} 的 JSON 解析失败: {e}")


# 节点映射（传统注册方式）
NODE_CLASS_MAPPINGS = {
    "RemoteComfyUIExecutor": RemoteComfyUIExecutor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RemoteComfyUIExecutor": "Remote ComfyUI Executor",
}
