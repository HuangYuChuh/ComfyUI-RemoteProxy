# ComfyUI-RemoteProxy

A ComfyUI proxy node that acts as a bridge to forward image generation tasks to a remote ComfyUI server. This is an ideal solution for scenarios where local GPU computing power is insufficient and you want to leverage a more powerful remote GPU server seamlessly within your local workflow.

## Installation

1. Place the `ComfyUI-RemoteProxy` directory into your ComfyUI's `custom_nodes/` folder.
2. Install the required Python dependencies:
   ```bash
   pip install websocket-client
   ```
3. Restart ComfyUI.

## Usage Guide

### Basic Usage (Using Built-in Templates)

1. Locate the node in the ComfyUI node menu under **Remote → Remote ComfyUI Executor**.
2. Enter the address of your remote ComfyUI server (e.g., `http://192.168.1.100:8188`).
3. Select the `default_txt2img` template from the dropdown menu.
4. Fill in the desired parameters such as prompts, width, and height.
5. Execute the queue.

### Using Custom Workflows

1. Design your desired workflow over on the remote ComfyUI instance.
2. Save it by clicking **File → Export (API)** to download the workflow JSON.
3. In your local ComfyUI, select the `custom` template on the `Remote ComfyUI Executor` node.
4. Paste the exported JSON content into the `custom_workflow` text box.
5. In your JSON text, use the following placeholder syntax to denote parameters that should be dynamically replaced during execution:
   - `{{positive_prompt}}` - Positive prompt
   - `{{negative_prompt}}` - Negative prompt
   - `{{seed}}` - Random seed
   - `{{width}}` / `{{height}}` - Image resolution dimensions
   - `{{input_image}}` - The filename of the uploaded input image (for img2img workflows)

### Creating Custom Built-in Templates

You can create your own reusable templates by placing any valid ComfyUI API workflow JSON file into the `workflows/` directory. It will automatically be detected and become selectable from the node's template dropdown menu upon restart.

## Node Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| server_url | STRING | The URL of the remote ComfyUI server. |
| template | COMBO | The workflow template to execute. |
| positive_prompt | STRING | The positive text prompt. |
| negative_prompt | STRING | The negative text prompt. |
| seed | INT | Random seed for generation. |
| width | INT | Image width in pixels. |
| height | INT | Image height in pixels. |
| timeout | INT | Execution timeout in seconds (default: 300). |
| custom_workflow | STRING | Custom workflow JSON (used when template is set to 'custom'). |
| input_images | IMAGE | Input images (Optional, used for img2img pipelines). |

## Important Notes

- Ensure the remote ComfyUI server is running and accessible from your local network.
- The `default_txt2img` template defaults to using the `v1-5-pruned-emaonly.safetensors` model. Please modify the template or use a custom JSON if you need to use a different checkpoint.
- During img2img operations, input images are automatically uploaded to the remote server's `input` directory prior to execution.
