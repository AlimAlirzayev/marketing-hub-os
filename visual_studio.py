"""Xalq Insurance Digital OS Visual Generation Engine.

Uses Google's state-of-the-art Imagen 3 model via Vertex AI to
generate high-quality images from text prompts.
"""

import os
import time
from pathlib import Path

from google import genai
from google.genai import types

_OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "visuals"

def generate_image(prompt: str, style: str = "photorealistic") -> str:
    """Generates an image using Imagen 3 via Gemini API and saves it."""
    
    API_KEY = os.getenv("GEMINI_API_KEY")
    if not API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in the environment.")

    client = genai.Client(api_key=API_KEY)

    full_prompt = f"{prompt}, {style}, high resolution, professional quality"
    
    result = client.models.generate_images(
        model='imagen-3.0-generate-001',
        prompt=full_prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            output_mime_type="image/png"
        )
    )
    
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _OUTPUT_DIR / f"visual_{int(time.time())}.png"
    
    for generated_image in result.generated_images:
        with open(file_path, "wb") as f:
            f.write(generated_image.image.image_bytes)
        break
    
    return str(file_path)
