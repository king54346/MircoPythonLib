class RGB_LED:
    def __init__(self, red_pin, green_pin, blue_pin):
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.blue_pin = blue_pin

    def light_red(self):
        self.red_pin.value(1)
        self.green_pin.value(0)
        self.blue_pin.value(0)

    def light_green(self):
        self.red_pin.value(0)
        self.green_pin.value(1)
        self.blue_pin.value(0)

    def light_blue(self):
        self.red_pin.value(0)
        self.green_pin.value(0)
        self.blue_pin.value(1)

    def light_yellow(self):
        self.red_pin.value(1)
        self.green_pin.value(1)
        self.blue_pin.value(0)

    def light_purple(self):
        self.red_pin.value(1)
        self.green_pin.value(0)
        self.blue_pin.value(1)

    def light_cyan(self):
        self.red_pin.value(0)
        self.green_pin.value(1)
        self.blue_pin.value(1)

    def light_white(self):
        self.red_pin.value(1)
        self.green_pin.value(1)
        self.blue_pin.value(1)
