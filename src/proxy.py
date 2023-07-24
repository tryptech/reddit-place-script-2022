import os
import random
import subprocess
import time
from stem import Signal, InvalidArguments, SocketError, ProtocolError
from stem.control import Controller


def Init(self):
    self.proxies = self.config_get("proxies")
    self.proxies = (
        get_proxies(self, self.proxies)
        if self.proxies is not None
        else get_proxies_text(self)
        if os.path.exists(os.path.join(os.getcwd(), "proxies.txt"))
        else None
    )
    self.using_tor = self.config_get("using_tor", False)
    self.tor_password = self.config_get("tor_password", "Passwort")
    self.tor_delay = self.config_get("tor_delay", 10)
    self.use_builtin_tor = self.config_get("use_builtin_tor", True)
    self.tor_port = self.config_get("tor_port", 1881)
    self.tor_control_port = self.config_get("tor_control_port", 9051)
    self.tor_ip = self.config_get("tor_ip", "127.0.0.1")
    print(self.tor_ip)

    # tor connection
    if self.using_tor:
        self.proxies = get_proxies(self, [self.tor_ip + ":" + str(self.tor_port)])
        if self.use_builtin_tor:
            subprocess.Popen(
                '"'
                + os.path.join(os.getcwd(), "./tor/Tor/tor.exe")
                + '"'
                + " --defaults-torrc "
                + '"'
                + os.path.join(os.getcwd(), "./Tor/Tor/torrc")
                + '"'
                + " --HTTPTunnelPort "
                + str(self.tor_port),
                shell=True,
            )
        try:
            self.tor_controller = Controller.from_port(port=self.tor_control_port)
            self.tor_controller.authenticate(self.tor_password)
            self.logger.info("successfully connected to tor!")
        except (ValueError, SocketError):
            self.logger.error("connection to tor failed, disabling tor")
            self.using_tor = False


def get_proxies_text(self):
    path_proxies = os.path.join(os.getcwd(), "proxies.txt")
    f = open(path_proxies)
    file = f.read()
    f.close()
    proxies_list = file.splitlines()
    self.proxies = []
    for i in proxies_list:
        self.proxies.append({"https": i, "http": i})
        self.logger.debug("loaded proxies {} from file {}", i, path_proxies)


def get_proxies(self, proxies):
    proxies_list = []
    for i in proxies:
        proxies_list.append({"https": i, "http": i})

        self.logger.debug("Loaded proxies: {}", str(proxies_list))
        return proxies_list
    return proxies_list


# name is the username of the worker and is used for personal proxies
def get_random_proxy(self, username=None):
    if self.using_tor:
        tor_reconnect(self)
        self.logger.debug("Using Tor. Selecting first proxy: {}.", str(self.proxies[0]))
        return self.proxies[0]
    
    if self.proxies is not None:
        random_proxy = self.proxies[random.randint(0, len(self.proxies) - 1)]
        self.logger.debug("Using proxy: {}", str(random_proxy))
        return random_proxy
    
    proxy = (
        self.config_get("workers")[username].get("personal_proxy")
        if username
        else None
    )

    return {"https": proxy, "http": proxy} if proxy else None


def tor_reconnect(self):
    if self.using_tor:
        try:
            self.tor_controller.signal(Signal.NEWNYM)
            self.logger.info("New Tor connection processing")
            time.sleep(self.tor_delay)
        except (InvalidArguments, ProtocolError):
            self.logger.error("couldn't establish new tor connection, disabling tor")
            self.using_tor = False
