from machine import Pin
from utime import sleep_ms


class LCD1602_8bit:
    def __init__(self, rs, en, d0, d1, d2, d3, d4, d5, d6, d7):
        self.rs = Pin(rs, Pin.OUT)
        self.en = Pin(en, Pin.OUT)
        self.data_pins = [Pin(d0, Pin.OUT), Pin(d1, Pin.OUT), Pin(d2, Pin.OUT),
                          Pin(d3, Pin.OUT), Pin(d4, Pin.OUT), Pin(d5, Pin.OUT),
                          Pin(d6, Pin.OUT), Pin(d7, Pin.OUT)]
        self.clear()
        self.init_lcd()

    def send(self, value, mode):
        self.rs.value(mode)
        self.en.value(0)

        for i in range(8):
            self.data_pins[i].value((value >> i) & 0x01)

        self.en.value(1)
        sleep_ms(1)
        self.en.value(0)

    def clear(self):
        self.send(0x01, 0)

    def init_lcd(self):
        self.send(0x38, 0)  # 8-bit mode, 2 line, 5x8 dots
        self.send(0x06, 0)  # Cursor move direction
        self.send(0x0C, 0)  # Turn cursor off
        self.clear()

    def set_cursor(self, row, col):
        if row == 0:
            self.send(0x80 + col, 0)
        else:
            self.send(0xC0 + col, 0)

    def display_string(self, string, row=0, col=0):
        self.set_cursor(row, col)
        for char in string:
            self.send(ord(char), 1)


