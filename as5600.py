from machine import SoftI2C, Pin
from micropython import const
from time import sleep_ms

AS5600_ID = const(0x36)  # 设备ID

# 根据数据手册命名寄存器
ZMCO = const(0)
ZPOS = const(1)
MPOS = const(3)
MANG = const(5)
CONF = const(0x7)
RAWANGLE = const(0xC)
ANGLE = const(0xE)
STATUS = const(0x1B)
AGC = const(0x1A)
MAGNITUDE = const(0x1B)
BURN = const(0xFF)

# RAWANGLE：这个寄存器提供的是原始的角度信息，表示0-360°的角度，通常没有进行任何的后处理或滤波。
#
# ANGLE：通常是经过滤波或其他处理的角度数据，可以用于更平滑的应用中。
#
#
#
# ZMCO (Zero Multi-Turn Configuration):
# 寄存器地址: 0x00
# 大小: 8 bits
# 用途: 用于定义零点保存的循环次数。
#
# ZPOS (Zero Position):
# 寄存器地址: 0x01 (高8位) 和 0x02 (低8位)
# 大小: 16 bits
# 用途: 定义零位置的角度，即当传感器测量到该角度时，输出将是0%。
#
# MPOS (Maximum Position):
# 寄存器地址: 0x03 (高8位) 和 0x04 (低8位)
# 大小: 16 bits
# 用途: 定义最大位置的角度，即当传感器测量到该角度时，输出将是100%。
#
# MANG (Maximum Angle):
# 寄存器地址: 0x05 (高8位) 和 0x06 (低8位)
# 大小: 16 bits
# 用途: 定义RAW ANGLE与MPOS之间的角度差，该角度差将对应PWM的最大输出值。


