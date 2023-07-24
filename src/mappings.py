import numpy as np
from PIL import ImageColor


class ColorMapper:
    HEX2ID = {
        # "#6D001A": 0,  # darkest red
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
    ID2NAME = {
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

    # Generate array of available rgb colors to be used
    COLORS = np.array([
        ImageColor.getcolor(color_hex, "RGB")
        for color_hex in HEX2ID.keys()
    ])

    @staticmethod
    def rgb2hex(rgb: tuple):
        """Convert rgb tuple to hexadecimal string."""
        return ("#%02x%02x%02x" % rgb).upper()

    @staticmethod
    def id2name(color_id: int):
        """More verbose color indicator from a pixel color id."""
        if color_id in ColorMapper.ID2NAME.keys():
            return "{} ({})".format(ColorMapper.ID2NAME[color_id], str(color_id))
        return "Invalid Color ({})".format(str(color_id))

    @staticmethod
    def correct_image(target_image: np.ndarray) -> np.ndarray:
        """
        Find the closest rgb color from palette to a target rgb color
        
        Old method is to just take the linear distance from color to the palette options
        This is bad when the template does not have accurate colors as it does not model
        human perception and color contributions to brightness
        https://en.wikipedia.org/wiki/Color_difference
        color_diff = math.sqrt((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2)

        For now, using a redmean approximation for sRGB colors
        Should be the same in cases of accurate color reference
        Otherwise provides
        """
        
        # Image dimension (m x n x 3)
        # Palette dimension (p x 3)
        
        # mean_r: mean of red channel with each palette color
        # (m x n x 1) + (1 x 1 x p) -> (m x n x p)
        mean_r = (target_image[...,None,0]
                  + ColorMapper.COLORS[None,None,:,0]) / 2
        # delta_rgb: difference between each pixel and each palette color
        # (m x n x 1 x 3) - (1 x 1 x p x 3) -> (m x n x p x 3)
        delta_rgb = (target_image[...,None,:]
                     - ColorMapper.COLORS[None,None,...])
        # weights: [2 + r_mean/256, 4, 2 + (255 - r_mean)/256]
        # (m x n x p x 3)
        weights = np.empty_like(delta_rgb)
        weights[...,0] = 2 + mean_r/256
        weights[...,1] = 4
        weights[...,2] = 3 - mean_r/256
        # delta_c: weighted distance between each pixel and each palette color
        # (m x n x p x 3) * (m x n x p x 3) -> (m x n x p)
        delta_c = np.einsum('...i,...i->...', weights, delta_rgb**2)
        # new_rgb_id: palette color id with minimum distance to the corresponding pixel
        # (m x n x p) -> (m x n)
        corrected_color_ids = np.argmin(delta_c, axis=-1)
        corrected_image = ColorMapper.COLORS[corrected_color_ids]
        return corrected_image.astype(np.uint8)
