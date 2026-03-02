# ComfyUI-RemoteProxy

将图片生成任务转发到远程 ComfyUI 服务器执行的代理节点。适用于本地 GPU 算力不足、需要利用远程 GPU 服务器的场景。

## 安装

1. 将 `ComfyUI-RemoteProxy` 目录放入 ComfyUI 的 `custom_nodes/` 目录
2. 安装依赖：
   ```bash
   pip install websocket-client
   ```
3. 重启 ComfyUI

## 使用方法

### 基础用法（使用内置模板）

1. 在节点菜单中找到 **Remote → Remote ComfyUI Executor**
2. 输入远程服务器地址（如 `http://192.168.1.100:8188`）
3. 选择 `default_txt2img` 模板
4. 填写 prompt、尺寸等参数
5. 执行

### 使用自定义 Workflow

1. 在远程 ComfyUI 中设计好 workflow
2. **File → Export (API)** 导出 workflow JSON
3. 在节点中选择 `custom` 模板
4. 将导出的 JSON 粘贴到 `custom_workflow` 输入框
5. 在 JSON 中使用占位符标记可替换参数：
   - `{{positive_prompt}}` - 正向提示词
   - `{{negative_prompt}}` - 负向提示词
   - `{{seed}}` - 随机种子
   - `{{width}}` / `{{height}}` - 图片尺寸
   - `{{input_image}}` - 上传的输入图片文件名

### 创建自定义模板

将 workflow JSON 文件放入 `workflows/` 目录即可自动识别为内置模板选项。

## 节点参数

| 参数 | 类型 | 说明 |
|------|------|------|
| server_url | STRING | 远程 ComfyUI 地址 |
| template | COMBO | workflow 模板选择 |
| positive_prompt | STRING | 正向提示词 |
| negative_prompt | STRING | 负向提示词 |
| seed | INT | 随机种子 |
| width | INT | 图片宽度 |
| height | INT | 图片高度 |
| timeout | INT | 超时秒数 (默认 300) |
| custom_workflow | STRING | 自定义 workflow JSON |
| input_images | IMAGE | 输入图片 (可选，用于 img2img) |

## 注意事项

- 确保远程 ComfyUI 服务器已启动且可访问
- 默认模板使用 `v1-5-pruned-emaonly.safetensors`，请根据实际模型修改模板
- img2img 时图片会自动上传到远程服务器的 input 目录
