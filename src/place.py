import numpy as np
import time
import threading
from loguru import logger
from json import JSONDecodeError

from src.mappings import ColorMapper
import src.proxy as proxy
import src.utils as utils
import src.connect as connect


class PlaceClient:
    def __init__(self, config_path, canvas_path):
        self.logger = logger
        logger.add('logs/{time}.log', rotation='1 day')

        # Thread monitoring
        self.update_lock = threading.Lock()
        self.config_lock = threading.Lock()
        self.print_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.board_outdated = threading.Event()
        self.template_outdated = threading.Event()

        # Data
        self.config_path = config_path
        self.canvas_path = canvas_path
        self.config = utils.get_json_data(self, self.config_path)
        self.canvas = utils.get_json_data(self, self.canvas_path)

        proxy.Init(self)

        self.colors_count = 0

        # Auth
        self.access_tokens = {}
        self.access_token_expires_at_timestamp = {}

        # Load template
        data = utils.load_template_data(self)
        if not data:
            exit(1)  # exit if template is empty
        coord, template = data

        # Template information
        self.coord = coord + np.array(self.canvas['offset']['template_api'])
        self.template = ColorMapper.correct_image(np.swapaxes(template, 0, 1))

        # Board information
        self.board: np.ndarray = None
        self.wrong_pixels: list = []

    # Update board, templates and canvas offsets
    # Returns position, size and template image
    def _update(self, username):
        # Update board image if outdated
        if self.board_outdated.is_set() or self.board is None:
            self.board_outdated.clear()
            logger.debug("Thread {}: Updating board image", username)
            self.board = np.swapaxes(
                connect
                .get_board(self, self.access_tokens[username])
                .crop((*self.coord, self.coord[0] + self.template.shape[0], self.coord[1] + self.template.shape[1]))
                .convert("RGB"),
                0, 1
            )
            # Compute wrong pixels (cropped template relative position)
            dist = ColorMapper.redmean_dist(self.board, self.template)
            coords = np.argwhere(
                (self.template[...,3] == 255)
                & (self.template[...,:3] != self.board).any(axis=-1)
            )  # sorted by distance to target color
            coords = coords[np.argsort(dist[coords[:,0], coords[:,1]])]
            # get rgb values of wrong pixels
            target_rgb = self.template[coords[:,0], coords[:,1]][:,:3]
            self.wrong_pixels = list(zip(coords, target_rgb))
            logger.info("Thread {}: Board image updated", username)

        # Update template image and canvas offsets if outdated
        if self.template_outdated.is_set():
            self.template_outdated.clear()
            logger.debug("Thread {}: Updating template image and canvas offsets", username)
            data = utils.load_template_data(self)
            if not data:
                return  # skip updating
            coord, template = data
            self.canvas = utils.get_json_data(self, self.canvas_path)
            self.coord = coord + np.array(self.canvas['offset']['template_api'])
            self.template = ColorMapper.correct_image(np.swapaxes(template, 0, 1))
            logger.info("Thread {}: Template image and canvas offsets updated", username)
        
    # Thread-safe config getter
    def config_get(self, key, default=None):
        with self.config_lock:
            return self.config.get(key, default)
    
    # Thread-safe config updater
    def config_update(self):
        with self.config_lock:
            self.config = utils.get_json_data(self, self.config_path)

    def get_wrong_pixel(self, username):
        # Check every 10 seconds for an unset pixel
        while not self.stop_event.wait(timeout=10):
            # Threads should have exclusive access to updating data
            with self.update_lock:
                # Update information
                self._update(username)

                # Pop the first unset pixel
                if len(self.wrong_pixels) > 0:
                    coord, new_rgb = self.wrong_pixels.pop()
                    logger.info(
                        "Thread {}: Found unset pixel at {}",  # shows visual position
                        username, coord + self.coord + np.array(self.canvas['offset']['visual'])
                    )
                    target_rgb = self.template[coord[0], coord[1], :3]
                    board_rgb = self.board[coord[0], coord[1], :3]
                    return coord, new_rgb, target_rgb, board_rgb
            
            # All pixels correct, try again in 10 seconds
            logger.info(
                "Thread {}: All pixels are correct, trying again in 10 seconds...",
                username
            )

    def set_pixel_and_check_ratelimit(self, color_index, coord, username,
                                      new_rgb, target_rgb, board_rgb):

        with self.print_lock:
            logger.opt(colors=True).warning(
                "Thread {}: Attempting to place pixel",
                username
            )
            new_rgb_name = ColorMapper.color_id_to_name(color_index)
            board_rgb_name = ColorMapper.rgb_to_name(board_rgb)
            print(f"Thread {username}",  # shows visual position
                  f"Pixel position: {coord + np.array(self.canvas['offset']['visual'])}",
                  f"Template color: [\033[38;2;{';'.join(map(str, target_rgb))}m▉\033[0m]",
                  f"Expected color: [\033[38;2;{';'.join(map(str, new_rgb))}m▉\033[0m] ({new_rgb_name})",
                  f"Board    color: [\033[38;2;{';'.join(map(str, board_rgb))}m▉\033[0m] ({board_rgb_name})",
                  sep='\n')

        # Convert global pixel position to local pixel position (Reddit API)
        # canvas structure:
        # 0 | 1 | 2
        # 3 | 4 | 5
        subcanvas = (coord // 1000)[0] + 3 * (coord // 1000)[1]
        coord = coord % 1000

        response = connect.set_pixel(self, coord, color_index,
                                     subcanvas, self.access_tokens[username])
        logger.debug("Thread {}: Received response: {}", username, response.text)

        # Successfully placed
        if response.json()["data"] is not None:
            
            next_time = (
                response.json()["data"]["act"]["data"][0]
                ["data"]["nextAvailablePixelTimestamp"]
            ) / 1000

            #Check if pixel was placed, potential shadowban
            who_placed = connect.check(self, coord, color_index, subcanvas, username) 
            if who_placed == username:
                logger.success("Thread {}: Succeeded placing pixel", username)
            else:
                logger.error("Thread {}: POTENTIALLY SHADOW BANNED", username)
                logger.error("Thread {}: Pixel placed by {}", username or "no one" , who_placed)
                return time.time()
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
        return next_time

    # Draw the input image
    def task(self, username, password):
        # Refresh auth tokens and / or draw a pixel
        while not self.stop_event.is_set():
            # get the current time
            current_time = time.time()

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
            relative, new_rgb, target_rgb, board_rgb = self.get_wrong_pixel(username)

            # draw the pixel onto r/place
            logger.info("Thread {} :: PLACING ::", username)
            next_placement_time = self.set_pixel_and_check_ratelimit(
                ColorMapper.rgb_to_id(new_rgb),
                self.coord + relative, username,
                new_rgb, target_rgb, board_rgb
            )

            # next time until drawing with random offset to try dodging shadow bans
            time_to_wait = next_placement_time - current_time + np.random.randint(0, 4) ** 4

            if time_to_wait > 10000:
                logger.warning("Thread {} :: CANCELLED :: Rate-Limit Banned", username)
                return

            # wait until next rate limit expires
            logger.info("Thread {}: Until next placement {:.0f}s", username, time_to_wait)
            # note: Reddit limits us to place 1 pixel every 5 minutes, so I am setting it to
            # 5 minutes and 30 seconds per pixel
            if self.stop_event.wait(time_to_wait):
                logger.warning("Thread {} :: CANCELLED :: Stopped by Main Thread", username)
                return

    def start(self):
        self.stop_event.clear()
        threads = {}
        i = 0

        try:
            while True:
                i += 1

                # Reduce CPU usage
                time.sleep(self.config_get("thread_delay") or 3)

                # Update config
                logger.debug("Main: Updating config")
                try:
                    self.config_update()
                except JSONDecodeError:
                    logger.warning("Main: Failed to update config")
                for username in self.config_get("workers").keys():
                    if username in threads:
                        continue
                    logger.debug("Main: Adding new worker {}", username)
                    threads[username] = threading.Thread(
                        target=self.task,
                        args=[username, self.config_get("workers")[username]["password"]]
                    )
                    threads[username].daemon = True
                    threads[username].start()

                    # Reduce CPU usage
                    time.sleep(self.config_get("thread_delay") or 3)

                # Update board image every seconds
                logger.debug("Main: Allowing board image update")
                self.board_outdated.set()

                # Check if any threads are alive
                if not any(thread.is_alive() for thread in threads.values()):
                    logger.warning("Main: All threads died")
                    break

                # Update template image and canvas offsets every 3-4 minutes
                if i % 100 == 0:
                    logger.debug("Main: Allowing template image and canvas offsets update")
                    self.template_outdated.set()
        # Check for ctrl+c
        except KeyboardInterrupt:
            logger.warning("Main: KeyboardInterrupt received, killing threads...")
            self.stop_event.set()
            logger.warning("Main: Threads killed, exiting...")
            for thread in threads:
                thread.join()
            exit(0)
