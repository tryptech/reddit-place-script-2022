import json
import os
import requests
from PIL import Image, UnidentifiedImageError
from io import BytesIO


def clear():
    os.system("cls||clear")
    return

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


def load_template_data(self):
    # Load the template images from the urls
    templates = []
    for url in self.template_urls:
        sources = get_json_from_url(self, url)
        if not sources:
            continue  # skip
        templates += sources['templates']
    
    original_names = set(template['name'] for template in templates)

    priority_names = set()
    try:
        if self.priority_url:
            for priority_template in get_json_from_url(self, self.priority_url)['templates']:
                priority_names.add(priority_template['name'])
    except requests.exceptions.HTTPError:
        self.logger.warning("Failed to load priority templates")

    # use priority unless nothing matches, then use names
    names = priority_names
    if not (priority_names & original_names):
        self.logger.warning("No priority templates found in template urls")
        names = set(
            self.json_data["names"]
            if "names" in self.json_data
            and self.json_data["names"]
            else []
        )

    # use names unless nothing matches, then use all templates
    if not (names & original_names):
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
    coord = (min(xs), min(ys))

    # Combine all images
    image = Image.new('RGBA', size)  # canvas in RGBA
    for i, x, y in zip(images[::-1], xs[::-1], ys[::-1]):
        image.paste(i, (x, y), i)
    image = image.crop((*coord, *size))

    self.logger.info("Loaded image size: {}", image.size)

    # Save the template image
    image.save(self.image_path)
    self.logger.info("Saved template image to {}", self.image_path)

    return coord, image
