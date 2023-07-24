import math


def closest_color(
        target_rgb: tuple, rgb_colors_array: list
    ):
        """Find the closest rgb color from palette to a target rgb color"""

        r, g, b = target_rgb[:3]
        color_diffs = []
        for color in rgb_colors_array:
            cr, cg, cb = color
            # Old method is to just take the linear distance from color to the palette options
            # This is bad when the template does not have accurate colors as it does not model
            # human perception and color contributions to brightness
            # https://en.wikipedia.org/wiki/Color_difference
            # color_diff = math.sqrt((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2)

            # For now, using a redmean approximation for sRGB colors
            # Should be the same in cases of accurate color reference
            # Otherwise provides 
            rmean = (r + cr)/2
            rdelta = r - cr
            gdelta = g - cg
            bdelta = b - cb
            color_diff = math.sqrt(((2 + rmean/256) * rdelta ** 2) + (4 * gdelta ** 2) + ((2 + (255-rmean)/256) * bdelta ** 2))
            color_diffs.append((color_diff, color))
        return min(color_diffs)[1]