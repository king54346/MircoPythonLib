# This is a sample Python script.
import time

from machine import Pin
from common.RGB_LED import RGB_LED

from utime import sleep_ms

color_state = 0


def rising_edge_callback(pin):
    global color_state
    pin.irq(trigger=0)  # 禁用中断
    sleep_ms(200)  # 延时200ms
    print("Debounced rising edge detected on pin:", pin)
    color_state = (color_state + 1) % 3
    enable_irq(pin)  # 重新启用中断


def enable_irq(pin):
    pin.irq(trigger=Pin.IRQ_RISING, handler=rising_edge_callback)


if __name__ == '__main__':
    # led
    pin25 = Pin(25, Pin.OUT)
    pin26 = Pin(26, Pin.OUT)
    pin27 = Pin(27, Pin.OUT)
    RGB_LED = RGB_LED(pin25, pin26, pin27)
    # button
    pin23 = Pin(23, Pin.IN, Pin.PULL_DOWN)
    enable_irq(pin23)
    while True:
        if color_state == 0:
            RGB_LED.light_red()
        elif color_state == 1:
            RGB_LED.light_green()
        elif color_state == 2:
            RGB_LED.light_blue()
        sleep_ms(10)  # 可选：添加一个小的延迟以减少CPU使用率
