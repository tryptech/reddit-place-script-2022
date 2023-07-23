import numpy as np
from PIL import ImageColor


class ColorMapper:
    COLOR_MAP = {
        "#FF4500": 2,  # red
        "#FFA800": 3,  # orange
        "#FFD635": 4,  # yellow
        "#00A368": 6,  # dark green
        "#7EED56": 8,  # light green
        "#2450A4": 12,  # dark blue
        "#3690EA": 13,  # blue
        "#51E9F4": 14,  # light blue
        "#811E9F": 18,  # dark purple
        "#B44AC0": 19,  # purple
        "#FF99AA": 23,  # light pink
        "#9C6926": 25,  # brown
        "#000000": 27,  # black
        "#898D90": 29,  # gray
        "#D4D7D9": 30,  # light gray
        "#FFFFFF": 31,  # white
    }

    # map of pixel color ids to verbose name (for debugging)
    NAME_MAP = {
        0: "Darkest Red",
        1: "Dark Red",
        2: "Bright Red",
        3: "Orange",
        4: "Yellow",
        5: "Pale yellow",
        6: "Dark Green",
        7: "Green",
        8: "Light Green",
        9: "Dark Teal",
        10: "Teal",
        11: "Light Teal",
        12: "Dark Blue",
        13: "Blue",
        14: "Light Blue",
        15: "Indigo",
        16: "Periwinkle",
        17: "Lavender",
        18: "Dark Purple",
        19: "Purple",
        20: "pale purple",
        21: "magenta",
        22: "Pink",
        23: "Light Pink",
        24: "Dark Brown",
        25: "Brown",
        26: "Beige",
        27: "Black",
        28: "ark gray",
        29: "Gray",
        30: "Light Gray",
        31: "White",
    }

    @staticmethod
    def rgb_to_hex(rgb):
        """Convert rgb tuple to hexadecimal string."""
        return ("#%02x%02x%02x" % rgb).upper()

    @staticmethod
    def color_id_to_name(color_id: int):
        """More verbose color indicator from a pixel color id."""
        if color_id in ColorMapper.NAME_MAP.keys():
            return "{} ({})".format(ColorMapper.NAME_MAP[color_id], str(color_id))
        return "Invalid Color ({})".format(str(color_id))

    @staticmethod
    def closest_color(target_rgb: np.ndarray, rgb_colors_array: np.ndarray) -> np.ndarray:
        # redmean approximation for sRGB colors
        mean = (target_rgb[0] + rgb_colors_array[:, 0]) / 2

        # Calculate delta for all colors at once
        delta = target_rgb - rgb_colors_array

        # Calculate the color difference using vectorized operations
        color_diff = np.sqrt(np.sum(np.array([2 + mean/256, 4, 2 + (255-mean)/256]) * delta ** 2, axis=1))

        # Find the index of the minimum color difference and return the corresponding color
        return rgb_colors_array[np.argmin(color_diff)]


    @staticmethod
    def generate_rgb_colors_array() -> np.ndarray:
        """Generate array of available rgb colors to be used"""
        return np.array([
            ImageColor.getcolor(color_hex, "RGB")
            for color_hex in list(ColorMapper.COLOR_MAP.keys())
        ])
