import sys
import json
import requests
from PIL import Image
from io import BytesIO
import numpy as np

from src.mappings import ColorMapper


config = json.load(open(sys.argv[1]))

urls = config['template_urls']

templates = []
for url in urls:
    sources = requests.get(url).json()
    templates += sources['templates']

for template in templates:
    name = template['name']
    url = template['sources'][0]

    if name != 'Anny Star':
        continue

    response = requests.get(url)
    image = Image.open(BytesIO(response.content))
    image = image.convert('RGBA')
    image.save(f"images/{name}.png")
    image = np.array(image)

    a_channel = image[...,-1]
    corrected_image = ColorMapper.correct_color(image[...,:-1])
    # corrected_image = np.concatenate([
    #     corrected_image,
    #     a_channel[...,np.newaxis]
    # ], axis=-1)

    Image.fromarray(corrected_image, 'RGB').save(f"images/{name}_corrected.png")
