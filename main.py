import gc
import time

import network
from machine import ADC, DEEPSLEEP_RESET, SPI, WDT, Pin, deepsleep, reset_cause

import config
from iot import rtc_mem
from iot.calibration import interpolate
from iot.ha import HA
from iot.pcd8544_flip import LCD
from iot.wifi import connect

SPI_RATE = 2_000_000
POLL_INTERVAL_SECONDS = 600
DRIVE = Pin.DRIVE_0


def DrivePin(pin_id, *args, **kwargs):
    return Pin(pin_id, *args, drive=DRIVE, **kwargs)


def mem_info(lcd):
    alloc = gc.mem_alloc() // 1024
    total = (gc.mem_alloc() + gc.mem_free()) // 1024
    lcd.log(f"m:{alloc}/{total}")


def enable_external_antenna():
    _rf_switch_power = Pin(3, mode=Pin.OUT, value=0)
    _select_external_antenna = Pin(14, mode=Pin.OUT, value=1)


def get_battery_level(adc, bat_voltage_cal, bat_percentage_cal):
    adc.read_u16()  # discard first sample just in case

    num_samples = 200
    v_sum = 0
    for x in range(num_samples):
        _v = adc.read_u16()
        v_sum += _v
    adc_voltage = v_sum / num_samples

    bat_voltage = interpolate(bat_voltage_cal, adc_voltage)
    bat_percentage = interpolate(bat_percentage_cal, bat_voltage)

    return int(bat_percentage), bat_voltage


def main():
    # WATCHDOG
    WDT(timeout=30_000)

    # SET UP
    coldboot = reset_cause() != DEEPSLEEP_RESET
    sleep_duration = POLL_INTERVAL_SECONDS
    backlight_num_blinks = 0
    state = rtc_mem.recall()

    if coldboot:
        sleep_duration = 10
        backlight_num_blinks = 5

    # ACTIVITY LED
    Pin(15, mode=Pin.OUT, value=0)  # goes off in sleep by itself

    # BACKLIGHT
    print("initialize backlight")
    backlight = Pin(0, mode=Pin.OUT, drive=Pin.DRIVE_0, hold=False)
    if coldboot:
        for x in range(backlight_num_blinks):
            backlight.value(not backlight.value())
            time.sleep(0.1)
    backlight.on()

    # LCD_SPI
    sck = DrivePin(16)
    mosi = DrivePin(23)
    spi = SPI(1, sck=sck, mosi=mosi)
    spi.init(baudrate=SPI_RATE, polarity=0, phase=0)

    # LCD
    cs = DrivePin(22, hold=False)
    dc = DrivePin(21)
    rst = DrivePin(2, hold=False)
    lcd = LCD(spi, cs, dc, rst, flip=True, echo=True)
    lcd.clear()

    # DEEP SLEEP
    def sleep(interval):
        # holding pin state during sleep for the following reasons:
        # backlight to keep backlight on
        # rst so display is not reset when going to sleep
        # cs so that no garbage on display screen on next wake up
        backlight.init(hold=True)
        rst.init(hold=True)
        cs.init(hold=True)

        deepsleep(interval)

    # ADC
    adc = ADC(1, atten=ADC.ATTN_0DB)
    if coldboot:
        lcd.log("cold delay")
        time.sleep(10)
    bat_percentage, bat_voltage = get_battery_level(
        adc,
        config.BAT_VOLTAGE_CAL,
        config.BAT_PERCENTAGE_CAL,
    )
    lcd.log(f"B:{bat_percentage}% {bat_voltage:.2f}V")

    bat_charged = True
    if bat_percentage < 20:
        bat_charged = False
    if bat_voltage < 3.45:
        sleep_dur_minutes = 20
        lcd.clear()
        lcd.log("plz charge")
        lcd.log(f"bat: {bat_percentage}%")
        lcd.log(f"bat: {bat_voltage:.2f}V")
        lcd.log("plz charge")
        lcd.log(f"(sleeping {sleep_dur_minutes}m)")
        sleep(sleep_dur_minutes * 60 * 1000, bl=backlight, rst=rst, cs=cs)

    # RECALL PREVIOUS STATE
    if state:
        lcd.log("old state:")
        lcd.log(f"{state['temp']:.2f}C")
        lcd.log(f"{state['ts']}")
    # WIFI
    enable_external_antenna()
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

        connect(
            wlan,
            hostname=config.HOSTNAME,
            netcreds=config.WIFI_CREDS,
        )
    except Exception as _err:
        lcd.log("wifi fiasco")
        sleep(10_000)

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
    lcd.clear()
    lcd.log(f"{temperature:.2f}C")
    lcd.log("")
    lcd.log(f"{time_now}")
    lcd.log(f"{bat_percentage}% {bat_voltage:.2f}")

    # STORE CURRENT STATE
    rtc_mem.store({"temp": temperature, "ts": time_now})

    # DEINIT
    wlan.disconnect()
    wlan.active(False)

    # GO TO DEEP SLEEP
    if bat_charged:
        lcd.log(f"Zzz {sleep_duration//60}min")
    else:
        lcd.log("PLZ CHARGE!")

    sleep(sleep_duration * 1000)


if __name__ == "__main__":
    main()
