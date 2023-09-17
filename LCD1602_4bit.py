from machine import Pin
from utime import sleep_ms


class LCD1602_4bit:
    def __init__(self, rs, rw, en, d4, d5, d6, d7):
        self.rs = Pin(rs, Pin.OUT)
        self.rw = Pin(rw, Pin.OUT)
        self.en = Pin(en, Pin.OUT)
        self.data_pins = [Pin(d4, Pin.OUT), Pin(d5, Pin.OUT), Pin(d6, Pin.OUT), Pin(d7, Pin.OUT)]

        self.rw.value(0)  # 设置为写模式
        self.init_lcd()

    def send(self, value, mode):
        self.rs.value(mode)
        self.en.value(0)

        # 发送高4位
        for i in range(4):
            self.data_pins[i].value((value >> (i + 4)) & 0x01)
        self.en.value(1)
        sleep_ms(1)
        self.en.value(0)
        sleep_ms(1)

        # 发送低4位
        for i in range(4):
            self.data_pins[i].value((value >> i) & 0x01)
        self.en.value(1)
        sleep_ms(1)
        self.en.value(0)
        sleep_ms(1)

    def init_lcd(self):
        sleep_ms(50)  # 等待LCD初始化完成
        self.send(0x33, 0)  # 初始化
        self.send(0x32, 0)  # 设置为4位模式
        self.send(0x28, 0)  # 2行, 5x8点阵
        self.send(0x0C, 0)  # 显示开, 光标关
        self.send(0x06, 0)  # 光标移动方向
        self.send(0x01, 0)  # 清屏

    def set_cursor(self, row, col):
        if row == 0:
            self.send(0x80 + col, 0)
        else:
            self.send(0xC0 + col, 0)

    def display_string(self, string, row=0, col=0):
        self.set_cursor(row, col)
        for char in string:
            self.send(ord(char), 1)

