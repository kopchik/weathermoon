import gc
import time

import config
import network
from machine import ADC, SPI, WDT, Pin, deepsleep

from iot.calibration import interpolate
from iot.pcd8544_flip import LCD
from iot.ha import HA
from iot.wifi import connect

def mem_info(lcd):
    alloc = gc.mem_alloc() // 1024
    total = (gc.mem_alloc() + gc.mem_free()) // 1024
    lcd.log(f"m:{alloc}/{total}")


def enable_external_antenna():
    rf_switch_power = Pin(3, mode=Pin.OUT, value=0)
    time.sleep(0.05)
    external_antenna = Pin(14, mode=Pin.OUT, value=1)
    time.sleep(0.05)


def sleep(interval, bl, rst, cs):
    # holding pin state during sleep for the following reasons:
    # backlight to keep backlight on
    # rst so display is not reset when going to sleep
    # cs so that no garbage on display screen on next wake up
    bl.init(hold=True)
    rst.init(hold=True)
    cs.init(hold=True)

    deepsleep(interval)


def get_battery_level(adc, bat_voltage_cal, bat_percentage_cal):
    adc.read_u16()  # discard first sample just in case

    num_samples = 400
    v_sum = 0
    for x in range(num_samples):
        _v = adc.read_u16()
        v_sum += _v
        # time.sleep_ms(50)  # let capacitor restore charge
    adc_voltage = v_sum / num_samples

    bat_voltage = interpolate(bat_voltage_cal, adc_voltage)
    bat_percentage = interpolate(bat_percentage_cal, bat_voltage)

    return int(bat_percentage), bat_voltage


def main():
    # WATCHDOG
    # TODO watchdog = WDT(timeout=20_000)

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
    DRIVE = Pin.DRIVE_0
    SPI_RATE = 2_000_000
    sck = Pin(16, drive=DRIVE)
    mosi = Pin(23, drive=DRIVE)
    spi = SPI(1, sck=sck, mosi=mosi)
    spi.init(baudrate=SPI_RATE, polarity=0, phase=0)

    # LCD
    cs = Pin(22, hold=False, drive=DRIVE)
    dc = Pin(21, drive=DRIVE)
    rst = Pin(2, hold=False, drive=DRIVE)
    lcd = LCD(spi, cs, dc, rst, flip=True, echo=True)
    lcd.clear()

    # ADC
    adc = ADC(1, atten=ADC.ATTN_0DB)
    time.sleep(1)
    bat_percentage, bat_voltage = get_battery_level(
        adc,
        config.BAT_VOLTAGE_CAL,
        config.BAT_PERCENTAGE_CAL,
    )
    lcd.log(f"bat: {bat_percentage}%")
    lcd.log(f"bat: {bat_voltage:.2f}V")

    bat_charged = True
    if bat_percentage < 20:
        bat_charged = False
    if bat_voltage < 3.45:
        sleep_dur = 10
        lcd.clear()
        lcd.log("plz charge")
        lcd.log(f"bat: {bat_percentage}%")
        lcd.log(f"bat: {bat_voltage:.2f}V")
        lcd.log("plz charge")
        lcd.log(f"(sleeping {sleep_dur}s)")
        # sleep(1800_000, bl=backlight, rst=rst, cs=cs)
        sleep(sleep_dur * 1000, bl=backlight, rst=rst, cs=cs)

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

        ip = connect(
            wlan,
            hostname=config.HOSTNAME,
            netcreds=config.WIFI_CREDS,
        )
    except Exception as err:
        lcd.log("wifi fiasco")
        sleep(5_000, bl=backlight, rst=rst, cs=cs)

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
    lcd.log(f"{bat_percentage}% {bat_voltage:.2f}")
    if not bat_charged:
        lcd.log("PLZ CHARGE!")

    # DEINIT
    wlan.disconnect()
    wlan.active(False)

    # DEEP SLEEP
    lcd.log("sleeping....")
    sleep(10_000, bl=backlight, rst=rst, cs=cs)


if __name__ == "__main__":
    main()
