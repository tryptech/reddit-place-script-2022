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
    corrected_image_numpy = ColorMapper.correct_image(image, ColorMapper.FULL_COLOR_MAP)
    total_time += time.time() - current_time

    current_time = time.time()
    corrected_image_base = np.empty_like(image)
    for i in range(image.shape[0]):
        for j in range(image.shape[1]):
            corrected_image_base[i][j][:3] = closest_color(image[i][j],
                                                            ColorMapper.palette_to_rgb(ColorMapper.FULL_COLOR_MAP))
            corrected_image_base[i][j][3] = image[i][j][3]
    total_time_old += time.time() - current_time

    equal = np.array_equal(corrected_image_numpy, corrected_image_base)

    print("Corrected {} image. Numpy {} Old".format(
        name, '==' if equal else '!='
    ))

    if not equal:
        diff = np.argwhere((corrected_image_numpy - corrected_image_base).any(axis=-1))
        print(diff)
        Image.fromarray(corrected_image_numpy, 'RGBA').save(f"images/{name}_numpy.png")
        Image.fromarray(corrected_image_base, 'RGBA').save(f"images/{name}_base.png")

print(f"Average image correction time")
print(f"numpy: {total_time / len(templates)}")
print(f"base: {total_time_old / len(templates)}")
