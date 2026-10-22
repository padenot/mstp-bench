"""Launch browsers through WebDriver. Selenium Manager provides the drivers."""
import os

from selenium import webdriver


def launch(browser: str, binary: str | None = None, realtime: bool = True):
    """Start a fresh browser process, headless except for Safari.

    browser   "chrome", "firefox" or "safari". Safari needs
              `sudo safaridriver --enable` and Develop ▸ Allow Remote Automation.
    binary    browser executable; defaults to the installed Chrome. Firefox
              needs a build with the patches listed in firefox/README.md.
    realtime  Firefox only: False disables real-time scheduling of sinkless
              AudioContext rendering (a control for the contention test).
    """
    if browser == "chrome":
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--autoplay-policy=no-user-gesture-required")
        # Gather plain host ICE candidates; the harness relays SDP itself.
        options.add_argument("--disable-features=WebRtcHideLocalIpsWithMdns")
        if binary:
            options.binary_location = binary
        driver = webdriver.Chrome(options=options)
    elif browser == "firefox":
        if not binary:
            raise ValueError("Firefox needs --firefox pointing to a patched build (see firefox/README.md)")
        options = webdriver.FirefoxOptions()
        options.binary_location = binary
        options.add_argument("-headless")
        for name, value in {
            "media.setsinkid.enabled": True,
            "media.autoplay.default": 0,  # Allow audio without a user gesture.
            "media.autoplay.block-webaudio": False,
            "media.peerconnection.ice.obfuscate_host_addresses": False,
        }.items():
            options.set_preference(name, value)
        env = {k: v for k, v in os.environ.items() if k != "MOZ_DISABLE_SINKLESS_RT"}
        if not realtime:
            env["MOZ_DISABLE_SINKLESS_RT"] = "1"
        driver = webdriver.Firefox(options=options, service=webdriver.FirefoxService(env=env))
    elif browser == "safari":
        driver = webdriver.Safari()
    else:
        raise ValueError(f"Unsupported browser: {browser}")
    driver.set_script_timeout(60)
    return driver


def describe(driver) -> dict:
    caps = driver.capabilities
    return {"name": caps["browserName"], "version": caps["browserVersion"], "build": caps.get("moz:buildID")}
