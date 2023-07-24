import sys
import json
import requests
from PIL import Image
from io import BytesIO
import numpy as np
import time

from src.mappings import ColorMapper
from test.mappings import closest_color

if len(sys.argv) != 2:
    print("Usage: python correct_image.py <config.json>")
    exit(1)

config = json.load(open(sys.argv[1]))

urls = config['template_urls']

templates = []
for url in urls:
    sources = requests.get(url).json()
    templates += sources['templates']

total_time = 0
total_time_old = 0

for template in templates:
    name = template['name']
    url = template['sources'][0]

    response = requests.get(url)
    image = Image.open(BytesIO(response.content))
    image = image.convert('RGBA')
    image.save(f"images/{name}.png")
    image = np.array(image)

    current_time = time.time()
    corrected_image = ColorMapper.correct_image(image)
    total_time += time.time() - current_time

    current_time = time.time()
    for i in range(image.shape[0]):
        for j in range(image.shape[1]):
            corrected_image[i][j][:3] = closest_color(image[i][j], ColorMapper.COLORS)
            corrected_image[i][j][3] = image[i][j][3]
    total_time_old += time.time() - current_time

    print(f"Corrected {name} image with numpy")

    Image.fromarray(corrected_image, 'RGBA').save(f"images/{name}_corrected_numpy.png")

print(f"Average image correction time")
print(f"numpy: {total_time / len(templates)}")
print(f"old: {total_time_old / len(templates)}")
