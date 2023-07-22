import json
import os
import requests
from PIL import Image, UnidentifiedImageError
from io import BytesIO


def clear():
    os.system("cls||clear")

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


def load_image(self):
    # Read and load the image to draw and get its dimensions
    try:
        image = Image.open(self.image_path)
    except FileNotFoundError:
        self.logger.exception("Failed to load image")
        exit()
    except UnidentifiedImageError:
        self.logger.exception("File found, but couldn't identify image format")
        exit()

    # Convert all images to RGBA - Transparency should only be supported with PNG
    if image.mode != "RGBA":
        image = image.convert("RGBA")
        self.logger.debug("Converted to rgba")
    
    self.logger.debug("Loaded image size: {}", image.size)
    return image


def get_json_from_url(self, url):
    # Get the json data from the url
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        self.logger.exception(f"Error fetching data from {url}: {e}")
        return None
    
    return response.json()


def load_image_from_url(self, url):
    # Get the image from the url
    try:
        response = requests.get(url)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))
    except requests.exceptions.RequestException as e:
        self.logger.exception(f"Error loading image from {url}: {e}")
        return None
    except UnidentifiedImageError:
        self.logger.exception(f"Coudln't identify image format from {url}")
        return None
    
    # Convert image to RGBA - Transparency should only be supported with PNG
    if image.mode != "RGBA":
        image = image.convert("RGBA")
        self.logger.debug("Converted to rgba")
    
    self.logger.debug("Loaded image size: {}", image.size)
    return image


def load_templates(self):
    # Load the template images from the urls
    templates = []
    for url in self.template_urls:
        sources = get_json_from_url(self, url)
        if not sources:
            continue  # skip
        templates += sources['templates']
    
    names = (
        self.json_data["names"]
        if "names" in self.json_data
        and self.json_data["names"]
        else []
    )
    if names:
        templates = list(filter(lambda template: template['name'] in names, templates))

    images = []
    for sources in templates:
        image = load_image_from_url(self, sources['sources'][0])
        if not image:
            continue  # skip
        images.append(image)
    
    if not images:
        self.logger.error("Empty templates")
        return None

    # Compute dimensions
    xs = [template['x'] for template in templates]
    ys = [template['y'] for template in templates]
    sizes = [image.size for image in images]
    ws = [s[0] + x for s, x in zip(sizes, xs)]
    hs = [s[1] + y for s, y in zip(sizes, ys)]
    size = (max(ws), max(hs))

    # Starting position
    x_start = min(xs)
    y_start = min(ys)

    # Combine all images
    image = Image.new('RGBA', size)  # canvas in RGBA
    for i, x, y in zip(images[::-1], xs[::-1], ys[::-1]):
        image.paste(i, (x, y), i)
    image = image.crop((x_start, y_start, *size))

    self.logger.info("Loaded image size: {}", image.size)

    # Save the template image
    image.save(self.image_path)
    self.logger.info("Saved template image to {}", self.image_path)

    return x_start, y_start, image

def load_canvas(self):
    # Load the canvas offsets from file
    self.canvas = get_json_data(self, self.canvas_path)
    self.logger.info("Updated canvas offsets")
    return