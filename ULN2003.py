import time
from machine import Pin

a = Pin(13, Pin.OUT)
b = Pin(12, Pin.OUT)
c = Pin(14, Pin.OUT)
d = Pin(27, Pin.OUT)

delay_time = 2  # 这个时间不能设置太小，否则电机来不及响应

print("单四拍模式")
for i in range(256):  # 顺时针转动180度
    a.value(1)
    b.value(0)
    c.value(0)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(1)
    c.value(0)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(0)
    c.value(1)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(0)
    c.value(0)
    d.value(1)
    time.sleep_ms(delay_time)

# 改变脉冲的顺序， 可以方便的改变转动的方向
for i in range(256):  # 逆时针转动转动180度
    a.value(0)
    b.value(0)
    c.value(0)
    d.value(1)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(0)
    c.value(1)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(1)
    c.value(0)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(1)
    b.value(0)
    c.value(0)
    d.value(0)
    time.sleep_ms(delay_time)

# 双四拍模式
print("双四拍模式")
for i in range(256):  # 顺时针转动 180 度
    a.value(1)
    b.value(1)
    c.value(0)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(1)
    c.value(1)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(0)
    c.value(1)
    d.value(1)
    time.sleep_ms(delay_time)

    a.value(1)
    b.value(0)
    c.value(0)
    d.value(1)
    time.sleep_ms(delay_time)

print('八拍模式')
for i in range(256):
    a.value(1)
    b.value(0)
    c.value(0)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(1)
    b.value(1)
    c.value(0)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(1)
    c.value(0)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(1)
    c.value(1)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(0)
    c.value(1)
    d.value(0)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(0)
    c.value(1)
    d.value(1)
    time.sleep_ms(delay_time)

    a.value(0)
    b.value(0)
    c.value(0)
    d.value(1)
    time.sleep_ms(delay_time)

    a.value(1)
    b.value(0)
    c.value(0)
    d.value(1)
    time.sleep_ms(delay_time)

# 步进电机停止后需要使四个相位引脚都为低电平，否则步进电机会发热
a.value(0)
b.value(0)
c.value(0)
d.value(0)
