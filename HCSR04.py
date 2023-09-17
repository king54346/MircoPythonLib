import machine, time

trig = machine.Pin(2,machine.Pin.OUT)
echo = machine.Pin(4,machine.Pin.IN)
# 触发：触发（输入）
# 回声：回声（输出）
# 当持续时间至少为10 µS（10微秒）的脉冲施加到触发引脚时 八个超声波脉冲通过空气传播，远离发射器。同时，回声引脚变为高电平，开始形成回声信号的开始。
# 如果这些脉冲没有被反射回来，则回波信号将在38毫秒（38毫秒）后超时并返回低电平。因此38 ms的脉冲表示在传感器范围内没有阻塞。
# 如果这些脉冲被反射回去，则在收到信号后，Echo引脚就会变低。这会产生一个脉冲，其宽度在150 µS至25 mS之间变化，具体取决于接收信号所花费时间。
# 距离=（0.034 cm / µs x 500 µs）/ 2   距离大于30cm，某些表面柔软，反射面呈浅角度 时候不适用
# 声速m / s = 331.4 +（0.606* 温度）+（0.0124 * 湿度）
def distance():
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    while echo.value() == 0:
        pass
    while echo.value() == 1:
        ts = time.ticks_us()
        while echo.value() == 1:
            pass
        te = time.ticks_us()
        tc = te - ts
        distance = round((tc*170)/10000, 2)
    return distance

while True:
    dist = distance()
    print('distance:', dist, 'cm')
    time.sleep(2)