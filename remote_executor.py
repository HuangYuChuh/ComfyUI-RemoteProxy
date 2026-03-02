"""
RemoteComfyUIClient - 与远程 ComfyUI 实例通信的核心模块。

通过 HTTP API 提交 workflow、通过 WebSocket 监听执行进度、
通过 /history 和 /view 端点获取生成的图片。
"""

import io
import json
import logging
import struct
import time
import uuid
import urllib.request
import urllib.parse
from typing import Optional

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)


class RemoteComfyUIError(Exception):
    """远程 ComfyUI 交互错误的基类。"""
    pass


class ConnectionError(RemoteComfyUIError):
    """连接远程服务器失败。"""
    pass


class ExecutionError(RemoteComfyUIError):
    """远程 workflow 执行失败。"""
    pass


class TimeoutError(RemoteComfyUIError):
    """远程执行超时。"""
    pass


class RemoteComfyUIClient:
    """封装与远程 ComfyUI 实例的所有 API 交互。"""

    def __init__(self, server_url: str, timeout: int = 300):
        """
        Args:
            server_url: 远程 ComfyUI 地址，如 "http://192.168.1.100:8188"
            timeout: 执行超时秒数
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

        # 解析出 host:port 用于 WebSocket 连接
        parsed = urllib.parse.urlparse(self.server_url)
        self.server_address = parsed.netloc  # e.g., "192.168.1.100:8188"
        self.scheme = parsed.scheme  # "http" or "https"
        self.ws_scheme = "wss" if self.scheme == "https" else "ws"

    def _http_get(self, path: str, params: Optional[dict] = None, max_retries: int = 3) -> bytes:
        """发起 HTTP GET 请求（包含重试机制）。"""
        url = f"{self.server_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
            
        last_error = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=30) as response:
                    return response.read()
            except Exception as e:
                last_error = e
                logger.warning(f"HTTP GET 请求失败 (尝试 {attempt + 1}/{max_retries}) {url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避: 1s, 2s...
                    
        if isinstance(last_error, urllib.error.URLError):
            raise ConnectionError(f"无法连接到远程服务器 {self.server_url}: {last_error}")
        else:
            raise RemoteComfyUIError(f"HTTP GET 请求最终失败 {url}: {last_error}")

    def _http_post_json(self, path: str, data: dict) -> dict:
        """发起 HTTP POST JSON 请求。"""
        url = f"{self.server_url}{path}"
        try:
            payload = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            # 尝试解析 ComfyUI 专属错误 JSON
            try:
                error_data = json.loads(error_body)
                if "error" in error_data or "node_errors" in error_data:
                    err_msg = ""
                    if "error" in error_data:
                        err_msg += f"验证失败: {error_data['error'].get('message', str(error_data['error']))}\n"
                    if "node_errors" in error_data and error_data["node_errors"]:
                        err_msg += f"节点配置错误: {json.dumps(error_data['node_errors'], ensure_ascii=False)}"
                    if err_msg:
                        raise ExecutionError(f"远程服务器拒绝了 workflow:\n{err_msg}")
            except json.JSONDecodeError:
                pass
            raise ConnectionError(f"HTTP {e.code} | {error_body}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"无法连接到远程服务器 {self.server_url}: {e}")
        except json.JSONDecodeError as e:
            raise RemoteComfyUIError(f"解析远程响应失败: {e}")
        except Exception as e:
            raise RemoteComfyUIError(f"HTTP POST 请求失败 {url}: {e}")

    def _http_post_multipart(self, path: str, fields: dict, file_field: str,
                             filename: str, file_data: bytes,
                             content_type: str = "image/png") -> dict:
        """发起 HTTP POST multipart/form-data 请求（用于上传图片）。"""
        import mimetypes
        boundary = uuid.uuid4().hex
        body = b""

        # 添加普通字段
        for key, value in fields.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
            body += f"{value}\r\n".encode()

        # 添加文件字段
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode()
        body += f"Content-Type: {content_type}\r\n\r\n".encode()
        body += file_data
        body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()

        url = f"{self.server_url}{path}"
        max_retries = 3
        last_error = None
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url, data=body,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
                )
                with urllib.request.urlopen(req, timeout=120) as response:
                    return json.loads(response.read())
            except Exception as e:
                last_error = e
                error_msg = str(e)
                logger.warning(f"上传失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避: 1s, 2s
                    continue
        raise RemoteComfyUIError(f"上传文件失败 ({max_retries} 次重试后): {last_error}")

    def check_connection(self) -> bool:
        """检查远程服务器是否可达。"""
        try:
            data = self._http_get("/system_stats")
            stats = json.loads(data)
            logger.info(f"远程服务器连接成功: ComfyUI {stats.get('system', {}).get('comfyui_version', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"远程服务器连接失败: {e}")
            return False

    def queue_prompt(self, workflow: dict) -> str:
        """
        提交 workflow 到远程服务器执行。

        Args:
            workflow: ComfyUI API 格式的 workflow JSON

        Returns:
            prompt_id: 远程任务的唯一标识
        """
        prompt_id = str(uuid.uuid4())
        payload = {
            "prompt": workflow,
            "client_id": self.client_id,
            "prompt_id": prompt_id,
        }
        result = self._http_post_json("/prompt", payload)

        if "error" in result:
            raise ExecutionError(f"远程 workflow 验证失败: {result['error']}")
        if "node_errors" in result and result["node_errors"]:
            raise ExecutionError(f"远程节点错误: {json.dumps(result['node_errors'], ensure_ascii=False)}")

        logger.info(f"已提交远程任务: prompt_id={prompt_id}")
        return prompt_id

    def wait_for_completion(self, prompt_id: str) -> None:
        """
        通过 WebSocket 等待远程 workflow 执行完成。

        Args:
            prompt_id: 远程任务 ID
        """
        try:
            import websocket
        except ImportError:
            raise RemoteComfyUIError(
                "需要安装 websocket-client: pip install websocket-client"
            )

        ws_url = f"{self.ws_scheme}://{self.server_address}/ws?clientId={self.client_id}"
        logger.info(f"连接远程 WebSocket: {ws_url}")

        ws = None
        try:
            ws = websocket.WebSocket()
            ws.settimeout(self.timeout)
            ws.connect(ws_url)

            start_time = time.time()
            while True:
                # 检查超时
                elapsed = time.time() - start_time
                if elapsed > self.timeout:
                    raise TimeoutError(
                        f"远程执行超时 ({self.timeout}s)。"
                        f"请检查远程服务器状态或增加 timeout 值。"
                    )

                try:
                    out = ws.recv()
                except websocket.WebSocketTimeoutException:
                    raise TimeoutError(f"WebSocket 接收超时 ({self.timeout}s)")

                if isinstance(out, str):
                    message = json.loads(out)
                    msg_type = message.get("type", "")

                    if msg_type == "executing":
                        data = message.get("data", {})
                        # node=None 且 prompt_id 匹配 → 执行完成
                        if data.get("node") is None and data.get("prompt_id") == prompt_id:
                            logger.info(f"远程任务完成: prompt_id={prompt_id}")
                            break

                    elif msg_type == "execution_error":
                        data = message.get("data", {})
                        if data.get("prompt_id") == prompt_id:
                            error_msg = data.get("exception_message", "未知执行错误")
                            raise ExecutionError(f"远程执行失败: {error_msg}")

                    elif msg_type == "progress":
                        data = message.get("data", {})
                        value = data.get("value", 0)
                        max_val = data.get("max", 0)
                        if max_val > 0:
                            pct = int(value / max_val * 100)
                            logger.info(f"远程执行进度: {pct}% ({value}/{max_val})")

                # 二进制数据（预览图）直接跳过
                # else: continue

        except (ConnectionError, ExecutionError, TimeoutError):
            raise
        except Exception as e:
            raise RemoteComfyUIError(f"WebSocket 通信错误: {e}")
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def get_history(self, prompt_id: str) -> dict:
        """获取指定 prompt 的执行历史。"""
        data = self._http_get(f"/history/{prompt_id}")
        history = json.loads(data)
        if prompt_id not in history:
            raise RemoteComfyUIError(f"远程历史记录中未找到 prompt_id={prompt_id}")
        return history[prompt_id]

    def get_image_data(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """从远程服务器下载图片。"""
        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type,
        }
        return self._http_get("/view", params)

    def get_output_images(self, prompt_id: str) -> list[torch.Tensor]:
        """
        从远程执行历史中提取所有输出图片，转换为 ComfyUI IMAGE tensor。

        Returns:
            list[Tensor]: 每个元素为 [B, H, W, C] 格式的图片 tensor
        """
        history = self.get_history(prompt_id)
        outputs = history.get("outputs", {})

        all_images = []
        for node_id, node_output in outputs.items():
            if "images" not in node_output:
                continue
            for img_info in node_output["images"]:
                filename = img_info["filename"]
                subfolder = img_info.get("subfolder", "")
                folder_type = img_info.get("type", "output")

                image_data = self.get_image_data(filename, subfolder, folder_type)
                tensor = self._bytes_to_tensor(image_data)
                all_images.append(tensor)

        if not all_images:
            raise RemoteComfyUIError("远程执行完成但未产生任何输出图片")

        return all_images

    def upload_image(self, image_tensor: torch.Tensor,
                     filename: str = "remote_input.png") -> str:
        """
        将本地 IMAGE tensor 上传到远程服务器。

        Args:
            image_tensor: [B, H, W, C] 格式的图片 tensor
            filename: 上传后的文件名

        Returns:
            上传后的文件名（可能被远程修改）
        """
        # 取 batch 中第一张图
        if image_tensor.dim() == 4:
            img = image_tensor[0]
        else:
            img = image_tensor

        # tensor → PIL → bytes
        np_img = (img.cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
        pil_img = Image.fromarray(np_img)

        buffer = io.BytesIO()
        pil_img.save(buffer, format="PNG")
        png_bytes = buffer.getvalue()

        result = self._http_post_multipart(
            "/upload/image",
            fields={"overwrite": "true", "type": "input"},
            file_field="image",
            filename=filename,
            file_data=png_bytes,
        )

        uploaded_name = result.get("name", filename)
        logger.info(f"图片已上传到远程服务器: {uploaded_name}")
        return uploaded_name

    def execute_workflow(self, workflow: dict) -> list[torch.Tensor]:
        """
        完整执行流程：提交 → 等待 → 获取结果。

        Args:
            workflow: ComfyUI API 格式的 workflow JSON

        Returns:
            list[Tensor]: 生成的图片列表
        """
        prompt_id = self.queue_prompt(workflow)
        self.wait_for_completion(prompt_id)
        return self.get_output_images(prompt_id)

    @staticmethod
    def _bytes_to_tensor(image_bytes: bytes) -> torch.Tensor:
        """将图片二进制数据转为 ComfyUI IMAGE tensor [1, H, W, C]。"""
        pil_image = Image.open(io.BytesIO(image_bytes))
        pil_image = pil_image.convert("RGB")
        np_image = np.array(pil_image).astype(np.float32) / 255.0
        tensor = torch.from_numpy(np_image).unsqueeze(0)  # [1, H, W, C]
        return tensor


def apply_template_params(workflow: dict, params: dict) -> dict:
    """
    将参数替换到 workflow 模板中。
    模板中使用 {{param_name}} 作为占位符。

    Args:
        workflow: workflow JSON dict
        params: 要替换的参数

    Returns:
        替换后的 workflow dict
    """
    workflow_str = json.dumps(workflow, ensure_ascii=False)
    for key, value in params.items():
        placeholder = "{{" + key + "}}"
        # 对于字符串值，直接替换（保留 JSON 转义）
        if isinstance(value, str):
            workflow_str = workflow_str.replace(placeholder, value)
        else:
            # 对于数值类型，需要处理 JSON 中引号包裹的情况
            # 如 "seed": "{{seed}}" → "seed": 12345
            quoted_placeholder = f'"{placeholder}"'
            json_value = json.dumps(value)
            if quoted_placeholder in workflow_str:
                workflow_str = workflow_str.replace(quoted_placeholder, json_value)
            else:
                workflow_str = workflow_str.replace(placeholder, str(value))

    return json.loads(workflow_str)
