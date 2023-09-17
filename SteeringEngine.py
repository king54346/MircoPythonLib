'''
该程序作用是使用 PWM 模块控制舵机转动
在线文档：https://docs.geeksman.com/
'''

import time
from machine import Pin, PWM

# 定义舵机控制对象
my_servo = PWM(Pin(15))
# 定义舵机频率
my_servo.freq(50)

# 使用不同方法控制转动角度

# 使用 duty() 方法转动到 0°，duty 方法的范围是 0-1023，
# 因此，参数值为 [0.5/(20/1023)] 取整等于 25
my_servo.duty(25)
time.sleep(2)

# 使用 duty_u16() 方法转动到 90°，duty_u16 方法的范围是 0-65535，
# 因此，参数值为 65535 // 20 * 1.5 取整等于 4915
# my_servo.duty_u16(int(65535//20*2.5))
# time.sleep(2)
