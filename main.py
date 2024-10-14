import gc
import time

import config
import network
from machine import ADC, SPI, WDT, Pin, deepsleep

from iot.calibration import interpolate
from iot.flip_screen import LCD
from iot.ha import HA
from iot.wifi import connect


def mem_info(lcd):
    alloc = gc.mem_alloc() // 1024
    total = (gc.mem_alloc() + gc.mem_free()) // 1024
    lcd.log(f"m:{alloc}/{total}")


def enable_external_antenna():
    rf_switch_power = Pin(3, mode=Pin.OUT, value=0)
    time.sleep(0.1)
    external_antenna = Pin(14, mode=Pin.OUT, value=1)


def sleep(interval, bl, rst, cs):
    # HOLD:
    # backlight to keep backlight on
    # rst so display is not reset when going to sleep
    # cs so that no garbage on display screen on next wake up
    bl.init(hold=True)
    rst.init(hold=True)
    cs.init(hold=True)

    deepsleep(interval)


def get_battery_level(adc, bat_voltage_cal, bat_percentage_cal):
    adc.read_uv()  # discard first sample just in case

    measurements = []
    for x in range(20):
        _v = adc.read_uv() // 1000
        measurements.append(_v)
        time.sleep_ms(25)  # let capacitor restore charge
    adc_voltage = sum(measurements) / len(measurements) / 1000

    bat_voltage = interpolate(bat_voltage_cal, adc_voltage)
    bat_percentage = interpolate(bat_percentage_cal, bat_voltage)

    return int(bat_percentage)


def main():
    # WATCHDOG
    # TODO
    watchdog = WDT(timeout=20_000)

    # ACTIVITY LED
    led = Pin(15, mode=Pin.OUT, value=0)  # goes off in sleep by itself

    # BACKLIGHT
    print("initialize backlight")
    backlight = Pin(1, mode=Pin.OUT, drive=Pin.DRIVE_0, hold=False)
    for x in range(10):
        backlight.value(not backlight.value())
        time.sleep(0.1)
    backlight.on()

    # LCD_SPI
    spi = SPI(1, sck=16, mosi=23)
    spi.init(baudrate=8_000_000, polarity=0, phase=0)

    # LCD
    cs = Pin(22, hold=False)
    dc = Pin(21)
    rst = Pin(2, hold=False)
    lcd = LCD(spi, cs, dc, rst, echo=True)
    lcd.clear()

    # ADC
    adc = ADC(0, atten=ADC.ATTN_11DB)
    bat_percentage = get_battery_level(
        adc, config.BAT_VOLTAGE_CAL, config.BAT_PERCENTAGE_CAL
    )
    lcd.log(f"bat: {bat_percentage}%")
    bat_charged = True
    if bat_percentage < 20:
        bat_charged = False
    if bat_percentage < 10:
        lcd.clear()
        lcd.log("bat. dead")
        lcd.log("bat. dead")
        lcd.log("bat. dead")
        sleep(None, bl=backlight, rst=rst, cs=cs)

    # WIFI
    lcd.log("connecting")
    try:
        wlan = network.WLAN(network.STA_IF)

        # # PRINT WIFI RSSI
        # wlan.active(True)
        # for ap in wlan.scan():
        #     ssid, bssid, channel, RSSI, security, hidden = ap
        #     if str(ssid) == config.WIFI_CREDS[0]:
        #         print(RSSI)
        # lcd.log(f"RSSI: {RSSI}")

        ip = connect(
            wlan,
            hostname=config.HOSTNAME,
            netcreds=config.WIFI_CREDS,
        )
    except Exception as err:
        lcd.log("wifi fiasco")
        sleep(5_000, bl=backlight, rst=rst, cs=cs)
    # TODO: handle connection error

    # HA
    lcd.log("home ass.")
    ha = HA(
        outdoor_sensor_id=config.OUTDOOR_SENSOR_ID,
        date_time_sensor_id=config.DATE_TIME_ID,
        ha_token=config.HA_TOKEN,
        base_url=config.HA_BASE_URL,
    )
    date, time_now = ha.get_local_date_time()
    temperature = ha.get_outdoor_temp()

    # MAIN SCREEN
    lcd.log("clear")
    lcd.clear()
    lcd.log(f"{temperature}C")
    lcd.log(f"{time_now}")
    lcd.log(f"bat: {bat_percentage}%")
    if not bat_charged:
        lcd.log("plz charge")

    # DEEP SLEEP
    lcd.log("sleeping....")
    sleep(10_000, bl=backlight, rst=rst, cs=cs)


if __name__ == "__main__":
    main()
