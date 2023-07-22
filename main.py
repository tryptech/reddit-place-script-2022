import math

import requests
import json
import time
import threading
import sys
from io import BytesIO
from http import HTTPStatus
from websocket import create_connection
from websocket._exceptions import WebSocketConnectionClosedException
import ssl
from datetime import timedelta
from PIL import Image
from random import randint

from loguru import logger
import click
from bs4 import BeautifulSoup


from src.mappings import ColorMapper
import src.proxy as proxy
import src.utils as utils


class PlaceClient:
    def __init__(self, config_path):
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
        x_start, y_start, image = (
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

        # Start coordinates
        self.raw_pixel_x_start: int = x_start - 500
        self.raw_pixel_y_start: int = y_start - 500
        self.pixel_x_start = self.raw_pixel_x_start + 1500
        self.pixel_y_start = self.raw_pixel_y_start + 1000

        self.first_run_counter = 0

        self.stop_event = threading.Event()

        self.waiting_thread_index = -1

    """ Main """
    # Draw a pixel at an x, y coordinate in r/place with a specific color

    def show_raw_pixel_coordinate(self, x, y, canvas_index):
        canvas_offset_x = int(canvas_index % 3) * 1000
        canvas_offset_y = int(math.floor(canvas_index / 3)) * 1000
        raw_x = canvas_offset_x + x - 1500
        raw_y = canvas_offset_y + y - 1000
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

        url = "https://gql-realtime-2.reddit.com/query"

        payload = json.dumps(
            {
                "operationName": "setPixel",
                "variables": {
                    "input": {
                        "actionName": "r/replace:set_pixel",
                        "PixelMessageData": {
                            "coordinate": {"x": x, "y": y},
                            "colorIndex": color_index_in,
                            "canvasIndex": canvas_index,
                        },
                    }
                },
                "query": """mutation setPixel($input: ActInput!) {
                        act(input: $input) {
                            data {
                                ... on BasicMessage {
                                    id
                                    data {
                                        ... on GetUserCooldownResponseMessageData {
                                            nextAvailablePixelTimestamp
                                            __typename
                                        }
                                        ... on SetPixelResponseMessageData {
                                            timestamp
                                            __typename
                                        }
                                        __typename
                                    }
                                    __typename
                                }
                                __typename
                            }
                            __typename
                        }
                    }
                """,
            }
        )
        headers = {
            "origin": "https://garlic-bread.reddit.com",
            "referer": "https://garlic-bread.reddit.com/",
            "apollographql-client-name": "garlic-bread",
            "Authorization": "Bearer " + access_token_in,
            "Content-Type": "application/json",
        }

        response = requests.request(
            "POST",
            url,
            headers=headers,
            data=payload,
            proxies=proxy.get_random_proxy(self, name=None),
        )
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
            logger.success(
                "Thread #{} - {}: Succeeded placing pixel", thread_index, name
            )

        # THIS COMMENTED CODE LETS YOU DEBUG THREADS FOR TESTING
        # Works perfect with one thread.
        # With multiple threads, every time you press Enter you move to the next one.
        # Move the code anywhere you want, I put it here to inspect the API responses.

        # Reddit returns time in ms and we need seconds, so divide by 1000
        # Add rand offset to delay pixel anywhere up to 3 minutes later
        return (waitTime / 1000) + randint(0,3*60)

    def get_board(self, access_token_in):
        logger.debug("Connecting and obtaining board images")
        while not self.stop_event.is_set():
            try:
                ws = create_connection(
                    "wss://gql-realtime-2.reddit.com/query",
                    origin="https://garlic-bread.reddit.com",
                    sslopt={"cert_reqs": ssl.CERT_NONE},
                    
                )
                break
            except Exception:
                logger.error(
                    "Failed to connect to websocket, trying again in 30 seconds..."
                )
                time.sleep(30)

        ws.send(
            json.dumps(
                {
                    "type": "connection_init",
                    "payload": {"Authorization": "Bearer " + access_token_in},
                }
            )
        )
        while not self.stop_event.is_set():
            try:
                msg = ws.recv()
            except WebSocketConnectionClosedException as e:
                logger.error(e)
                continue
            if msg is None:
                logger.error("Reddit failed to acknowledge connection_init")
                exit()
            if msg.startswith('{"type":"connection_ack"}'):
                logger.debug("Connected to WebSocket server")
                break
        logger.debug("Obtaining Canvas information")
        ws.send(
            json.dumps(
                {
                    "id": "1",
                    "type": "start",
                    "payload": {
                        "variables": {
                            "input": {
                                "channel": {
                                    "teamOwner": "GARLICBREAD",
                                    "category": "CONFIG",
                                }
                            }
                        },
                        "extensions": {},
                        "operationName": "configuration",
                        "query": "subscription configuration($input: SubscribeInput!) {\n  subscribe(input: $input) {\n    id\n    ... on BasicMessage {\n      data {\n        __typename\n        ... on ConfigurationMessageData {\n          colorPalette {\n            colors {\n              hex\n              index\n              __typename\n            }\n            __typename\n          }\n          canvasConfigurations {\n            index\n            dx\n            dy\n            __typename\n          }\n          canvasWidth\n          canvasHeight\n          __typename\n        }\n      }\n      __typename\n    }\n    __typename\n  }\n}\n",
                    },
                }
            )
        )

        while not self.stop_event.is_set():
            canvas_payload = json.loads(ws.recv())
            if canvas_payload["type"] == "data":
                canvas_details = canvas_payload["payload"]["data"]["subscribe"]["data"]
                logger.debug("Canvas config: {}", canvas_payload)
                break

        canvas_sockets = []

        canvas_count = len(canvas_details["canvasConfigurations"])

        for i in range(0, canvas_count):
            canvas_sockets.append(2 + i)
            logger.debug("Creating canvas socket {}", canvas_sockets[i])

            ws.send(
                json.dumps(
                    {
                        "id": str(2 + i),
                        "type": "start",
                        "payload": {
                            "variables": {
                                "input": {
                                    "channel": {
                                        "teamOwner": "GARLICBREAD",
                                        "category": "CANVAS",
                                        "tag": str(i),
                                    }
                                }
                            },
                            "extensions": {},
                            "operationName": "replace",
                            "query": """subscription replace($input: SubscribeInput!) {
                                    subscribe(input: $input) {
                                        id
                                        ... on BasicMessage {
                                            data {
                                                __typename
                                                ... on FullFrameMessageData {
                                                    __typename
                                                    name
                                                    timestamp
                                                }
                                                ... on DiffFrameMessageData {
                                                    __typename
                                                    name
                                                    currentTimestamp
                                                    previousTimestamp
                                                }
                                            }
                                            __typename
                                        }
                                        __typename
                                    }
                                }""",
                        },
                    }
                )
            )

        imgs = []
        logger.debug("A total of {} canvas sockets opened", len(canvas_sockets))

        while len(canvas_sockets) > 0:
            temp = json.loads(ws.recv())
            logger.debug("Waiting for WebSocket message")

            if temp["type"] == "data":
                logger.debug(f"Received WebSocket data type message")
                msg = temp["payload"]["data"]["subscribe"]

                if msg["data"]["__typename"] == "FullFrameMessageData":
                    logger.debug("Received full frame message")
                    img_id = int(temp["id"])
                    logger.debug("Image ID: {}", img_id)

                    if img_id in canvas_sockets:
                        logger.debug("Getting image: {}", msg["data"]["name"])
                        img = requests.get(msg["data"]["name"], stream=True,
                                           proxies=proxy.get_random_proxy(self, name=None),)
                        if not img.status_code == 404:
                            imgs.append(
                                [
                                    img_id,
                                    Image.open(
                                        BytesIO(img.content)
                                    ),
                                ]
                            )
                            canvas_sockets.remove(img_id)
                            logger.debug(
                                "Canvas sockets remaining: {}", len(canvas_sockets)
                            )
                        else:
                            logger.debug("Received wrong image")
                            canvas_sockets.remove(img_id)

        for i in range(0, canvas_count - 1):
            ws.send(json.dumps({"id": str(2 + i), "type": "stop"}))

        ws.close()

        new_img_width = (
            max(map(lambda x: x["dx"], canvas_details["canvasConfigurations"]))
            + canvas_details["canvasWidth"]
        )
        logger.debug("New image width: {}", new_img_width)

        new_img_height = (
            max(map(lambda x: x["dy"], canvas_details["canvasConfigurations"]))
            + canvas_details["canvasHeight"]
        )
        logger.debug("New image height: {}", new_img_height)

        new_img = Image.new("RGB", (new_img_width, new_img_height))

        for idx, img in enumerate(sorted(imgs, key=lambda x: x[0])):
            logger.debug("Adding image (ID {}): {}", img[0], img[1])
            dx_offset = int(canvas_details["canvasConfigurations"][idx]["dx"])
            dy_offset = int(canvas_details["canvasConfigurations"][idx]["dy"])
            new_img.paste(img[1], (dx_offset, dy_offset))

        return new_img

    def get_unset_pixel(self, x, y, index, pix, image_size,
                        self_pixel_x_start, self_pixel_y_start):
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

            if x >= image_size[0]:
                y += 1
                x = 0

            if y >= image_size[1]:

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
                boardimg = self.get_board(self.access_tokens[index])
                pix2 = boardimg.convert("RGB").load()
                imgOutdated = False

            logger.debug("{}, {}", x + self_pixel_x_start, y + self_pixel_y_start)
            logger.debug(
                "{}, {}, boardimg, {}, {}", x, y, image_size[0], image_size[1]
            )

            target_rgb = pix[x, y]

            new_rgb = ColorMapper.closest_color(
                target_rgb, self.rgb_colors_array, self.legacy_transparency
            )

            if pix2[x + self_pixel_x_start, y + self_pixel_y_start] != new_rgb:
                logger.debug(
                    "{}, {}, {}, {}",
                    pix2[x + self_pixel_x_start, y + self_pixel_y_start],
                    new_rgb,
                    new_rgb != (69, 42, 0),
                    pix2[x, y] != new_rgb,
                )

                # (69, 42, 0) is a special color reserved for transparency.
                if new_rgb != (69, 42, 0):
                    logger.debug(
                        "Thread #{} : Replacing {} pixel at: {},{} with {} color",
                        index,
                        pix2[x + self_pixel_x_start, y + self_pixel_y_start],
                        x + self_pixel_x_start - 1500,
                        y + self_pixel_y_start - 1000,
                        new_rgb,
                    )
                    break
                else:
                    logger.debug(
                        "Transparent Pixel at {}, {} skipped",
                        x + self_pixel_x_start - 1500,
                        y + self_pixel_y_start - 1000,
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
                self_pixel_x_start = self.pixel_x_start
                self_pixel_y_start = self.pixel_y_start

            # last_time_placed_pixel = math.floor(time.time())

            # note: Reddit limits us to place 1 pixel every 5 minutes, so I am setting it to
            # 5 minutes and 30 seconds per pixel
            if self.unverified_place_frequency:
                pixel_place_frequency = 1230
            else:
                pixel_place_frequency = 330

            next_pixel_placement_time = math.floor(time.time()) + pixel_place_frequency

            # Current pixel row and pixel column being drawn
            current_r = randint(0,image_size[0])
            current_c = randint(0,image_size[1])

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
                    self_pixel_x_start = self.pixel_x_start
                    self_pixel_y_start = self.pixel_y_start

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

                    while not self.stop_event.is_set():
                        try:
                            client = requests.Session()
                            client.proxies = proxy.get_random_proxy(self, name)
                            client.headers.update(
                                {
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                                    "Origin": "https://www.reddit.com",
                                    "Referer": "https://www.reddit.com/login/?",
                                }
                            )

                            client.get("https://www.reddit.com")

                            r = client.get(
                                "https://www.reddit.com/login",
                                proxies=proxy.get_random_proxy(self, name),
                            )
                            login_get_soup = BeautifulSoup(r.content, "html.parser")
                            csrf_token = login_get_soup.find(
                                "input", {"name": "csrf_token"}
                            )["value"]
                            data = {
                                "username": username,
                                "password": password,
                                "dest": "https://new.reddit.com/",
                                "csrf_token": csrf_token,
                                "otp": "",
                            }

                            r = client.post(
                                "https://www.reddit.com/login",
                                data=data,
                                proxies=proxy.get_random_proxy(self, name),
                            )
                            break
                        except Exception:
                            logger.error(
                                "Failed to connect to websocket, trying again in 30 seconds..."
                            )
                            time.sleep(30)

                    if r.status_code != HTTPStatus.OK.value:
                        # password is probably invalid
                        logger.exception("{} - Authorization failed!", username)
                        logger.debug("response: {} - {}", r.status_code, r.text)
                        return
                    else:
                        logger.success("{} - Authorization successful!", username)
                    logger.debug("Obtaining access token...")
                    r = client.get(
                        "https://new.reddit.com/",
                        proxies=proxy.get_random_proxy(self, name),
                    )
                    data_str = (
                        BeautifulSoup(r.content, features="html.parser")
                        .find("script", {"id": "data"})
                        .contents[0][len("window.__r = ") : -1]
                    )
                    data = json.loads(data_str)
                    response_data = data["user"]["session"]

                    if "error" in response_data:
                        logger.error(
                            "An error occured. Make sure you have the correct credentials. Response data: {}",
                            response_data,
                        )
                        exit(1)

                    self.access_tokens[index] = response_data["accessToken"]
                    # access_token_type = data["user"]["session"]["accessToken"]  # this is just "bearer"
                    access_token_expires_in_seconds = response_data[
                        "expiresIn"
                    ]  # this is usually "3600"
                    # access_token_scope = response_data["scope"]  # this is usually "*"

                    # ts stores the time in seconds
                    self.access_token_expires_at_timestamp[
                        index
                    ] = current_timestamp + int(access_token_expires_in_seconds)
                    if not self.compactlogging:
                        logger.debug(
                            "Received new access token: {}************",
                            self.access_tokens.get(index)[:5],
                        )

                # draw pixel onto screen
                if self.access_tokens.get(index) is not None and (
                    current_timestamp >= next_pixel_placement_time
                    or self.first_run_counter <= index
                ):

                    # place pixel immediately
                    # first_run = False
                    self.first_run_counter += 1

                    # get target color
                    # target_rgb = pix[current_r, current_c]

                    # get current pixel position from input image and replacement color
                    current_r, current_c, new_rgb = self.get_unset_pixel(
                        current_r,
                        current_c,
                        index,
                        pix,
                        image_size,
                        self_pixel_x_start,
                        self_pixel_y_start,
                    )

                    # get converted color
                    new_rgb_hex = ColorMapper.rgb_to_hex(new_rgb)
                    pixel_color_index = ColorMapper.COLOR_MAP[new_rgb_hex]

                    logger.info("\nAccount Placing: ", name, "\n")

                    # draw the pixel onto r/place
                    # There's a better way to do this
                    canvas = 0
                    pixel_x_start = self_pixel_x_start + current_r
                    pixel_y_start = self_pixel_y_start + current_c

                    canvas = (3 * math.floor(pixel_x_start / 1000)) + math.floor(pixel_y_start / 1000)

                    # draw the pixel onto r/place
                    next_pixel_placement_time = self.set_pixel_and_check_ratelimit(
                        self.access_tokens[index],
                        pixel_x_start%1000,
                        pixel_y_start%1000,
                        name,
                        pixel_color_index,
                        canvas,
                        index,
                    )

                    current_r = randint(0,image_size[0])
                    current_c = randint(0,image_size[1])

                    # exit when all pixels drawn
                    if current_c >= image_size[1]:
                        logger.info("Thread #{} :: image completed", index)
                        break
            
            if not repeat_forever:
                break

    # Update templates
    def update_templates(self):
        # Reduce CPU usage by looping every 5 minutes
        while not self.stop_event.wait(timeout=300):
            # Get templates
            templates = utils.load_templates(self)
            if templates is None:
                continue
            x_start, y_start, image = templates

            # Update information
            with self.image_lock:
                self.pix = image.load()
                self.image_size = image.size
                self.raw_pixel_x_start = x_start - 500
                self.raw_pixel_y_start = y_start - 500
                self.pixel_x_start = self.raw_pixel_x_start + 1500
                self.pixel_y_start = self.raw_pixel_y_start + 1000

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



@click.command()
@click.option(
    "-d",
    "--debug",
    is_flag=True,
    help="Enable debug mode. Prints debug messages to the console.",
)
@click.option(
    "-c",
    "--config",
    default="config.json",
    help="Location of config.json",
)
def main(debug: bool, config: str):

    if not debug:
        # default loguru level is DEBUG
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    client = PlaceClient(config_path=config)
    # Start everything
    client.start()


if __name__ == "__main__":
    main()
