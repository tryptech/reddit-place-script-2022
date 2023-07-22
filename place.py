import math

import time
import threading
from datetime import timedelta
from random import randint

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
        self.unverified_place_frequency = (
            self.json_data["unverified_place_frequency"]
            if "unverified_place_frequency" in self.json_data
            and self.json_data["unverified_place_frequency"] is not None
            else False
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

        # Load templates
        self.x_start, self.y_start, image = (
            utils.load_templates(self)
            or (
                *self.json_data["image_start_coords"],
                utils.load_image(self)
            )
        )

        # Image information
        self.image_lock = threading.Lock()
        self.pix = image.load()
        self.image_size = image.size

        self.first_run_counter = 0

        self.stop_event = threading.Event()

        self.waiting_thread_index = -1

    """ Main """
    # Draw a pixel at an x, y coordinate in r/place with a specific color

    def show_raw_pixel_coordinate(self, x, y, canvas_index):
        canvas_offset_x = int(canvas_index % 3) * 1000
        canvas_offset_y = int(math.floor(canvas_index / 3)) * 1000
        raw_x = canvas_offset_x + x + self.canvas['offset']['visual'][0]
        raw_y = canvas_offset_y + y + self.canvas['offset']['visual'][1]
        return raw_x, raw_y

    def set_pixel_and_check_ratelimit(
        self,
        access_token_in,
        x,
        y,
        name,
        color_index_in=18,
        canvas_index=0,
        thread_index=-1,
    ):
        # canvas structure:
        # 0 | 1 | 2
        # 3 | 4 | 5
        raw_x, raw_y = self.show_raw_pixel_coordinate(x, y, canvas_index)
        logger.warning(
            "Thread #{} - {}: Attempting to place {} pixel at {}, {}",
            thread_index,
            name,
            ColorMapper.color_id_to_name(color_index_in),
            raw_x,
            raw_y,
        )

        response = connect.set_pixel(self, [x, y],color_index_in, canvas_index, access_token_in, proxy.get_random_proxy(self, name=None))
        logger.debug(
            "Thread #{} - {}: Received response: {}", thread_index, name, response.text
        )

        self.waiting_thread_index = -1

        # There are 2 different JSON keys for responses to get the next timestamp.
        # If we don't get data, it means we've been rate limited.
        # If we do, a pixel has been successfully placed.
        if response.json()["data"] is None:
            logger.debug(response.json().get("errors"))
            errors = response.json().get("errors")[0]
            if "extensions" in errors:
                waitTime = math.floor(
                    errors["extensions"]["nextAvailablePixelTs"]
                )
                logger.error(
                    "Thread #{} - {}: Failed placing pixel: rate limited for {}",
                    thread_index,
                    name,
                    str(round(timedelta(milliseconds=errors["extensions"]["nextAvailablePixelTs"] - time.time()*1000).total_seconds())) + "s",
                )
            else:
                # Wait 1 minute on any other error
                waitTime = 60*1000
                logger.error(
                    "Thread #{} - {}: {}",
                    thread_index,
                    name,
                    errors.get("message")
                )
        else:
            waitTime = math.floor(
                response.json()["data"]["act"]["data"][0]["data"][
                    "nextAvailablePixelTimestamp"
                ]
            )
            logger.info(
                "Thread #{} - {}: Succeeded placing pixel", thread_index, name
            )

        # THIS COMMENTED CODE LETS YOU DEBUG THREADS FOR TESTING
        # Works perfect with one thread.
        # With multiple threads, every time you press Enter you move to the next one.
        # Move the code anywhere you want, I put it here to inspect the API responses.

        # Reddit returns time in ms and we need seconds, so divide by 1000
        # Add rand offset to delay pixel anywhere up to 1 minute later
        return (waitTime / 1000) + randint(0,60)

    def get_unset_pixel(self, x, y, index, pix, image_size):
        # x and y are pixel indicies within pix
        # image_size is [x, y] tuple
        # x must be less than image_size[0]
        # y must be less than image_size[1]

        originalX = x
        originalY = y
        loopedOnce = False
        imgOutdated = True
        wasWaiting = False

        while not self.stop_event.is_set():
            time.sleep(0.05)
            if self.waiting_thread_index != -1 and self.waiting_thread_index != index:
                x = originalX
                y = originalY
                loopedOnce = False
                imgOutdated = True
                wasWaiting = True
                continue

            # Stagger reactivation of threads after wait
            if wasWaiting:
                wasWaiting = False
                time.sleep(index * self.delay_between_launches)

            if x >= image_size[0]-1:
                y += 1
                x = 0

            if y >= image_size[1]-1:

                y = 0

            if x == originalX and y == originalY and loopedOnce:
                logger.info(
                    "Thread #{} : All pixels correct, trying again in 10 seconds... ",
                    index,
                )
                self.waiting_thread_index = index
                time.sleep(10)
                imgOutdated = True

            if imgOutdated:
                boardimg = connect.get_board(self, self.access_tokens[index])
                pix2 = boardimg.convert("RGB").load()
                imgOutdated = False

            logger.debug(
                "{}, {}, boardimg, {}, {}", x, y, image_size[0], image_size[1]
            )

            target_rgba = pix[x, y]

            new_rgb = ColorMapper.closest_color(
                target_rgba, self.rgb_colors_array, self.legacy_transparency
            )

            pix2_pos = [x + self.x_start + self.canvas['offset']['template_api'][0],
                    y + self.y_start + self.canvas['offset']['template_api'][1]]

            if pix2[pix2_pos[0], pix2_pos[1]] != new_rgb:
                logger.debug(
                    "{}, {}, {}, {}",
                    pix2[pix2_pos[0], pix2_pos[1]],
                    new_rgb,
                    target_rgba[:-1] != 255,
                    pix2[x, y] != new_rgb,
                )

                if target_rgba[:-1] == 255:
                    logger.debug(
                        "Thread #{} : Replacing {} pixel at: {},{} with {} color",
                        index,
                        pix2[pix2_pos[0], pix2_pos[1]],
                        x + self.x_start + self.canvas['offset']['visual'][0],
                        y + self.y_start + self.canvas['offset']['visual'][1],
                        new_rgb,
                    )
                    break
                else:
                    logger.debug(
                        "Transparent Pixel at {}, {} skipped",
                        x + self.x_start + self.canvas['offset']['visual'][0],
                        y + self.y_start + self.canvas['offset']['visual'][1],
                    )
            x += 1
            loopedOnce = True
        return x, y, new_rgb

    # Draw the input image
    def task(self, index, name, worker):
        # Whether image should keep drawing itself
        repeat_forever = True
        while not self.stop_event.is_set():
            # Update information
            with self.image_lock:
                pix = self.pix
                image_size = self.image_size

            # last_time_placed_pixel = math.floor(time.time())

            # note: Reddit limits us to place 1 pixel every 5 minutes, so I am setting it to
            # 5 minutes and 30 seconds per pixel
            if self.unverified_place_frequency:
                pixel_place_frequency = 1230
            else:
                pixel_place_frequency = 330

            next_pixel_placement_time = math.floor(time.time()) + pixel_place_frequency

            # Current pixel row and pixel column being drawn
            current_r = randint(0,image_size[0]-1)
            current_c = randint(0,image_size[1]-1)

            # Time until next pixel is drawn
            update_str = ""

            # Refresh auth tokens and / or draw a pixel
            # Reduce CPU usage by sleeping 1 second
            while not self.stop_event.wait(timeout=1):
                # get the current time
                current_timestamp = math.floor(time.time())

                # Update information
                with self.image_lock:
                    pix = self.pix
                    image_size = self.image_size

                # log next time until drawing
                time_until_next_draw = next_pixel_placement_time - current_timestamp

                if time_until_next_draw > 10000:
                    logger.warning(
                        "Thread #{} - {} :: CANCELLED :: Rate-Limit Banned", index, name
                    )
                    repeat_forever = False
                    break

                new_update_str = (
                    f"{time_until_next_draw} seconds until next pixel is drawn"
                )

                if update_str != new_update_str and time_until_next_draw % 10 == 0:
                    update_str = new_update_str
                else:
                    update_str = ""

                if len(update_str) > 0:
                    if not self.compactlogging:
                        logger.info("Thread #{} - {}: {}", index, name, update_str)

                # refresh access token if necessary
                if (
                    len(self.access_tokens) == 0
                    or len(self.access_token_expires_at_timestamp) == 0
                    or
                    # index in self.access_tokens
                    index not in self.access_token_expires_at_timestamp
                    or (
                        self.access_token_expires_at_timestamp.get(index)
                        and current_timestamp
                        >= self.access_token_expires_at_timestamp.get(index)
                    )
                ):
                    if not self.compactlogging:
                        logger.debug(
                            "Thread #{} - {}: Refreshing access token", index, name
                        )

                    # developer's reddit username and password
                    try:
                        username = name
                        password = worker["password"]
                    except Exception:
                        logger.exception(
                            "You need to provide all required fields to worker '{}'",
                            name,
                        )
                        exit(1)

                    connect.login(self, username, password, index, current_timestamp)

                # draw pixel onto screen
                if self.access_tokens.get(index) is not None and (
                    current_timestamp >= next_pixel_placement_time
                    or self.first_run_counter <= index
                ):

                    # place pixel immediately
                    # first_run = False
                    self.first_run_counter += 1

                    # get current pixel position from input image and replacement color
                    current_r, current_c, new_rgb = self.get_unset_pixel(
                        current_r,
                        current_c,
                        index,
                        pix,
                        image_size
                    )

                    # get converted color
                    new_rgb_hex = ColorMapper.rgb_to_hex(new_rgb)
                    pixel_color_index = ColorMapper.COLOR_MAP[new_rgb_hex]

                    logger.info("\nAccount Placing: ", name, "\n")

                    # draw the pixel onto r/place
                    # There's a better way to do this
                    subcanvas = 0
                    pixel_x_start = self.x_start + current_r + self.canvas['offset']['template_api'][0]
                    pixel_y_start = self.y_start + current_c + self.canvas['offset']['template_api'][1]

                    subcanvas = (3 * math.floor(pixel_x_start / 1000)) + math.floor(pixel_y_start / 1000)

                    # draw the pixel onto r/place
                    next_pixel_placement_time = self.set_pixel_and_check_ratelimit(
                        self.access_tokens[index],
                        pixel_x_start%1000,
                        pixel_y_start%1000,
                        name,
                        pixel_color_index,
                        subcanvas,
                        index,
                    )

                    current_r = randint(0,image_size[0]-1)
                    current_c = randint(0,image_size[1]-1)
            
            if not repeat_forever:
                break

    # Update templates
    def update_templates(self):
        # Reduce CPU usage by looping every 5 minutes
        while not self.stop_event.wait(timeout=300):
            # Update canvas offsets
            utils.load_canvas(self)
            # Get templates
            templates = utils.load_templates(self)
            if templates is None:
                continue
            self.x_start, self.y_start, image = templates

            # Update information
            with self.image_lock:
                self.pix = image.load()
                self.image_size = image.size

            logger.info("Templates updated")

    def start(self):
        self.stop_event.clear()

        threads = [
            threading.Thread(
                target=self.update_templates,
            )
        ] + [
            threading.Thread(
                target=self.task,
                args=[index, worker, self.json_data["workers"][worker]],
            )
            for index, worker in enumerate(self.json_data["workers"])
        ]

        for thread in threads:
            thread.start()
            # exit(1)
            time.sleep(self.delay_between_launches)
        
        # check for ctrl+c
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.warning("KeyboardInterrupt received, killing threads...")
            self.stop_event.set()
            logger.warning("Threads killed, exiting...")
            exit(0)