import machine

PINS = {"sck": 16, "mosi": 23, "cs": 22, "dc": 21, "rst": 2}

machine.WDT(timeout=100_000)

for name, pin_id in PINS.items():
    print("processing pin", name)
    pin = machine.Pin(pin_id, hold=False)
    pwm = machine.PWM(pin, freq=5000, duty=512)
    input("press ENTER to stop")
    pwm.deinit()
