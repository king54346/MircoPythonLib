from machine import I2C, Pin
from micropython import const
from time import sleep

AS5600_ID = const(0x36)  # �豸ID

# ���������ֲ������Ĵ���
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


class AS5600:
    def __init__(self, i2c, device_id=AS5600_ID):
        self.i2c = i2c
        self.device_id = device_id

    # �Ĵ�����ַ����ʼλ������λ��һ�����ڽ��ն������
    def _readwrite(self, register, firstbit, lastbit, *args):
        """��д1��2���ֽڵ�λ�ֶΡ�(������������)"""
        # �ж�Ҫ��ȡ��д����ֽ��� ���firstbit����7�����ڵڶ����ֽ��У�����ѡ��2���ֽڣ�����ֻѡ��1���ֽڡ�
        byte_num = 2 if firstbit > 7 else 1
        # ������Ҫ��ȡ������λ�ֶ�
        mask = 1 << (firstbit - lastbit + 1) - 1
        # ��ȡ�Ĵ����ĵ�ǰֵ
        b = self.i2c.readfrom(register, byte_num)
        # ��ȡ��ֵ
        oldvalue = b[1] << 8 + b[0] if byte_num == 2 else b[0]
        oldvalue &= mask
        # û���ṩ����Ĳ�������û��Ҫд���ֵ������ֻ���ص�ǰ�ӼĴ�����ȡ��ֵ
        if not args:  # ���û���ṩ��������ֻ��ȡ
            return oldvalue
        # ����ṩ��д��ֵ�����ȴ�args��ȡ��ֵ
        value = args[0]
        # ��ȡ���oldvalue�е��ض����ֶ�
        hole = ~(mask << lastbit)
        # ��ֵ����Ϊ�����λ
        newvalue = (oldvalue & hole) | ((value & mask) << lastbit)  # �⽫�����ֵ�Ƶ���ȷ��λ�ò���λ������ϲ���ֵ
        # ����ֵд�ؼĴ���
        if byte_num == 1:
            self.i2c.writeto(register, bytes([newvalue]))
        else:
            # �����2���ֽڣ�����Ҫ����ֵ���зָ����ת��Ϊ�ֽ��б� bytes���Զ���ȡ��8λ
            self.i2c.writeto(register, bytes([newvalue >> 8, newvalue]))

        return value

    def zmco(self, value=None):
        """��¼��Ƕȱ���¼�Ĵ���"""
        return self._readwrite(ZMCO, 1, 0, value)

    def zpos(self, value=None):
        """��λ�� - ���統��Ϊ��λ��ʹ��"""
        return self._readwrite(ZPOS, 11, 0, value)

    def mpos(self, value=None):
        """���λ�� - ���統��Ϊ��λ��ʹ��"""
        return self._readwrite(MPOS, 11, 0, value)

    def mang(self, value=None):
        """���Ƕȣ�MPOS�������"""
        return self._readwrite(MANG, 11, 0, value)

    # PM(1:0)     1:0     Power Mode      00 = NOM, 01 = LPM1, 10 = LPM2, 11 = LPM3
    # HYST(1:0)   3:2     Hysteresis      00 = OFF, 01 = 1 LSB, 10 = 2 LSBs, 11 = 3 LSBs
    # OUTS(1:0)   5:4     Output Stage    00 = analog (full range from 0% to 100% between GND and VDD, 01 = analog (reduced range from 10% to 90% between GND and VDD, 10 = digital PWM
    # PWMF(1:0)   7:6     PWM Frequency   00 = 115 Hz; 01 = 230 Hz; 10 = 460 Hz; 11 = 920 Hz
    # SF(1:0)     9:8     Slow Filter     00 = 16x (1); 01 = 8x; 10 = 4x; 11 = 2x
    # FTH(2:0)    12:10   Fast Filter Threshold   000 = slow filter only, 001 = 6 LSBs, 010 = 7 LSBs, 011 = 9 LSBs,100 = 18 LSBs, 101 = 21 LSBs, 110 = 24 LSBs, 111 = 10 LSBs
    # WD          13      Watchdog        0 = OFF, 1 = ON

    def pm(self, value=None):
        """��Դģʽ - �μ������ֲ�"""
        return self._readwrite(CONF, 1, 0, value)

    def hyst(self, value=None):
        """�ͺ� - 0,1,2��3 LSB"""
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
        """ԭʼ�Ƕȣ����˲������ŵ�"""
        return self._readwrite(RAWANGLE, 11, 0)

    def angle(self):
        """�����ͺ�ȵĽǶ�"""
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
    # ��������Ĵ���д�� 0x80 ʱ��ZPOS �� MPOS �ĵ�ǰֵ�ᱻ��¼��
    # ��������Ĵ���д�� 0x40 ʱ������¼ ZPOS��MPOS �� CONF �Ĵ��������á�
    def burn_angle(self):
        "Burn ZPOS and MPOS -(can only do this 3 times)"
        self._readwrite(BURN, 7, 0, 0x80)  # This wrt

    def burn_setting(self):
        "Burn config and mang- (can only do this once)"
        self._readwrite(BURN, 7, 0, 0x40)

    def scan(self):
        """���Թ��ߺ������������i2c����"""
        devices = self.i2c.scan()
        print(devices)
        if self.device_id in devices:
            print('Found AS5600 (id =', hex(self.device_id), ')')
        print(self.CONF)


i2c = I2C(0, scl=Pin(17), sda=Pin(16), freq=400000)

z = AS5600(i2c)
z.scan()
whatever = 89
while True:
    print(z.MD)
    sleep(1)
