# 引脚定义
# 1. gnd  red yellow
from machine import Pin



class double_led:
    def __init__(self, pin1, pin2):
        self.pin1 = pin1
        self.pin2 = pin2

    def light_red(self):
        self.pin1.value(1)
        self.pin2.value(0)

    def light_yellow(self):
        self.pin1.value(0)
        self.pin2.value(1)

    def light_off(self):
        self.pin1.value(0)
        self.pin2.value(0)

    def light_orange(self):
        self.pin1.value(1)
        self.pin2.value(1)