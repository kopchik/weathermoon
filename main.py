import gc
import time

import esp32
import machine
import network
from machine import SPI, Pin, deepsleep

import config
from iot.wifi import connect
from iot.ha import HA


def main():
    # BACKLIGHT
    print("initialize backlight")
    bl = Pin(16, mode=Pin.OUT, drive=Pin.DRIVE_0)
    for x in range(1):
        bl.value(not bl.value())
        time.sleep(0.1)
    bl.on()

    # WIFI
    print("WLAN")
    wlan = network.WLAN(network.STA_IF)
    print(f"WLAN STATUS: {wlan.isconnected()}")
    ip = connect(
        wlan,
        hostname=config.HOSTNAME,
        netcreds=config.WIFI_CREDS,
    )
    print(ip)
    # TODO: handle connection error

    # HA
    ha = HA(
        outdoor_sensor_id=config.OUTDOOR_SENSOR_ID,
        date_time_sensor_id=config.DATE_TIME_ID,
        ha_token=config.HA_TOKEN,
        base_url=config.HA_BASE_URL,
    )

    print(ha.get_date_time())
    print(ha.get_outdoor_temp())


if __name__ == "__main__":
    main()
