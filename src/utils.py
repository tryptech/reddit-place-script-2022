import json
import os
import requests
import shutil
from PIL import Image, UnidentifiedImageError
from io import BytesIO
from random import randint

def get_json_data(self, config_path):
    configFilePath = os.path.join(os.getcwd(), config_path)

    if not os.path.exists(configFilePath):
        exit("No config.json file found. Read the README")

    # To not keep file open whole execution time
    f = open(configFilePath)
    json_data = json.load(f)
    f.close()

    return json_data

    # Read the input image.jpg file


def load_api(self):
    res = requests.get("https://template.vtubers.place/api/Template/raw/no-whitelist")
    templates = res.json()["templates"]
    file_path = os.path.join(os.getcwd(), "images")

    # Check if images folder exists, make otherwise
    if os.path.exists(file_path):
        # Delete existing images 
        for filename in os.listdir(file_path):
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
            except Exception as e:
                self.logger.exception('Failed to delete %s. Reason: %s' % (file_path, e))
    else:
        os.mkdir(file_path)
    for template in templates:
        file = os.path.join(file_path,f'{template["name"]}.png')

        response = requests.get(template['sources'][0])
        if response.status_code == 200:
            image_res = requests.get(response.url)
            image = BytesIO(image_res.content)
            image_file = Image.open(image)
            image_file.save(file)
            self.images.append({
                'name': template['name'],
                'path': file,
                'x': template['x'],
                'y': template['y'],
                'width': image_file.size[0],
                'height': image_file.size[1],
            })
            image_file.close()
            self.logger.info(template)
        else:
            self.logger.info(f"Failed to download image '{template['name']}'")

def load_image(self):
    # Read and load the image to draw and get its dimensions
    try:
        im = Image.open(self.image_path)
    except FileNotFoundError:
        self.logger.exception("Failed to load image")
        exit()
    except UnidentifiedImageError:
        self.logger.exception("File found, but couldn't identify image format")

    # Convert all images to RGBA - Transparency should only be supported with PNG
    if im.mode != "RGBA":
        im = im.convert("RGBA")
        self.logger.info("Converted to rgba")
    self.pix = im.load()

    self.logger.info("Loaded image size: {}", im.size)

    self.image_size = im.size
