import sys
import json
import requests
from PIL import Image
from io import BytesIO
import numpy as np

from src.mappings import ColorMapper

if len(sys.argv) != 2:
    print("Usage: python correct_image.py <config.json>")
    exit(1)

config = json.load(open(sys.argv[1]))

urls = config['template_urls']

templates = []
for url in urls:
    sources = requests.get(url).json()
    templates += sources['templates']

for template in templates:
    name = template['name']
    url = template['sources'][0]

    response = requests.get(url)
    image = Image.open(BytesIO(response.content))
    image = image.convert('RGBA')
    image.save(f"images/{name}.png")
    image = np.array(image)

    corrected_image = np.concatenate([
        ColorMapper.correct_image(image[...,:3]),
        image[...,[3]]
    ], axis=-1)

    print(f"Corrected {name} image with numpy")

    Image.fromarray(corrected_image, 'RGBA').save(f"images/{name}_corrected_numpy.png")
