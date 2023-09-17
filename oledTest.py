from machine import Pin, I2C, RTC, Timer, ADC
import time
import esp32
from common.ssd1306 import SSD1306_I2C

rtc = RTC()
# 定义对应的管脚对象
i2c = I2C(1, scl=Pin(5), sda=Pin(4), freq=400000)

# 创建 OLED 对象
oled = SSD1306_I2C(width=128, height=64, i2c=i2c)

# 清屏
oled.fill(0)


# 画点
# oled.pixel(30, 30, 1)
# oled.pixel(30, 31, 1)
# oled.pixel(30, 32, 1)
# oled.pixel(30, 33, 1)
# oled.pixel(30, 34, 1)
# oled.pixel(30, 35, 1)

# 画方块

# for x in range(30, 61):
#     for y in range(30, 61):
#         oled.pixel(x, y, 1)

def draw_time():
    date_time = rtc.datetime()
    year, month, day, _, hour, minute, second, _ = date_time
    # formatted_time = "{}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(year, month, day, hour, minute, second)
    formatted_time = "{:02d}:{:02d}:{:02d}".format(hour, minute, second)
    # oled.fill(0)
    oled.text(formatted_time, 0, 0)


# 定时器中断
# Timer(0).init(period=1000, mode=Timer.PERIODIC, callback=draw_time)


options = ["time", "temp", "light", "sound"]
selected = 0


def display_menu(selected):
    draw_time()  # 在最上面画出时间
    for i, option in enumerate(options):
        y_position = 10 + i * 10  # 注意这里的偏移，从第二行开始显示
        if i == selected:
            oled.text(">" + str(i + 1) + ". " + option, 0, y_position)
        else:
            oled.text(str(i + 1) + ". " + option, 0, y_position)
    oled.show()


ps_2_x = ADC(Pin(34), atten=ADC.ATTN_11DB)
ps_2_y = ADC(Pin(35), atten=ADC.ATTN_11DB)
# include "soc/ulp_arg.h"


a = """
 data:       .long 0

entry:      move r3, data    # load address of data into r3
            ld r2, r3, 0     # load data contents ([r3+0]) into r2
            add r2, r2, 1    # increment r2
            st r2, r3, 0     # store r2 contents into data ([r3+0])

            halt             # halt ULP co-prozessor (until it gets waked up again)
"""

while True:
    # 读取 Y 轴的值
    y_value = ps_2_y.read()

    # 如果 Y 轴值小于一定阈值，向上滚动
    if y_value < 1000:
        selected = (selected - 1) % len(options)
    # 如果 Y 轴值大于一定阈值，向下滚动
    elif y_value > 3000:
        selected = (selected + 1) % len(options)
    oled.fill(0)
    # 显示当前菜单项
    display_menu(selected)

    # 延迟一段时间，以降低刷新率
    time.sleep(0.2)
