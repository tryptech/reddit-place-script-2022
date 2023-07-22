import math
import time
import threading
from loguru import logger

from src.mappings import ColorMapper
import src.proxy as proxy
import src.utils as utils
import src.connect as connect


class PlaceClient:
    def __init__(self, config_path, canvas_path):
        self.logger = logger
        logger.add('logs/{time}.log', rotation='1 day')

        # Data
        self.json_data = utils.get_json_data(self, config_path)
        
        self.template_urls = (
            self.json_data["template_urls"]
            if "template_urls" in self.json_data
            and self.json_data["template_urls"] is not None
            else []
        )
        self.canvas_path = canvas_path
        self.canvas = utils.get_json_data(self, self.canvas_path)
        self.image_path = (
            self.json_data["image_path"]
            if "image_path" in self.json_data
            else "image.jpg"
        )

        # In seconds
        self.delay_between_launches = (
            self.json_data["thread_delay"]
            if "thread_delay" in self.json_data
            and self.json_data["thread_delay"] is not None
            else 3
        )
        self.unverified_rate_limit = (
            self.json_data["unverified_rate_limit"]
            if "unverified_rate_limit" in self.json_data
            and self.json_data["unverified_rate_limit"] is not None
            else 0
        )

        self.legacy_transparency = (
            self.json_data["legacy_transparency"]
            if "legacy_transparency" in self.json_data
            and self.json_data["legacy_transparency"] is not None
            else True
        )
        proxy.Init(self)

        # Color palette
        self.rgb_colors_array = ColorMapper.generate_rgb_colors_array()

        # Auth
        self.access_tokens = {}
        self.access_token_expires_at_timestamp = {}

        # Thread monitoring
        self.update_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.board_outdated = threading.Event()
        self.template_outdated = threading.Event()

        # Load template
        coord, template = (
            utils.load_template_data(self)
            or (
                self.json_data["image_start_coords"],
                utils.load_image(self)
            )
        )

        # Template information
        self.coord = (
            coord[0] + self.canvas['offset']['template_api'][0],
            coord[1] + self.canvas['offset']['template_api'][1]
        )
        self.size = template.size
        self.template = template.load()

        # Board information
        self.board = None
        self.wrong_pixels = []

    # Update board, templates and canvas offsets
    # Returns position, size and template image
    def update(self, username):
        # Threads should have exclusive access to updating data
        with self.update_lock:
            # Update template image and canvas offsets if outdated
            if self.template_outdated.is_set():
                self.template_outdated.clear()
                logger.debug("Thread {}: Updating template image and canvas offsets", username)
                coord, template = utils.load_template_data(self)
                self.canvas = utils.get_json_data(self, self.canvas_path)
                self.coord = (
                    coord[0] + self.canvas['offset']['template_api'][0],
                    coord[1] + self.canvas['offset']['template_api'][1]
                )
                self.size = template.size
                self.template = template.load()
                logger.info("Thread {}: Template image and canvas offsets updated", username)
            
            # Update board image if outdated
            if self.board_outdated.is_set() or self.board is None:
                self.board_outdated.clear()
                logger.debug("Thread {}: Updating board image", username)
                self.board = (
                    connect
                    .get_board(self, self.access_tokens[username])
                    .crop((*self.coord, self.coord[0] + self.size[0], self.coord[1] + self.size[1]))
                    .convert("RGB")
                    .load()
                )
                logger.info("Thread {}: Board image updated", username)

    def get_wrong_pixel(self, username):
        # Check every 10 seconds for an unset pixel
        while not self.stop_event.wait(timeout=10):
            # Update information
            self.update(username)

            # Search for unset pixels
            with self.update_lock:
                self.compute_wrong_pixels(username)
                # Pop the first unset pixel
                if len(self.wrong_pixels) > 0:
                    coord, new_rgb = self.wrong_pixels.pop()
                    logger.info(
                        "Thread {}: Found unset pixel at {}",
                        username, coord
                    )
                    return coord, new_rgb
            
            # All pixels correct, try again in 10 seconds
            logger.info(
                "Thread {}: All pixels are correct, trying again in 10 seconds...",
                username
            )

    def compute_wrong_pixels(self, username):
        if len(self.wrong_pixels) > 0:
            logger.debug("Thread {}: Board is still up-to-date", username)
            return
        logger.debug("Thread {}: Board has been updated", username)
        for x in range(0, self.size[0]):
            for y in range(0, self.size[1]):
                target_rgba = self.template[x, y]
                if target_rgba[-1] == 0:
                    continue  # skip transparent pixels
                new_rgb = ColorMapper.closest_color(
                    target_rgba, self.rgb_colors_array, self.legacy_transparency
                )
                if self.board[x, y] == new_rgb:
                    continue  # skip correct pixels
                self.wrong_pixels.append(((x, y), new_rgb))

    def get_visual_position(self, coord, subcanvas):
        canvas_offset_x = int(subcanvas % 3) * 1000
        canvas_offset_y = int(math.floor(subcanvas / 3)) * 1000
        raw_x = canvas_offset_x + coord[0] + self.canvas['offset']['visual'][0]
        raw_y = canvas_offset_y + coord[1] + self.canvas['offset']['visual'][1]
        return raw_x, raw_y

    def set_pixel_and_check_ratelimit(self, color_index, coord, username):
        # canvas structure:
        # 0 | 1 | 2
        # 3 | 4 | 5
        subcanvas = (3 * math.floor(coord[0] / 1000)) + math.floor(coord[1] / 1000)

        logger.warning(
            "Thread {}: Attempting to place {} pixel at {}",
            username, ColorMapper.color_id_to_name(color_index),
            self.get_visual_position(coord, subcanvas)
        )

        response = connect.set_pixel(self, coord, color_index, subcanvas, self.access_tokens[username])
        logger.debug("Thread {}: Received response: {}", username, response.text)

        # Successfully placed
        if response.json()["data"] is not None:
            next_time = math.floor(
                response.json()["data"]["act"]["data"][0]
                ["data"]["nextAvailablePixelTimestamp"]
            )
            logger.info("Thread {}: Succeeded placing pixel", username)
            return next_time
        
        logger.debug(response.json().get("errors"))
        errors = response.json().get("errors")[0]

        # Unknown error
        if "extensions" not in errors:
            logger.error("Thread {}: {}", username, errors.get("message"))
            # Wait 1 minute on any other error
            return 60
        
        # Rate limited, time in ms
        next_time = errors["extensions"]["nextAvailablePixelTs"] / 1000
        logger.error(
            "Thread {}: Failed placing pixel: rate limited for {:.0f}s",
            username, next_time - time.time(),
        )

        # THIS COMMENTED CODE LETS YOU DEBUG THREADS FOR TESTING
        # Works perfect with one thread.
        # With multiple threads, every time you press Enter you move to the next one.
        # Move the code anywhere you want, I put it here to inspect the API responses.

        return next_time

    # Draw the input image
    def task(self, username, password):
        # note: Reddit limits us to place 1 pixel every 5 minutes, so I am setting it to
        # 5 minutes and 30 seconds per pixel
        time_to_wait = self.unverified_rate_limit
        # Refresh auth tokens and / or draw a pixel
        while not self.stop_event.wait(time_to_wait):
            # get the current time
            current_time = math.floor(time.time())

            # Refresh access token if necessary
            if (username not in self.access_tokens
                    or username not in self.access_token_expires_at_timestamp
                    or (
                        self.access_token_expires_at_timestamp[username]
                        and current_time >= self.access_token_expires_at_timestamp[username]
                    )):
                logger.debug("Thread {}: Refreshing access token", username)
                connect.login(self, username, password, username, current_time)

            # get current pixel position from input image and replacement color
            relative, new_rgb = self.get_wrong_pixel(username)

            # draw the pixel onto r/place
            logger.info("Thread {} :: PLACING ::", username)
            next_placement_time = self.set_pixel_and_check_ratelimit(
                ColorMapper.COLOR_MAP[ColorMapper.rgb_to_hex(new_rgb)],
                (self.coord[0] + relative[0], self.coord[1] + relative[1]), username,
            )

            # log next time until drawing
            time_to_wait = next_placement_time - current_time

            if time_to_wait > 10000:
                logger.warning("Thread {} :: CANCELLED :: Rate-Limit Banned", username)
                return

            # wait until next rate limit expires
            logger.debug("Thread {}: Until next placement, {}s", username, time_to_wait)
            time.sleep(time_to_wait)

    def start(self):
        self.stop_event.clear()

        threads = [
            threading.Thread(
                target=self.task,
                args=[username, self.json_data["workers"][username]["password"]]
            )
            for username in self.json_data["workers"].keys()
        ]

        for thread in threads:
            thread.start()
            # exit(1)
            time.sleep(self.delay_between_launches)
        
        try:
            while True:
                for _ in range(300):
                    time.sleep(1)
                    # Update board image every seconds
                    self.board_outdated.set()
                # Update template image and canvas offsets every 5 minutes
                self.template_outdated.set()
        # Check for ctrl+c
        except KeyboardInterrupt:
            logger.warning("KeyboardInterrupt received, killing threads...")
            self.stop_event.set()
            logger.warning("Threads killed, exiting...")
            exit(0)