class AS5600:
    def __init__(self, i2c, device_id=AS5600_ID):
        self.i2c = i2c
        self.device_id = device_id

    # 寄存器地址、起始位、结束位和一个用于接收额外参数
    def _readwrite(self, register, firstbit, lastbit, value=None):
        """读写1或2个字节的位字段。(满足所有需求)"""
        # 判断要读取或写入的字节数 如果firstbit大于7（即在第二个字节中），则选择2个字节；否则，只选择1个字节。
        byte_num = 2 if firstbit > 7 else 1
        # 计算需要提取或设置位字段
        mask = (1 << (firstbit - lastbit + 1)) - 1

        # 读取寄存器的当前值
        b = self.i2c.readfrom_mem(self.device_id, register, byte_num)
        # 提取旧值
        oldvalue = ((b[0] << 8) | b[1]) if byte_num == 2 else b[0]
        oldvalue &= mask
        # 没有提供额外的参数（即没有要写入的值），则只返回当前从寄存器读取的值
        if value is None:  # 如果没有提供参数，则只读取
            return oldvalue
        # 如果提供了写入值，首先从args获取该值
        # 获取清除oldvalue中的特定子字段
        hole = ~(mask << lastbit)
        # 新值设置为所需的位
        newvalue = (oldvalue & hole) | ((value & mask) << lastbit)  # 这将所需的值移到正确的位置并且位或操作合并新值
        # 将新值写回寄存器
        if byte_num == 1:
            self.i2c.writeto_mem(self.device_id,register, bytes([newvalue]))
        else:
            high_byte = newvalue >> 8
            low_byte = newvalue & 0xFF
            byte_representation = bytes([high_byte, low_byte])
            # 如果是2个字节，则需要对新值进行分割并将其转换为字节列表 bytes会自动获取低8位
            self.i2c.writeto_mem(self.device_id,register,byte_representation)

        return value

    def zmco(self, value=None):
        """记录零角度被烧录的次数"""
        return self._readwrite(ZMCO, 1, 0, value)

    def zpos(self, value=None):
        """零位置 - 例如当作为电位器使用"""
        return self._readwrite(ZPOS, 11, 0, value)

    def mpos(self, value=None):
        """最大位置 - 例如当作为电位器使用"""
        return self._readwrite(MPOS, 11, 0, value)

    def mang(self, value=None):
        """最大角度（MPOS的替代）"""
        return self._readwrite(MANG, 11, 0, value)

    # PM(1:0)     1:0     Power Mode      00 = NOM, 01 = LPM1, 10 = LPM2, 11 = LPM3
    # HYST(1:0)   3:2     Hysteresis      00 = OFF, 01 = 1 LSB, 10 = 2 LSBs, 11 = 3 LSBs
    # OUTS(1:0)   5:4     Output Stage    00 = analog (full range from 0% to 100% between GND and VDD, 01 = analog (reduced range from 10% to 90% between GND and VDD, 10 = digital PWM
    # PWMF(1:0)   7:6     PWM Frequency   00 = 115 Hz; 01 = 230 Hz; 10 = 460 Hz; 11 = 920 Hz
    # SF(1:0)     9:8     Slow Filter     00 = 16x (1); 01 = 8x; 10 = 4x; 11 = 2x
    # FTH(2:0)    12:10   Fast Filter Threshold   000 = slow filter only, 001 = 6 LSBs, 010 = 7 LSBs, 011 = 9 LSBs,100 = 18 LSBs, 101 = 21 LSBs, 110 = 24 LSBs, 111 = 10 LSBs
    # WD          13      Watchdog        0 = OFF, 1 = ON

    def pm(self, value=None):
        """电源模式 - 参见数据手册"""
        return self._readwrite(CONF, 1, 0, value)

    def hyst(self, value=None):
        """滞后 - 0,1,2或3 LSB"""
        return self._readwrite(CONF, 3, 2, value)

    def outs(self, value=None):
        "PMW vs Analog 0=Analog, 1= PWM"
        return self._readwrite(CONF, 5, 4, value)

    def pwmf(self, value=None):
        "PMW frequency 115,230,460 or 920Hz"
        return self._readwrite(CONF, 7, 6, value)

    def sf(self, value=None):
        "Slow filter value"
        return self._readwrite(CONF, 9, 8, value)

    def fth(self, value=None):
        "Fast filter threshold"
        return self._readwrite(CONF, 12, 10, value)

    def watchdog(self, value=None):
        "Watchdog 0 == OFF< 1 == ON"
        return self._readwrite(CONF, 13, 13, value)

    def raw_angle(self):
        """原始角度，无滤波、缩放等"""
        return self._readwrite(RAWANGLE, 11, 0)

    def angle(self):
        """带有滞后等的角度"""
        return self._readwrite(ANGLE, 11, 0)

    # Status registers - Read only
    def md(self):
        "Magnet detected"
        return self._readwrite(STATUS, 5, 5)

    def ml(self):
        "Magnet too low"
        return self._readwrite(STATUS, 4, 4)

    def mh(self):
        "Magnet too high"
        return self._readwrite(STATUS, 3, 3)

    def agc(self):
        "Automatic gain"
        return self._readwrite(AGC, 7, 0)

    def magnitude(self):
        "? something to do with the CORDIC (?Dont worry about it)"
        return self._readwrite(MAGNITUDE, 11, 0)

        # Read datasheet before using these functions!!!

    # Permanently burn zpos and mpos values into device (Can only use 3 times)
    # 当向这个寄存器写入 0x80 时，ZPOS 和 MPOS 的当前值会被烧录。
    # 当向这个寄存器写入 0x40 时，会烧录 ZPOS、MPOS 和 CONF 寄存器的设置。
    def burn_angle(self):
        "Burn ZPOS and MPOS -(can only do this 3 times)"
        self._readwrite(BURN, 7, 0, 0x80)  # This wrt

    def burn_setting(self):
        "Burn config and mang- (can only do this once)"
        self._readwrite(BURN, 7, 0, 0x40)

    def scan(self):
        """调试工具函数，检查您的i2c总线"""
        devices = self.i2c.scan()
        print(devices)
        if self.device_id in devices:
            print('Found AS5600 (id =', hex(self.device_id), ')')
        # print(self.CONF)


i2c = SoftI2C(scl=Pin(26), sda=Pin(25), freq=400000)

z = AS5600(i2c)
z.scan()

while True:
    print(z.angle())
    sleep_ms(200)
