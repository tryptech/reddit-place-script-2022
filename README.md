# ROBOCO

[![Code style: black](./black_badge.svg)](https://github.com/psf/black)
[![forthebadge](https://forthebadge.com/images/badges/made-with-python.svg)](https://forthebadge.com)
[![forthebadge](https://forthebadge.com/images/badges/60-percent-of-the-time-works-every-time.svg)](https://forthebadge.com)

## Thanks to everyone who contributed! r/place is now over

<a href="https://github.com/tryptech/roboco/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=tryptech/roboco" />
</a>

## About

This is a script to draw images from a json template onto r/place (<https://www.reddit.com/r/place/>).

It has adapted r/place in 2023.

## Features

- Support for multiple accounts.
- Supports multiple .json templates as defined in [templateManager](https://github.com/osuplace/templateManager).
- Manual/automatic prioritization of specific templates.
- Automatically updates accounts list and templates.
- Determines the cooldown time remaining for each account.
- Detects existing matching pixels on the r/place map and skips them.
- Automatically converts colors to the r/place color palette.
- Prioritizes pixels based on perceptual difference to template.
- Easy(ish) to read output with colors.
- SOCKS proxy support.
- No client id and secret needed.
- Proxies from "proxies.txt" file.
- Tor support.

## Requirements

- [Python 3.10](https://www.python.org/downloads/)

## Get Started

Move the file `"config_example.json"` to `"config.json"`

Edit the values to replace with actual credentials and values

Note: Please use <https://jsonlint.com/> to check that your JSON file is correctly formatted

```json
{
    "template_urls": [
        "https://url.to.the.template1.png",
        "https://url.to.the.template2.png"
    ],
    "priority_url": "https://url.to.the.template3.png",
    "names": ["template1_name1", "template1_name2", "template2_name1"],
    "workers": {
        "username": "password"
    }
}
```

- `template_urls` - a list of URLs to the template overlays.
- `priority_url` - a URL to a priority template with a filtered list of sources from `"template_urls"`.
- `names` - a list of template names to use from the template overlay. If empty, all templates will be used. `priority_url` will override this.
- `workers` - an array of accounts to use. Each account has a password. You can add as many accounts as you want, but reddit may detect you the more you add.
- ~~If you use 2 factor authentication (2FA) in your account, then change `password` to `password:XXXXXX` where `XXXXXX` is your 2FA code.~~ This no longer appears to work.

## Run the Script

### Windows

```shell
start.bat or startverbose.bat
```

### Unix-like (Linux, macOS etc.)

```shell
chmod +x start.sh startverbose.sh
./start.sh or ./startverbose.sh
```

### Python

You can get more logs (`DEBUG`) by running the script with `-d` flag:

```shell
python3 main.py -d
python3 main.py --debug
```

#### **Notes**

If you want to use tor on macOS. you'll need to provide your own tor binary or install it via [Homebrew](https://brew.sh) using ``brew install tor``, and start it manually.

Make sure to deactivate the "use_builtin tor"
option in the config and configure your tor to use the correct ports and password.

*Please note that socks proxy connection to tor doesn't work for the time
being, so the config value is for an httpTunnel port*

## Multiple Workers

Just create multiple child arrays to `"workers"` in the .json file:

```json
"workers": {
    "username1": "password1",
    "username2": "password2"
}
```

In this case, both workers will draw random pixels onto r/place that are different from the template image.

## Other Settings

If any JSON decoders errors are found, the `config.json` needs to be fixed. Make sure to add the below 2 lines in the file.

```json
"thread_delay": 2,
"proxies": ["1.1.1.1:8080", "2.2.2.2:1234"]
```

- `thread_delay` - the delay between starting threads and board updates. Setting to `0` is not recommended.
- `proxies` - Sets proxies to use for sending requests to reddit. The proxy used is randomly selected for each request. Can be used to avoid ratelimiting.
- You can also setup proxies by creating a "proxies" and have a new line for each proxies.

## Tor

Tor can be used as an alternative to normal proxies. Note that currently, you cannot use normal proxies and tor at the same time.

```json
"using_tor": false,
"tor_ip": "127.0.0.1",
"tor_port": 1881,
"tor_control_port": 9051,
"tor_password": "Passwort",
"tor_delay": 5,
"use_builtin_tor": true
```

The config values are as follows:

- Deactivates or activates tor.
- Sets the ip/hostname of the tor proxy to use
- Sets the httptunnel port that should be used.
- Sets the tor control port.
- Sets the password. (Leave it as "Passwort" if you want to use the default binaries.)
- The delay that tor should receive to process a new connection.
- Whether the included tor binary should be used. It is preconfigured. If you want to use your own binary, make sure you configure it properly.

Note that when using the included binaries, only the tunnel port is explicitly set while starting tor.

If you want to use your own binaries, follow these steps:

- Get tor standalone for your platform [here](https://www.torproject.org/download/tor/). For Windows just use the expert bundle. For macOS, you can use [Homebrew](https://brew.sh) to install tor: ``brew install tor``.
- In your tor folder, create a file named ``torrc``. Copy [this](https://github.com/torproject/tor/blob/main/src/config/torrc.sample.in) into it.
- Search for ``ControlPort`` in your torrc file and uncomment it. Change the port number to your desired control port.
- Decide on the password you want to use. Run ``tor --hash-password PASSWORD`` from a terminal in the folder with your tor executable, with "PASSWORD" being your desired password. Copy the resulting hash.
- Search for ``HashedControlPassword`` and uncomment it. Paste the hash value you copied after it.
- Decide on a port for your httptunnel. The default for this script is 1881.
- Fill in your password, your httptunnel port and your control port in this script's ``config.json`` and enable tor with ``using_tor = true``.
- To start tor, run ``tor --defaults-torrc PATHTOTORRC --HttpTunnelPort TUNNELPORT``, with PATHTOTORRC being your path to the torrc file you created and TUNNELPORT being your httptunnel port.
- Now run the script and (hopefully) everything should work.

License for the included tor binary:

> Tor is distributed under the "3-clause BSD" license, a commonly used
software license that means Tor is both free software and open source:
Copyright (c) 2001-2004, Roger Dingledine
Copyright (c) 2004-2006, Roger Dingledine, Nick Mathewson
Copyright (c) 2007-2019, The Tor Project, Inc.
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:
>
>- Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.
>- Redistributions in binary form must reproduce the above
copyright notice, this list of conditions and the following disclaimer
in the documentation and/or other materials provided with the
distribution.
>- Neither the names of the copyright owners nor the names of its
contributors may be used to endorse or promote products derived from
this software without specific prior written permission.
>
>THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## Docker

A dockerfile is provided. Instructions on installing docker are outside the scope of this guide.

- After editing the `config.json` file,  build the image

```sh
docker build -t place-bot .
```

> Note: You can use the option `--build-arg` to specify a configuration file

```sh
docker build -t place-bot --build-arg CONFIG=custom_config.json .
```

- You can now run it with `docker run place-bot`

## Contributing

See the [Contributing Guide](docs/CONTRIBUTING.md).
