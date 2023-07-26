import click
import sys
from loguru import logger

from place import PlaceClient


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
@click.option(
    "-C",
    "--canvas",
    default="canvas.json",
    help="Location of canvas.json",
)
def main(debug: bool, config: str, canvas: str):
    if not debug:
        # default loguru level is DEBUG
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    client = PlaceClient(config_path=config, canvas_path=canvas)
    # Start everything
    client.start()


if __name__ == "__main__":
    main()
