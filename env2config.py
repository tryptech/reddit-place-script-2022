import json
import os
from dotenv import load_dotenv

load_dotenv()

toJSON = {
    "thread_delay": 3,
    "proxies": None,
    "workers": {},
}

for i in range(len(json.loads(os.getenv("ENV_PLACE_USERNAME")))):
    toJSON["workers"][json.loads(os.getenv("ENV_PLACE_USERNAME"))[i]] = {
        "password": json.loads(os.getenv("ENV_PLACE_PASSWORD"))[i],
        "client_id": json.loads(os.getenv("ENV_PLACE_APP_CLIENT_ID"))[i],
        "client_secret": json.loads(os.getenv("ENV_PLACE_SECRET_KEY"))[i],
        "start_coords": [
            int(json.loads(os.getenv("ENV_R_START"))[i]),
            int(json.loads(os.getenv("ENV_C_START"))[i]),
        ],
    }

with open("config.json", "w") as outfile:
    json.dump(toJSON, outfile, sort_keys=True, indent=4)
