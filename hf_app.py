import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import spaces
import torch

torch.cuda.is_available = lambda: False   # keep all models on CPU

import gradio as gr
from starlette.routing import Mount
from mfasha.api.main import create_app


@spaces.GPU
def _gpu_probe():
    return "ok"


with gr.Blocks() as demo:
    gr.Markdown("MFASHA API is running. Endpoints are under /mfasha/api/")
    _out = gr.Textbox(visible=False)
    gr.Button("probe", visible=False).click(_gpu_probe, None, _out)

api = create_app()

demo.launch(server_name="0.0.0.0", server_port=7860, prevent_thread_lock=True, ssr_mode=False)

# put the API at the FRONT of the route list, so Gradio's catch-all cannot swallow /mfasha
demo.app.router.routes.insert(0, Mount("/mfasha", app=api))

demo.block_thread()