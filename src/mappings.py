import numpy as np
from PIL import ImageColor


class ColorMapper:
    FULL_COLOR_MAP = {
        "#6D001A": 0,  # darkest red
        "#BE0039": 1,  # dark red
        "#FF4500": 2,  # red
        "#FFA800": 3,  # orange
        "#FFD635": 4,  # yellow
        "#FFF8B8": 5,  # pale yellow
        "#00A368": 6,  # dark green
        "#00CC78": 7,  # green
        "#7EED56": 8,  # light green
        "#00756F": 9,  # dark teal
        "#009EAA": 10,  # teal
        "#00CCC0": 11,  # light teal
        "#2450A4": 12,  # dark blue
        "#3690EA": 13,  # blue
        "#51E9F4": 14,  # light blue
        "#493AC1": 15,  # indigo
        "#6A5CFF": 16,  # periwinkle
        "#94B3FF": 17,  # lavender
        "#811E9F": 18,  # dark purple
        "#B44AC0": 19,  # purple
        "#E4ABFF": 20,  # pale purple
        "#DE107F": 21,  # magenta
        "#FF3881": 22,  # pink
        "#FF99AA": 23,  # light pink
        "#6D482F": 24,  # dark brown
        "#9C6926": 25,  # brown
        "#FFB470": 26,  # beige
        "#000000": 27,  # black
        "#515252": 28,  # dark gray
        "#898D90": 29,  # gray
        "#D4D7D9": 30,  # light gray
        "#FFFFFF": 31,  # white
    }

    COLOR_MAP = {
        #"#6D001A": 0,  # darkest red
        "#BE0039": 1,  # dark red
        "#FF4500": 2,  # red
        "#FFA800": 3,  # orange
        "#FFD635": 4,  # yellow
        #"#FFF8B8": 5,  # pale yellow
        "#00A368": 6,  # dark green
        "#00CC78": 7,  # green
        "#7EED56": 8,  # light green
        "#00756F": 9,  # dark teal
        "#009EAA": 10,  # teal
        #"#00CCC0": 11,  # light teal
        "#2450A4": 12,  # dark blue
        "#3690EA": 13,  # blue
        "#51E9F4": 14,  # light blue
        "#493AC1": 15,  # indigo
        "#6A5CFF": 16,  # periwinkle
        #"#94B3FF": 17,  # lavender
        "#811E9F": 18,  # dark purple
        "#B44AC0": 19,  # purple
        #"#E4ABFF": 20,  # pale purple
        #"#DE107F": 21,  # magenta
        "#FF3881": 22,  # pink
        "#FF99AA": 23,  # light pink
        "#6D482F": 24,  # dark brown
        "#9C6926": 25,  # brown
        #"#FFB470": 26,  # beige
        "#000000": 27,  # black
        #"#515252": 28,  # dark gray
        "#898D90": 29,  # gray
        "#D4D7D9": 30,  # light gray
        "#FFFFFF": 31,  # white
    }

    # map of pixel color ids to verbose name (for debugging)
    FULL_NAME_MAP = {
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

    COLORS = np.array([
        ImageColor.getcolor(color_hex, "RGB")
        for color_hex in COLOR_MAP
    ])

    @staticmethod
    def update_colors(colors_count: int):
        if colors_count != ColorMapper.COLORS.shape[0]:
            ColorMapper.COLORS = np.array([
                ImageColor.getcolor(color_hex, "RGB")
                for color_hex in (
                    ColorMapper.COLOR_MAP
                    if colors_count < 32
                    else ColorMapper.FULL_COLOR_MAP
                )
            ])

    @staticmethod
    def rgb_to_name(rgb: np.ndarray):
        return ColorMapper.color_id_to_name(
            ColorMapper.rgb_to_id(rgb)
        )
    
    @staticmethod
    def rgb_to_id(rgb: np.ndarray):
        return ColorMapper.FULL_COLOR_MAP[
            ColorMapper.rgb_to_hex(rgb)
        ]

    @staticmethod
    def rgb_to_hex(rgb: np.ndarray):
        """Convert rgb tuple to hexadecimal string."""
        return ("#%02x%02x%02x" % tuple(rgb)).upper()

    @staticmethod
    def color_id_to_name(color_id: int):
        """More verbose color indicator from a pixel color id."""
        if color_id in ColorMapper.FULL_NAME_MAP.keys():
            return "{} ({})".format(ColorMapper.FULL_NAME_MAP[color_id], str(color_id))
        return "Invalid Color ({})".format(str(color_id))

    @staticmethod
    def redmean_dist(image: np.ndarray, target: np.ndarray):
        """
        Calculate the redmean distance between two rgb colors
        https://en.wikipedia.org/wiki/Color_difference
        """
        
        # convert to float to prevent overflow
        image = image[...,:3].astype(np.float32)
        target = target[...,:3].astype(np.float32)

        mean_r = 0.5 * image[...,0] + 0.5 * target[...,0]
        delta_rgb = image - target
        weights = np.empty_like(delta_rgb)
        weights[...,0] = 2 + mean_r/256
        weights[...,1] = 4
        weights[...,2] = 3 - mean_r/256
        return np.einsum('...i,...i->...', weights, delta_rgb**2)

    @staticmethod
    def correct_image(target_image: np.ndarray) -> np.ndarray:
        image = np.empty_like(target_image)
        correction_dist = np.empty(
            target_image.shape[:2] + (ColorMapper.COLORS.shape[0],),
            dtype=np.uint8)
        
        for i, color in enumerate(ColorMapper.COLORS):
            correction_dist[...,i] = ColorMapper.redmean_dist(target_image, color)
        
        ids = np.argmin(correction_dist, axis=-1)
        image[...,:3] = ColorMapper.COLORS[ids].astype(np.uint8)
        image[...,3] = target_image[...,3]
        return image
