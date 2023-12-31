import math
from machine import I2C, Pin
import time

from common.MPU6050 import MPU6050

# 115200波特率 ，加速度，角速度，姿态角 温度
# 另外还有aux_cl和aux_da 用于连接外部设备，如磁传感器这样就组成九轴传感器
# vd0是地址控制引脚，悬空0x68高电平是0x69
# 0x6b 电源管理寄存器用于复位
# 0x1b 陀螺仪配置寄存器
# 0x1c 加速度配置寄存器
# 0x23 FIFO 可用于存储一系列的传感器读数，以便稍后一起读取
# 0x19 陀螺仪采样寄存器，采样频率= 陀螺仪输出频率/(1+smplrt_div)
# 0x1a 配置寄存器，低通滤波器的设置位
# 0x6c 电源管理寄存器 全部设置为0
# 0x43-0x48 陀螺仪输出寄存器
# 0x3b-0x40 加速度输出寄存器
# 0x41-0x42 温度输出寄存器
# 0x80复位 0x00唤醒开始工作 最低3位设置时钟001，管理器2所有为0
# DMP 简化四轴代码设计输出四元数是放大30倍的
# 俯仰角：pitch=asin(-2q1q3+2q0q2)*57.3
# 横滚角：roll=atan2(2q2*q3+2q0q1,-2q1q1-2q2q2+1)*57.3
# 航向角：yaw=atan2(2*(q1q2+q0q3),q0q0+q1q1-q2q2-q3q3)*57.3  需要通过地磁传感器矫正
# from struct import unpack as unp
from machine import I2C

from math import isnan, pi, asin, atan, atan2


def bytes_to_int(msb, lsb):
    if not msb & 0x80:
        return msb << 8 | lsb
    return - (((msb ^ 255) << 8) | (lsb ^ 255) + 1)


class SMBus(I2C):
    """ Provides an 'SMBus' module which supports some of the py-smbus
        i2c methods, as well as being a subclass of machine.I2C

        Hopefully this will allow you to run code that was targeted at
        py-smbus unmodified on micropython.

	    Use it like you would the machine.I2C class:

            import usmbus.SMBus

            bus = SMBus(1, pins=('G15','G10'), baudrate=100000)
            bus.read_byte_data(addr, register)
            ... etc
	"""

    def read_byte_data(self, addr, register):
        """ Read a single byte from register of device at addr
            Returns a single byte """
        return self.readfrom_mem(addr, register, 1)[0]

    def read_i2c_block_data(self, addr, register, length):
        """ Read a block of length from register of device at addr
            Returns a bytes object filled with whatever was read """
        return self.readfrom_mem(addr, register, length)

    def write_byte_data(self, addr, register, data):
        """ Write a single byte from buffer `data` to register of device at addr
            Returns None """
        # writeto_mem() expects something it can treat as a buffer
        if isinstance(data, int):
            data = bytes([data])
        return self.writeto_mem(addr, register, data)

    def write_i2c_block_data(self, addr, register, data):
        """ Write multiple bytes of data to register of device at addr
            Returns None """
        # writeto_mem() expects something it can treat as a buffer
        if isinstance(data, int):
            data = bytes([data])
        return self.writeto_mem(addr, register, data)

    # The follwing haven't been implemented, but could be.
    def read_byte(self, *args, **kwargs):
        """ Not yet implemented """
        raise RuntimeError("Not yet implemented")

    def write_byte(self, *args, **kwargs):
        """ Not yet implemented """
        raise RuntimeError("Not yet implemented")

    def read_word_data(self, *args, **kwargs):
        """ Not yet implemented """
        raise RuntimeError("Not yet implemented")

    def write_word_data(self, *args, **kwargs):
        """ Not yet implemented """
        raise RuntimeError("Not yet implemented")


class PyComms:
    def __init__(self, address, bus=SMBus(scl=Pin(2), sda=Pin(4))):
        self.address = address
        self.bus = bus

    def reverseByteOrder(self, data):
        # Reverses the byte order of an int (16-bit) or long (32-bit) value
        # Courtesy Vishal Sapre
        dstr = hex(data)[2:].replace('L', '')
        byteCount = len(dstr[::2])
        val = 0
        for i, n in enumerate(range(byteCount)):
            d = data & 0xFF
            val |= (d << (8 * (byteCount - i - 1)))
            data >>= 8
        return val

    def readBit(self, reg, bitNum):
        b = self.readU8(reg)
        data = b & (1 << bitNum)
        return data

    def writeBit(self, reg, bitNum, data):
        b = self.readU8(reg)

        if data != 0:
            b = (b | (1 << bitNum))
        else:
            b = (b & ~(1 << bitNum))

        return self.write8(reg, b)

    def readBits(self, reg, bitStart, length):
        # 01101001 read byte
        # 76543210 bit numbers
        #    xxx   args: bitStart=4, length=3
        #    010   masked
        #   -> 010 shifted

        b = self.readU8(reg)
        mask = ((1 << length) - 1) << (bitStart - length + 1)
        b &= mask
        b >>= (bitStart - length + 1)

        return b

    def writeBits(self, reg, bitStart, length, data):
        #      010 value to write
        # 76543210 bit numbers
        #    xxx   args: bitStart=4, length=3
        # 00011100 mask byte
        # 10101111 original value (sample)
        # 10100011 original & ~mask
        # 10101011 masked | value

        b = self.readU8(reg)
        mask = ((1 << length) - 1) << (bitStart - length + 1)
        data <<= (bitStart - length + 1)
        data &= mask
        b &= ~(mask)
        b |= data

        return self.write8(reg, b)

    def readBytes(self, reg, length):
        output = []

        i = 0
        while i < length:
            output.append(self.readU8(reg))
            i += 1

        return output

    def readBytesListU(self, reg, length):
        output = []

        i = 0
        while i < length:
            output.append(self.readU8(reg + i))
            i += 1

        return output

    def readBytesListS(self, reg, length):
        output = []

        i = 0
        while i < length:
            output.append(self.readS8(reg + i))
            i += 1

        return output

    def writeList(self, reg, list):
        # Writes an array of bytes using I2C format"
        try:
            self.bus.write_i2c_block_data(self.address, reg, list)
        except:
            print("Error accessing 0x%02X: Check your I2C address" % self.address)
        return -1

    def write8(self, reg, value):
        # Writes an 8-bit value to the specified register/address
        try:
            self.bus.write_byte_data(self.address, reg, value)
        except:
            print("Error accessing 0x%02X: Check your I2C address" % self.address)
            return -1

    def readU8(self, reg):
        # Read an unsigned byte from the I2C device
        try:
            result = self.bus.read_byte_data(self.address, reg)
            return result
        except:
            print("Error accessing 0x%02X: Check your I2C address" % self.address)
            return -1

    def readS8(self, reg):
        # Reads a signed byte from the I2C device
        try:
            result = self.bus.read_byte_data(self.address, reg)
            if result > 127:
                return result - 256
            else:
                return result
        except:
            print("Error accessing 0x%02X: Check your I2C address" % self.address)
            return -1

    def readU16(self, reg):
        # Reads an unsigned 16-bit value from the I2C device
        try:
            hibyte = self.bus.read_byte_data(self.address, reg)
            result = (hibyte << 8) + self.bus.read_byte_data(self.address, reg + 1)
            return result
        except:
            print("Error accessing 0x%02X: Check your I2C address" % self.address)
            return -1

    def readS16(self, reg):
        # Reads a signed 16-bit value from the I2C device
        try:
            hibyte = self.bus.read_byte_data(self.address, reg)
            if hibyte > 127:
                hibyte -= 256
            result = (hibyte << 8) + self.bus.read_byte_data(self.address, reg + 1)
            return result
        except:
            print("Error accessing 0x%02X: Check your I2C address" % self.address)
            return -1


def safe_asin(v):
    if isnan(v): return 0
    if v >= 1: return pi / 2
    if v <= -1: return -pi / 2
    return asin(v)


class MPU6050:
    MPU6050_ADDRESS_AD0_LOW = 0x68  # address pin low (GND), default for InvenSense evaluation board
    MPU6050_ADDRESS_AD0_HIGH = 0x69  # address pin high (VCC)
    MPU6050_DEFAULT_ADDRESS = MPU6050_ADDRESS_AD0_LOW

    MPU6050_RA_XG_OFFS_TC = 0x00  # [7] PWR_MODE, [6:1] XG_OFFS_TC, [0] OTP_BNK_VLD
    MPU6050_RA_YG_OFFS_TC = 0x01  # [7] PWR_MODE, [6:1] YG_OFFS_TC, [0] OTP_BNK_VLD
    MPU6050_RA_ZG_OFFS_TC = 0x02  # [7] PWR_MODE, [6:1] ZG_OFFS_TC, [0] OTP_BNK_VLD
    MPU6050_RA_XA_OFFS_H = 0x06  # [15:0] XA_OFFS
    MPU6050_RA_XA_OFFS_L_TC = 0x07
    MPU6050_RA_YA_OFFS_H = 0x08  # [15:0] YA_OFFS
    MPU6050_RA_YA_OFFS_L_TC = 0x09
    MPU6050_RA_ZA_OFFS_H = 0x0A  # [15:0] ZA_OFFS
    MPU6050_RA_ZA_OFFS_L_TC = 0x0B
    MPU6050_RA_XG_OFFS_USRH = 0x13  # [15:0] XG_OFFS_USR
    MPU6050_RA_XG_OFFS_USRL = 0x14
    MPU6050_RA_YG_OFFS_USRH = 0x15  # [15:0] YG_OFFS_USR
    MPU6050_RA_YG_OFFS_USRL = 0x16
    MPU6050_RA_ZG_OFFS_USRH = 0x17  # [15:0] ZG_OFFS_USR
    MPU6050_RA_ZG_OFFS_USRL = 0x18
    MPU6050_RA_SMPLRT_DIV = 0x19
    MPU6050_RA_CONFIG = 0x1A
    MPU6050_RA_GYRO_CONFIG = 0x1B
    MPU6050_RA_ACCEL_CONFIG = 0x1C
    MPU6050_RA_FF_THR = 0x1D
    MPU6050_RA_FF_DUR = 0x1E
    MPU6050_RA_MOT_THR = 0x1F
    MPU6050_RA_MOT_DUR = 0x20
    MPU6050_RA_ZRMOT_THR = 0x21
    MPU6050_RA_ZRMOT_DUR = 0x22
    MPU6050_RA_FIFO_EN = 0x23
    MPU6050_RA_INT_PIN_CFG = 0x37
    MPU6050_RA_INT_ENABLE = 0x38
    MPU6050_RA_DMP_INT_STATUS = 0x39
    MPU6050_RA_INT_STATUS = 0x3A
    MPU6050_RA_ACCEL_XOUT_H = 0x3B
    MPU6050_RA_ACCEL_XOUT_L = 0x3C
    MPU6050_RA_ACCEL_YOUT_H = 0x3D
    MPU6050_RA_ACCEL_YOUT_L = 0x3E
    MPU6050_RA_ACCEL_ZOUT_H = 0x3F
    MPU6050_RA_ACCEL_ZOUT_L = 0x40
    MPU6050_RA_GYRO_XOUT_H = 0x43
    MPU6050_RA_GYRO_XOUT_L = 0x44
    MPU6050_RA_GYRO_YOUT_H = 0x45
    MPU6050_RA_GYRO_YOUT_L = 0x46
    MPU6050_RA_GYRO_ZOUT_H = 0x47
    MPU6050_RA_GYRO_ZOUT_L = 0x48
    MPU6050_RA_USER_CTRL = 0x6A
    MPU6050_RA_PWR_MGMT_1 = 0x6B
    MPU6050_RA_PWR_MGMT_2 = 0x6C
    MPU6050_RA_BANK_SEL = 0x6D
    MPU6050_RA_MEM_START_ADDR = 0x6E
    MPU6050_RA_MEM_R_W = 0x6F
    MPU6050_RA_DMP_CFG_1 = 0x70
    MPU6050_RA_DMP_CFG_2 = 0x71
    MPU6050_RA_FIFO_COUNTH = 0x72
    MPU6050_RA_FIFO_COUNTL = 0x73
    MPU6050_RA_FIFO_R_W = 0x74

    MPU6050_TC_PWR_MODE_BIT = 7
    MPU6050_TC_OFFSET_BIT = 6
    MPU6050_TC_OFFSET_LENGTH = 6
    MPU6050_TC_OTP_BNK_VLD_BIT = 0

    MPU6050_CFG_EXT_SYNC_SET_BIT = 5
    MPU6050_CFG_EXT_SYNC_SET_LENGTH = 3
    MPU6050_CFG_DLPF_CFG_BIT = 2
    MPU6050_CFG_DLPF_CFG_LENGTH = 3

    MPU6050_EXT_SYNC_TEMP_OUT_L = 0x1

    MPU6050_DLPF_BW_42 = 0x03

    MPU6050_GCONFIG_FS_SEL_BIT = 4
    MPU6050_GCONFIG_FS_SEL_LENGTH = 2

    MPU6050_GYRO_FS_250 = 0x00
    MPU6050_GYRO_FS_2000 = 0x03

    MPU6050_ACONFIG_AFS_SEL_BIT = 4
    MPU6050_ACONFIG_AFS_SEL_LENGTH = 2

    MPU6050_ACCEL_FS_2 = 0x00

    MPU6050_INTCFG_I2C_BYPASS_EN_BIT = 1

    MPU6050_INTERRUPT_DMP_INT_BIT = 1

    MPU6050_USERCTRL_DMP_EN_BIT = 7
    MPU6050_USERCTRL_FIFO_EN_BIT = 6
    MPU6050_USERCTRL_DMP_RESET_BIT = 3
    MPU6050_USERCTRL_FIFO_RESET_BIT = 2

    MPU6050_PWR1_DEVICE_RESET_BIT = 7
    MPU6050_PWR1_SLEEP_BIT = 6
    MPU6050_PWR1_CYCLE_BIT = 5
    MPU6050_PWR1_CLKSEL_BIT = 2
    MPU6050_PWR1_CLKSEL_LENGTH = 3

    MPU6050_CLOCK_PLL_XGYRO = 0x01
    MPU6050_CLOCK_PLL_YGYRO = 0x02
    MPU6050_CLOCK_PLL_ZGYRO = 0x03

    MPU6050_BANKSEL_PRFTCH_EN_BIT = 6
    MPU6050_BANKSEL_CFG_USER_BANK_BIT = 5
    MPU6050_BANKSEL_MEM_SEL_BIT = 4
    MPU6050_BANKSEL_MEM_SEL_LENGTH = 5

    MPU6050_BANKSEL_PRFTCH_EN_BIT = 6
    MPU6050_BANKSEL_CFG_USER_BANK_BIT = 5
    MPU6050_BANKSEL_MEM_SEL_BIT = 4
    MPU6050_BANKSEL_MEM_SEL_LENGTH = 5

    # DMP

    MPU6050_DMP_MEMORY_BANKS = 8
    MPU6050_DMP_MEMORY_BANK_SIZE = 256
    MPU6050_DMP_MEMORY_CHUNK_SIZE = 16

    MPU6050_DMP_CODE_SIZE = 1929  # dmpMemory[]
    MPU6050_DMP_CONFIG_SIZE = 192  # dmpConfig[]
    MPU6050_DMP_UPDATES_SIZE = 47  # dmpUpdates[]

    # this block of memory gets written to the MPU on start-up, and it seems
    # to be volatile memory, so it has to be done each time (it only takes ~1 second though)
    dmpMemory = [
        # bank 0, 256 bytes
        0xFB, 0x00, 0x00, 0x3E, 0x00, 0x0B, 0x00, 0x36, 0x00, 0x01, 0x00, 0x02, 0x00, 0x03, 0x00, 0x00,
        0x00, 0x65, 0x00, 0x54, 0xFF, 0xEF, 0x00, 0x00, 0xFA, 0x80, 0x00, 0x0B, 0x12, 0x82, 0x00, 0x01,
        0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x28, 0x00, 0x00, 0xFF, 0xFF, 0x45, 0x81, 0xFF, 0xFF, 0xFA, 0x72, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x03, 0xE8, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x7F, 0xFF, 0xFF, 0xFE, 0x80, 0x01,
        0x00, 0x1B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x3E, 0x03, 0x30, 0x40, 0x00, 0x00, 0x00, 0x02, 0xCA, 0xE3, 0x09, 0x3E, 0x80, 0x00, 0x00,
        0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00, 0x60, 0x00, 0x00, 0x00,
        0x41, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x0B, 0x2A, 0x00, 0x00, 0x16, 0x55, 0x00, 0x00, 0x21, 0x82,
        0xFD, 0x87, 0x26, 0x50, 0xFD, 0x80, 0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00, 0x05, 0x80, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00,
        0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x6F, 0x00, 0x02, 0x65, 0x32, 0x00, 0x00, 0x5E, 0xC0,
        0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0xFB, 0x8C, 0x6F, 0x5D, 0xFD, 0x5D, 0x08, 0xD9, 0x00, 0x7C, 0x73, 0x3B, 0x00, 0x6C, 0x12, 0xCC,
        0x32, 0x00, 0x13, 0x9D, 0x32, 0x00, 0xD0, 0xD6, 0x32, 0x00, 0x08, 0x00, 0x40, 0x00, 0x01, 0xF4,
        0xFF, 0xE6, 0x80, 0x79, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0xD0, 0xD6, 0x00, 0x00, 0x27, 0x10,

        # bank 1, 256 bytes
        0xFB, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00,
        0x00, 0x00, 0xFA, 0x36, 0xFF, 0xBC, 0x30, 0x8E, 0x00, 0x05, 0xFB, 0xF0, 0xFF, 0xD9, 0x5B, 0xC8,
        0xFF, 0xD0, 0x9A, 0xBE, 0x00, 0x00, 0x10, 0xA9, 0xFF, 0xF4, 0x1E, 0xB2, 0x00, 0xCE, 0xBB, 0xF7,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x04, 0x00, 0x02, 0x00, 0x02, 0x02, 0x00, 0x00, 0x0C,
        0xFF, 0xC2, 0x80, 0x00, 0x00, 0x01, 0x80, 0x00, 0x00, 0xCF, 0x80, 0x00, 0x40, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x06, 0x00, 0x00, 0x00, 0x00, 0x14,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x03, 0x3F, 0x68, 0xB6, 0x79, 0x35, 0x28, 0xBC, 0xC6, 0x7E, 0xD1, 0x6C,
        0x80, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0xB2, 0x6A, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3F, 0xF0, 0x00, 0x00, 0x00, 0x30,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x25, 0x4D, 0x00, 0x2F, 0x70, 0x6D, 0x00, 0x00, 0x05, 0xAE, 0x00, 0x0C, 0x02, 0xD0,

        # bank 2, 256 bytes
        0x00, 0x00, 0x00, 0x00, 0x00, 0x65, 0x00, 0x54, 0xFF, 0xEF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x01, 0x00, 0x00, 0x44, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x00, 0x00, 0x00, 0x01, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x54, 0x00, 0x00, 0xFF, 0xEF, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x1B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00,
        0x00, 0x1B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,

        # bank 3, 256 bytes
        0xD8, 0xDC, 0xBA, 0xA2, 0xF1, 0xDE, 0xB2, 0xB8, 0xB4, 0xA8, 0x81, 0x91, 0xF7, 0x4A, 0x90, 0x7F,
        0x91, 0x6A, 0xF3, 0xF9, 0xDB, 0xA8, 0xF9, 0xB0, 0xBA, 0xA0, 0x80, 0xF2, 0xCE, 0x81, 0xF3, 0xC2,
        0xF1, 0xC1, 0xF2, 0xC3, 0xF3, 0xCC, 0xA2, 0xB2, 0x80, 0xF1, 0xC6, 0xD8, 0x80, 0xBA, 0xA7, 0xDF,
        0xDF, 0xDF, 0xF2, 0xA7, 0xC3, 0xCB, 0xC5, 0xB6, 0xF0, 0x87, 0xA2, 0x94, 0x24, 0x48, 0x70, 0x3C,
        0x95, 0x40, 0x68, 0x34, 0x58, 0x9B, 0x78, 0xA2, 0xF1, 0x83, 0x92, 0x2D, 0x55, 0x7D, 0xD8, 0xB1,
        0xB4, 0xB8, 0xA1, 0xD0, 0x91, 0x80, 0xF2, 0x70, 0xF3, 0x70, 0xF2, 0x7C, 0x80, 0xA8, 0xF1, 0x01,
        0xB0, 0x98, 0x87, 0xD9, 0x43, 0xD8, 0x86, 0xC9, 0x88, 0xBA, 0xA1, 0xF2, 0x0E, 0xB8, 0x97, 0x80,
        0xF1, 0xA9, 0xDF, 0xDF, 0xDF, 0xAA, 0xDF, 0xDF, 0xDF, 0xF2, 0xAA, 0xC5, 0xCD, 0xC7, 0xA9, 0x0C,
        0xC9, 0x2C, 0x97, 0x97, 0x97, 0x97, 0xF1, 0xA9, 0x89, 0x26, 0x46, 0x66, 0xB0, 0xB4, 0xBA, 0x80,
        0xAC, 0xDE, 0xF2, 0xCA, 0xF1, 0xB2, 0x8C, 0x02, 0xA9, 0xB6, 0x98, 0x00, 0x89, 0x0E, 0x16, 0x1E,
        0xB8, 0xA9, 0xB4, 0x99, 0x2C, 0x54, 0x7C, 0xB0, 0x8A, 0xA8, 0x96, 0x36, 0x56, 0x76, 0xF1, 0xB9,
        0xAF, 0xB4, 0xB0, 0x83, 0xC0, 0xB8, 0xA8, 0x97, 0x11, 0xB1, 0x8F, 0x98, 0xB9, 0xAF, 0xF0, 0x24,
        0x08, 0x44, 0x10, 0x64, 0x18, 0xF1, 0xA3, 0x29, 0x55, 0x7D, 0xAF, 0x83, 0xB5, 0x93, 0xAF, 0xF0,
        0x00, 0x28, 0x50, 0xF1, 0xA3, 0x86, 0x9F, 0x61, 0xA6, 0xDA, 0xDE, 0xDF, 0xD9, 0xFA, 0xA3, 0x86,
        0x96, 0xDB, 0x31, 0xA6, 0xD9, 0xF8, 0xDF, 0xBA, 0xA6, 0x8F, 0xC2, 0xC5, 0xC7, 0xB2, 0x8C, 0xC1,
        0xB8, 0xA2, 0xDF, 0xDF, 0xDF, 0xA3, 0xDF, 0xDF, 0xDF, 0xD8, 0xD8, 0xF1, 0xB8, 0xA8, 0xB2, 0x86,

        # bank 4, 256 bytes
        0xB4, 0x98, 0x0D, 0x35, 0x5D, 0xB8, 0xAA, 0x98, 0xB0, 0x87, 0x2D, 0x35, 0x3D, 0xB2, 0xB6, 0xBA,
        0xAF, 0x8C, 0x96, 0x19, 0x8F, 0x9F, 0xA7, 0x0E, 0x16, 0x1E, 0xB4, 0x9A, 0xB8, 0xAA, 0x87, 0x2C,
        0x54, 0x7C, 0xB9, 0xA3, 0xDE, 0xDF, 0xDF, 0xA3, 0xB1, 0x80, 0xF2, 0xC4, 0xCD, 0xC9, 0xF1, 0xB8,
        0xA9, 0xB4, 0x99, 0x83, 0x0D, 0x35, 0x5D, 0x89, 0xB9, 0xA3, 0x2D, 0x55, 0x7D, 0xB5, 0x93, 0xA3,
        0x0E, 0x16, 0x1E, 0xA9, 0x2C, 0x54, 0x7C, 0xB8, 0xB4, 0xB0, 0xF1, 0x97, 0x83, 0xA8, 0x11, 0x84,
        0xA5, 0x09, 0x98, 0xA3, 0x83, 0xF0, 0xDA, 0x24, 0x08, 0x44, 0x10, 0x64, 0x18, 0xD8, 0xF1, 0xA5,
        0x29, 0x55, 0x7D, 0xA5, 0x85, 0x95, 0x02, 0x1A, 0x2E, 0x3A, 0x56, 0x5A, 0x40, 0x48, 0xF9, 0xF3,
        0xA3, 0xD9, 0xF8, 0xF0, 0x98, 0x83, 0x24, 0x08, 0x44, 0x10, 0x64, 0x18, 0x97, 0x82, 0xA8, 0xF1,
        0x11, 0xF0, 0x98, 0xA2, 0x24, 0x08, 0x44, 0x10, 0x64, 0x18, 0xDA, 0xF3, 0xDE, 0xD8, 0x83, 0xA5,
        0x94, 0x01, 0xD9, 0xA3, 0x02, 0xF1, 0xA2, 0xC3, 0xC5, 0xC7, 0xD8, 0xF1, 0x84, 0x92, 0xA2, 0x4D,
        0xDA, 0x2A, 0xD8, 0x48, 0x69, 0xD9, 0x2A, 0xD8, 0x68, 0x55, 0xDA, 0x32, 0xD8, 0x50, 0x71, 0xD9,
        0x32, 0xD8, 0x70, 0x5D, 0xDA, 0x3A, 0xD8, 0x58, 0x79, 0xD9, 0x3A, 0xD8, 0x78, 0x93, 0xA3, 0x4D,
        0xDA, 0x2A, 0xD8, 0x48, 0x69, 0xD9, 0x2A, 0xD8, 0x68, 0x55, 0xDA, 0x32, 0xD8, 0x50, 0x71, 0xD9,
        0x32, 0xD8, 0x70, 0x5D, 0xDA, 0x3A, 0xD8, 0x58, 0x79, 0xD9, 0x3A, 0xD8, 0x78, 0xA8, 0x8A, 0x9A,
        0xF0, 0x28, 0x50, 0x78, 0x9E, 0xF3, 0x88, 0x18, 0xF1, 0x9F, 0x1D, 0x98, 0xA8, 0xD9, 0x08, 0xD8,
        0xC8, 0x9F, 0x12, 0x9E, 0xF3, 0x15, 0xA8, 0xDA, 0x12, 0x10, 0xD8, 0xF1, 0xAF, 0xC8, 0x97, 0x87,

        # bank 5, 256 bytes
        0x34, 0xB5, 0xB9, 0x94, 0xA4, 0x21, 0xF3, 0xD9, 0x22, 0xD8, 0xF2, 0x2D, 0xF3, 0xD9, 0x2A, 0xD8,
        0xF2, 0x35, 0xF3, 0xD9, 0x32, 0xD8, 0x81, 0xA4, 0x60, 0x60, 0x61, 0xD9, 0x61, 0xD8, 0x6C, 0x68,
        0x69, 0xD9, 0x69, 0xD8, 0x74, 0x70, 0x71, 0xD9, 0x71, 0xD8, 0xB1, 0xA3, 0x84, 0x19, 0x3D, 0x5D,
        0xA3, 0x83, 0x1A, 0x3E, 0x5E, 0x93, 0x10, 0x30, 0x81, 0x10, 0x11, 0xB8, 0xB0, 0xAF, 0x8F, 0x94,
        0xF2, 0xDA, 0x3E, 0xD8, 0xB4, 0x9A, 0xA8, 0x87, 0x29, 0xDA, 0xF8, 0xD8, 0x87, 0x9A, 0x35, 0xDA,
        0xF8, 0xD8, 0x87, 0x9A, 0x3D, 0xDA, 0xF8, 0xD8, 0xB1, 0xB9, 0xA4, 0x98, 0x85, 0x02, 0x2E, 0x56,
        0xA5, 0x81, 0x00, 0x0C, 0x14, 0xA3, 0x97, 0xB0, 0x8A, 0xF1, 0x2D, 0xD9, 0x28, 0xD8, 0x4D, 0xD9,
        0x48, 0xD8, 0x6D, 0xD9, 0x68, 0xD8, 0xB1, 0x84, 0x0D, 0xDA, 0x0E, 0xD8, 0xA3, 0x29, 0x83, 0xDA,
        0x2C, 0x0E, 0xD8, 0xA3, 0x84, 0x49, 0x83, 0xDA, 0x2C, 0x4C, 0x0E, 0xD8, 0xB8, 0xB0, 0xA8, 0x8A,
        0x9A, 0xF5, 0x20, 0xAA, 0xDA, 0xDF, 0xD8, 0xA8, 0x40, 0xAA, 0xD0, 0xDA, 0xDE, 0xD8, 0xA8, 0x60,
        0xAA, 0xDA, 0xD0, 0xDF, 0xD8, 0xF1, 0x97, 0x86, 0xA8, 0x31, 0x9B, 0x06, 0x99, 0x07, 0xAB, 0x97,
        0x28, 0x88, 0x9B, 0xF0, 0x0C, 0x20, 0x14, 0x40, 0xB8, 0xB0, 0xB4, 0xA8, 0x8C, 0x9C, 0xF0, 0x04,
        0x28, 0x51, 0x79, 0x1D, 0x30, 0x14, 0x38, 0xB2, 0x82, 0xAB, 0xD0, 0x98, 0x2C, 0x50, 0x50, 0x78,
        0x78, 0x9B, 0xF1, 0x1A, 0xB0, 0xF0, 0x8A, 0x9C, 0xA8, 0x29, 0x51, 0x79, 0x8B, 0x29, 0x51, 0x79,
        0x8A, 0x24, 0x70, 0x59, 0x8B, 0x20, 0x58, 0x71, 0x8A, 0x44, 0x69, 0x38, 0x8B, 0x39, 0x40, 0x68,
        0x8A, 0x64, 0x48, 0x31, 0x8B, 0x30, 0x49, 0x60, 0xA5, 0x88, 0x20, 0x09, 0x71, 0x58, 0x44, 0x68,

        # bank 6, 256 bytes
        0x11, 0x39, 0x64, 0x49, 0x30, 0x19, 0xF1, 0xAC, 0x00, 0x2C, 0x54, 0x7C, 0xF0, 0x8C, 0xA8, 0x04,
        0x28, 0x50, 0x78, 0xF1, 0x88, 0x97, 0x26, 0xA8, 0x59, 0x98, 0xAC, 0x8C, 0x02, 0x26, 0x46, 0x66,
        0xF0, 0x89, 0x9C, 0xA8, 0x29, 0x51, 0x79, 0x24, 0x70, 0x59, 0x44, 0x69, 0x38, 0x64, 0x48, 0x31,
        0xA9, 0x88, 0x09, 0x20, 0x59, 0x70, 0xAB, 0x11, 0x38, 0x40, 0x69, 0xA8, 0x19, 0x31, 0x48, 0x60,
        0x8C, 0xA8, 0x3C, 0x41, 0x5C, 0x20, 0x7C, 0x00, 0xF1, 0x87, 0x98, 0x19, 0x86, 0xA8, 0x6E, 0x76,
        0x7E, 0xA9, 0x99, 0x88, 0x2D, 0x55, 0x7D, 0x9E, 0xB9, 0xA3, 0x8A, 0x22, 0x8A, 0x6E, 0x8A, 0x56,
        0x8A, 0x5E, 0x9F, 0xB1, 0x83, 0x06, 0x26, 0x46, 0x66, 0x0E, 0x2E, 0x4E, 0x6E, 0x9D, 0xB8, 0xAD,
        0x00, 0x2C, 0x54, 0x7C, 0xF2, 0xB1, 0x8C, 0xB4, 0x99, 0xB9, 0xA3, 0x2D, 0x55, 0x7D, 0x81, 0x91,
        0xAC, 0x38, 0xAD, 0x3A, 0xB5, 0x83, 0x91, 0xAC, 0x2D, 0xD9, 0x28, 0xD8, 0x4D, 0xD9, 0x48, 0xD8,
        0x6D, 0xD9, 0x68, 0xD8, 0x8C, 0x9D, 0xAE, 0x29, 0xD9, 0x04, 0xAE, 0xD8, 0x51, 0xD9, 0x04, 0xAE,
        0xD8, 0x79, 0xD9, 0x04, 0xD8, 0x81, 0xF3, 0x9D, 0xAD, 0x00, 0x8D, 0xAE, 0x19, 0x81, 0xAD, 0xD9,
        0x01, 0xD8, 0xF2, 0xAE, 0xDA, 0x26, 0xD8, 0x8E, 0x91, 0x29, 0x83, 0xA7, 0xD9, 0xAD, 0xAD, 0xAD,
        0xAD, 0xF3, 0x2A, 0xD8, 0xD8, 0xF1, 0xB0, 0xAC, 0x89, 0x91, 0x3E, 0x5E, 0x76, 0xF3, 0xAC, 0x2E,
        0x2E, 0xF1, 0xB1, 0x8C, 0x5A, 0x9C, 0xAC, 0x2C, 0x28, 0x28, 0x28, 0x9C, 0xAC, 0x30, 0x18, 0xA8,
        0x98, 0x81, 0x28, 0x34, 0x3C, 0x97, 0x24, 0xA7, 0x28, 0x34, 0x3C, 0x9C, 0x24, 0xF2, 0xB0, 0x89,
        0xAC, 0x91, 0x2C, 0x4C, 0x6C, 0x8A, 0x9B, 0x2D, 0xD9, 0xD8, 0xD8, 0x51, 0xD9, 0xD8, 0xD8, 0x79,

        # bank 7, 138 bytes (remainder)
        0xD9, 0xD8, 0xD8, 0xF1, 0x9E, 0x88, 0xA3, 0x31, 0xDA, 0xD8, 0xD8, 0x91, 0x2D, 0xD9, 0x28, 0xD8,
        0x4D, 0xD9, 0x48, 0xD8, 0x6D, 0xD9, 0x68, 0xD8, 0xB1, 0x83, 0x93, 0x35, 0x3D, 0x80, 0x25, 0xDA,
        0xD8, 0xD8, 0x85, 0x69, 0xDA, 0xD8, 0xD8, 0xB4, 0x93, 0x81, 0xA3, 0x28, 0x34, 0x3C, 0xF3, 0xAB,
        0x8B, 0xF8, 0xA3, 0x91, 0xB6, 0x09, 0xB4, 0xD9, 0xAB, 0xDE, 0xFA, 0xB0, 0x87, 0x9C, 0xB9, 0xA3,
        0xDD, 0xF1, 0xA3, 0xA3, 0xA3, 0xA3, 0x95, 0xF1, 0xA3, 0xA3, 0xA3, 0x9D, 0xF1, 0xA3, 0xA3, 0xA3,
        0xA3, 0xF2, 0xA3, 0xB4, 0x90, 0x80, 0xF2, 0xA3, 0xA3, 0xA3, 0xA3, 0xA3, 0xA3, 0xA3, 0xA3, 0xA3,
        0xA3, 0xB2, 0xA3, 0xA3, 0xA3, 0xA3, 0xA3, 0xA3, 0xB0, 0x87, 0xB5, 0x99, 0xF1, 0xA3, 0xA3, 0xA3,
        0x98, 0xF1, 0xA3, 0xA3, 0xA3, 0xA3, 0x97, 0xA3, 0xA3, 0xA3, 0xA3, 0xF3, 0x9B, 0xA3, 0xA3, 0xDC,
        0xB9, 0xA7, 0xF1, 0x26, 0x26, 0x26, 0xD8, 0xD8, 0xFF]

    dmpConfig = [
        # BANK    OFFSET  LENGTH  [DATA]
        0x03, 0x7B, 0x03, 0x4C, 0xCD, 0x6C,  # FCFG_1 inv_set_gyro_calibration
        0x03, 0xAB, 0x03, 0x36, 0x56, 0x76,  # FCFG_3 inv_set_gyro_calibration
        0x00, 0x68, 0x04, 0x02, 0xCB, 0x47, 0xA2,  # D_0_104 inv_set_gyro_calibration
        0x02, 0x18, 0x04, 0x00, 0x05, 0x8B, 0xC1,  # D_0_24 inv_set_gyro_calibration
        0x01, 0x0C, 0x04, 0x00, 0x00, 0x00, 0x00,  # D_1_152 inv_set_accel_calibration
        0x03, 0x7F, 0x06, 0x0C, 0xC9, 0x2C, 0x97, 0x97, 0x97,  # FCFG_2 inv_set_accel_calibration
        0x03, 0x89, 0x03, 0x26, 0x46, 0x66,  # FCFG_7 inv_set_accel_calibration
        0x00, 0x6C, 0x02, 0x20, 0x00,  # D_0_108 inv_set_accel_calibration
        0x02, 0x40, 0x04, 0x00, 0x00, 0x00, 0x00,  # CPASS_MTX_00 inv_set_compass_calibration
        0x02, 0x44, 0x04, 0x00, 0x00, 0x00, 0x00,  # CPASS_MTX_01
        0x02, 0x48, 0x04, 0x00, 0x00, 0x00, 0x00,  # CPASS_MTX_02
        0x02, 0x4C, 0x04, 0x00, 0x00, 0x00, 0x00,  # CPASS_MTX_10
        0x02, 0x50, 0x04, 0x00, 0x00, 0x00, 0x00,  # CPASS_MTX_11
        0x02, 0x54, 0x04, 0x00, 0x00, 0x00, 0x00,  # CPASS_MTX_12
        0x02, 0x58, 0x04, 0x00, 0x00, 0x00, 0x00,  # CPASS_MTX_20
        0x02, 0x5C, 0x04, 0x00, 0x00, 0x00, 0x00,  # CPASS_MTX_21
        0x02, 0xBC, 0x04, 0x00, 0x00, 0x00, 0x00,  # CPASS_MTX_22
        0x01, 0xEC, 0x04, 0x00, 0x00, 0x40, 0x00,  # D_1_236 inv_apply_endian_accel
        0x03, 0x7F, 0x06, 0x0C, 0xC9, 0x2C, 0x97, 0x97, 0x97,  # FCFG_2 inv_set_mpu_sensors
        0x04, 0x02, 0x03, 0x0D, 0x35, 0x5D,  # CFG_MOTION_BIAS inv_turn_on_bias_from_no_motion
        0x04, 0x09, 0x04, 0x87, 0x2D, 0x35, 0x3D,  # FCFG_5 inv_set_bias_update
        0x00, 0xA3, 0x01, 0x00,  # D_0_163 inv_set_dead_zone
        # SPECIAL 0x01 = enable interrupts
        0x00, 0x00, 0x00, 0x01,  # SET INT_ENABLE at i=22, SPECIAL INSTRUCTION
        0x07, 0x86, 0x01, 0xFE,  # CFG_6 inv_set_fifo_interupt
        0x07, 0x41, 0x05, 0xF1, 0x20, 0x28, 0x30, 0x38,  # CFG_8 inv_send_quaternion
        0x07, 0x7E, 0x01, 0x30,  # CFG_16 inv_set_footer
        0x07, 0x46, 0x01, 0x9A,  # CFG_GYRO_SOURCE inv_send_gyro
        0x07, 0x47, 0x04, 0xF1, 0x28, 0x30, 0x38,  # CFG_9 inv_send_gyro -> inv_construct3_fifo
        0x07, 0x6C, 0x04, 0xF1, 0x28, 0x30, 0x38,  # CFG_12 inv_send_accel -> inv_construct3_fifo
        0x02, 0x16, 0x02, 0x00, 0x05  # D_0_22 inv_set_fifo_rate
    ]

    dmpUpdates = [
        0x01, 0xB2, 0x02, 0xFF, 0xFF,
        0x01, 0x90, 0x04, 0x09, 0x23, 0xA1, 0x35,
        0x01, 0x6A, 0x02, 0x06, 0x00,
        0x01, 0x60, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x60, 0x04, 0x40, 0x00, 0x00, 0x00,
        0x01, 0x62, 0x02, 0x00, 0x00,
        0x00, 0x60, 0x04, 0x00, 0x40, 0x00, 0x00]

    # Setting up internal 42-byte (default) DMP packet buffer
    dmpPacketSize = 42

    # construct a new object with the I2C address of the MPU6050
    def __init__(self, address=MPU6050_DEFAULT_ADDRESS):
        self.i2c = PyComms(address)
        self.address = address

    def initialize(self):
        self.setClockSource(self.MPU6050_CLOCK_PLL_XGYRO)
        self.setFullScaleGyroRange(self.MPU6050_GYRO_FS_250)
        self.setFullScaleAccelRange(self.MPU6050_ACCEL_FS_2)
        self.setSleepEnabled(False)

    def getRate(self):
        return self.i2c.readU8(self.MPU6050_RA_SMPLRT_DIV)

    def setRate(self, value):
        self.i2c.write8(self.MPU6050_RA_SMPLRT_DIV, value)

    def getExternalFrameSync(self):
        return self.i2c.readBits(self.MPU6050_RA_CONFIG, self.MPU6050_CFG_EXT_SYNC_SET_BIT,
                                 self.MPU6050_CFG_EXT_SYNC_SET_LENGTH)

    def setExternalFrameSync(self, sync):
        self.i2c.writeBits(self.MPU6050_RA_CONFIG, self.MPU6050_CFG_EXT_SYNC_SET_BIT,
                           self.MPU6050_CFG_EXT_SYNC_SET_LENGTH, sync)

    def getDLPFMode(self):
        return self.i2c.readBits(self.MPU6050_RA_CONFIG, self.MPU6050_CFG_DLPF_CFG_BIT,
                                 self.MPU6050_CFG_DLPF_CFG_LENGTH)

    def setDLPFMode(self, mode):
        self.i2c.writeBits(self.MPU6050_RA_CONFIG, self.MPU6050_CFG_DLPF_CFG_BIT, self.MPU6050_CFG_DLPF_CFG_LENGTH,
                           mode)

    def getFullScaleGyroRange(self):
        return self.i2c.readBits(self.MPU6050_RA_GYRO_CONFIG, self.MPU6050_GCONFIG_FS_SEL_BIT,
                                 self.MPU6050_GCONFIG_FS_SEL_LENGTH)

    def setFullScaleGyroRange(self, range):
        self.i2c.writeBits(self.MPU6050_RA_GYRO_CONFIG, self.MPU6050_GCONFIG_FS_SEL_BIT,
                           self.MPU6050_GCONFIG_FS_SEL_LENGTH, range)

    def getFullScaleAccelRange(self):
        return self.i2c.readBits(self.MPU6050_RA_ACCEL_CONFIG, self.MPU6050_ACONFIG_AFS_SEL_BIT,
                                 self.MPU6050_ACONFIG_AFS_SEL_LENGTH)

    def setFullScaleAccelRange(self, value):
        self.i2c.writeBits(self.MPU6050_RA_ACCEL_CONFIG, self.MPU6050_ACONFIG_AFS_SEL_BIT,
                           self.MPU6050_ACONFIG_AFS_SEL_LENGTH, value)

    def getMotionDetectionThreshold(self):
        return self.i2c.readU8(self.MPU6050_RA_MOT_THR)

    def setMotionDetectionThreshold(self, treshold):
        self.i2c.write8(self.MPU6050_RA_MOT_THR, treshold)

    def getMotionDetectionDuration(self):
        return self.i2c.readU8(self.MPU6050_RA_MOT_DUR)

    def setMotionDetectionDuration(self, duration):
        self.i2c.write8(self.MPU6050_RA_MOT_DUR, duration)

    def getZeroMotionDetectionThreshold(self):
        return self.i2c.readU8(self.MPU6050_RA_ZRMOT_THR)

    def setZeroMotionDetectionThreshold(self, treshold):
        self.i2c.write8(self.MPU6050_RA_ZRMOT_THR, treshold)

    def getZeroMotionDetectionDuration(self):
        return self.i2c.readU8(self.MPU6050_RA_ZRMOT_DUR)

    def setZeroMotionDetectionDuration(self, duration):
        self.i2c.write8(self.MPU6050_RA_ZRMOT_DUR, duration)

    def getI2CBypassEnabled(self):
        return self.i2c.readBit(self.MPU6050_RA_INT_PIN_CFG, self.MPU6050_INTCFG_I2C_BYPASS_EN_BIT)

    def setI2CBypassEnabled(self, enabled):
        self.i2c.writeBit(self.MPU6050_RA_INT_PIN_CFG, self.MPU6050_INTCFG_I2C_BYPASS_EN_BIT, enabled)

    def setIntEnabled(self, status):
        self.i2c.write8(self.MPU6050_RA_INT_ENABLE, status)

    def getIntStatus(self):
        return self.i2c.readU8(self.MPU6050_RA_INT_STATUS)

    def getFIFOEnabled(self):
        return self.i2c.readBit(self.MPU6050_RA_USER_CTRL, self.MPU6050_USERCTRL_FIFO_EN_BIT)

    def setFIFOEnabled(self, status):
        self.i2c.writeBit(self.MPU6050_RA_USER_CTRL, self.MPU6050_USERCTRL_FIFO_EN_BIT, status)

    def resetFIFO(self):
        self.i2c.writeBit(self.MPU6050_RA_USER_CTRL, self.MPU6050_USERCTRL_FIFO_RESET_BIT, True)

    def reset(self):
        self.i2c.writeBit(self.MPU6050_RA_PWR_MGMT_1, self.MPU6050_PWR1_DEVICE_RESET_BIT, True)

    def getSleepEnabled(self):
        return self.i2c.readBit(self.MPU6050_RA_PWR_MGMT_1, self.MPU6050_PWR1_SLEEP_BIT)

    def setSleepEnabled(self, status):
        self.i2c.writeBit(self.MPU6050_RA_PWR_MGMT_1, self.MPU6050_PWR1_SLEEP_BIT, status)

    def getClockSource(self):
        return self.i2c.readBits(self.MPU6050_RA_PWR_MGMT_1, self.MPU6050_PWR1_CLKSEL_BIT,
                                 self.MPU6050_PWR1_CLKSEL_LENGTH)

    def setClockSource(self, source):
        self.i2c.writeBits(self.MPU6050_RA_PWR_MGMT_1, self.MPU6050_PWR1_CLKSEL_BIT, self.MPU6050_PWR1_CLKSEL_LENGTH,
                           source)

    def getFIFOCount(self):
        return self.i2c.readU16(self.MPU6050_RA_FIFO_COUNTH)

    def getFIFOBytes(self, length):
        return self.i2c.readBytes(self.MPU6050_RA_FIFO_R_W, length)

    def getOTPBankValid(self):
        result = self.i2c.readBit(self.MPU6050_RA_XG_OFFS_TC, self.MPU6050_TC_OTP_BNK_VLD_BIT)
        return result

    def setOTPBankValid(self, status):
        self.i2c.writeBit(self.MPU6050_RA_XG_OFFS_TC, self.MPU6050_TC_OTP_BNK_VLD_BIT, status)

    def getXGyroOffset(self):
        return self.i2c.readBits(self.MPU6050_RA_XG_OFFS_TC, self.MPU6050_TC_OFFSET_BIT, self.MPU6050_TC_OFFSET_LENGTH)

    def setXGyroOffset(self, offset):
        self.i2c.writeBits(self.MPU6050_RA_XG_OFFS_TC, self.MPU6050_TC_OFFSET_BIT, self.MPU6050_TC_OFFSET_LENGTH,
                           offset)

    def getYGyroOffset(self):
        return self.i2c.readBits(self.MPU6050_RA_YG_OFFS_TC, self.MPU6050_TC_OFFSET_BIT, self.MPU6050_TC_OFFSET_LENGTH)

    def setYGyroOffset(self, offset):
        self.i2c.writeBits(self.MPU6050_RA_YG_OFFS_TC, self.MPU6050_TC_OFFSET_BIT, self.MPU6050_TC_OFFSET_LENGTH,
                           offset)

    def getZGyroOffset(self):
        return self.i2c.readBits(self.MPU6050_RA_ZG_OFFS_TC, self.MPU6050_TC_OFFSET_BIT, self.MPU6050_TC_OFFSET_LENGTH)

    def setZGyroOffset(self, offset):
        self.i2c.writeBits(self.MPU6050_RA_ZG_OFFS_TC, self.MPU6050_TC_OFFSET_BIT, self.MPU6050_TC_OFFSET_LENGTH,
                           offset)

    def setXGyroOffsetUser(self, value):
        self.i2c.write8(self.MPU6050_RA_XG_OFFS_USRH, value >> 8)
        self.i2c.write8(self.MPU6050_RA_XG_OFFS_USRL, value & 0xFF)
        return True

    def getYGyroOffsetUser(self):
        pass

    def setYGyroOffsetUser(self, value):
        self.i2c.write8(self.MPU6050_RA_YG_OFFS_USRH, value >> 8)
        self.i2c.write8(self.MPU6050_RA_YG_OFFS_USRL, value & 0xFF)
        return True

    def getZGyroOffsetUser(self):
        pass

    def setZGyroOffsetUser(self, value):
        self.i2c.write8(self.MPU6050_RA_ZG_OFFS_USRH, value >> 8)
        self.i2c.write8(self.MPU6050_RA_ZG_OFFS_USRL, value & 0xFF)
        return True

    def getIntDMPStatus(self):
        return self.i2c.readBit(self.MPU6050_RA_INT_STATUS, self.MPU6050_INTERRUPT_DMP_INT_BIT)

    def getDMPEnabled(self):
        return self.i2c.readBit(self.MPU6050_RA_USER_CTRL, self.MPU6050_USERCTRL_DMP_EN_BIT)

    def setDMPEnabled(self, status):
        self.i2c.writeBit(self.MPU6050_RA_USER_CTRL, self.MPU6050_USERCTRL_DMP_EN_BIT, status)

    def resetDMP(self):
        self.i2c.writeBit(self.MPU6050_RA_USER_CTRL, self.MPU6050_USERCTRL_DMP_RESET_BIT, True)

    def setMemoryBank(self, bank, prefetchEnabled=False, userBank=False):
        bank &= 0x1F

        if userBank:
            bank |= 0x20
        if prefetchEnabled:
            bank |= 0x40

        self.i2c.write8(self.MPU6050_RA_BANK_SEL, bank)
        return True

    def setMemoryStartAddress(self, address):
        self.i2c.write8(self.MPU6050_RA_MEM_START_ADDR, address)

    def readMemoryByte(self):
        result = self.i2c.readU8(self.MPU6050_RA_MEM_R_W)
        return result

    def writeMemoryByte(self, data):
        self.i2c.write8(self.MPU6050_RA_MEM_R_W, data)

    def readMemoryBlock(self):
        pass

    def writeMemoryBlock(self, data, dataSize, bank=0, address=0, verify=False):
        self.setMemoryBank(bank)
        self.setMemoryStartAddress(address)
        i = 0
        while i < dataSize:
            self.i2c.write8(self.MPU6050_RA_MEM_R_W, data[i])
            # Verify
            if verify:
                self.setMemoryBank(bank)
                self.setMemoryStartAddress(address)
                result = self.i2c.readU8(self.MPU6050_RA_MEM_R_W)

                if result != data[i]:
                    print(data[i]),
                    print(result),
                    print(address)
            # reset adress to 0 after reaching 255
            if address == 255:
                address = 0
                bank += 1
                self.setMemoryBank(bank)
            else:
                address += 1
            self.setMemoryStartAddress(address)
            # increase byte index
            i += 1

    def writeDMPConfigurationSet(self, data, dataSize, bank=0, address=0, verify=False):
        pos = 0
        while pos < dataSize:
            j = 0
            dmpConfSet = []
            while ((j < 4) or (j < dmpConfSet[2] + 3)):
                dmpConfSet.append(data[pos])
                j += 1
                pos += 1

            # write data or perform special action
            if dmpConfSet[2] > 0:
                # regular block of data to write
                self.writeMemoryBlock(dmpConfSet[3:], dmpConfSet[2], dmpConfSet[0], dmpConfSet[1], verify)
            else:
                if dmpConfSet[3] == 0x01:
                    self.i2c.write8(self.MPU6050_RA_INT_ENABLE, 0x32);  # single operation

    def getDMPConfig1(self):
        self.i2c.readU8(self.MPU6050_RA_DMP_CFG_1)

    def setDMPConfig1(self, config):
        self.i2c.write8(self.MPU6050_RA_DMP_CFG_1, config)

    def getDMPConfig2(self):
        return self.i2c.readU8(self.MPU6050_RA_DMP_CFG_2)

    def setDMPConfig2(self, config):
        self.i2c.write8(self.MPU6050_RA_DMP_CFG_2, config)

    def dmpPacketAvailable(self):
        return self.getFIFOCount() >= self.dmpGetFIFOPacketSize()

    def dmpGetFIFOPacketSize(self):
        return self.dmpPacketSize

    def dmpGetAccel(self):
        pass
    #  四元数，w: 是标量部分（也称为实部） x, y, z: 是矢量部分（也称为虚部）
    def dmpGetQuaternion(self, packet):
        # We are dealing with signed bytes
        if packet[0] > 127: packet[0] -= 256
        if packet[4] > 127: packet[4] -= 256
        if packet[8] > 127: packet[8] -= 256
        if packet[12] > 127: packet[12] -= 256
        w = ((packet[0] << 8) + packet[1]) / 16384.0
        x = ((packet[4] << 8) + packet[5]) / 16384.0
        y = ((packet[8] << 8) + packet[9]) / 16384.0
        z = ((packet[12] << 8) + packet[13]) / 16384.0
        return (w, x, y, z)

    # gx：X轴上的角速度读数。
    # gy：Y轴上的角速度读数。
    # gz：Z轴上的角速度读数 通过陀螺仪
    def dmpGetGyro(self, packet):
        if packet[16] > 127: packet[16] -= 256
        if packet[20] > 127: packet[20] -= 256
        if packet[24] > 127: packet[24] -= 256
        gx = ((packet[16] << 8) + packet[17])
        gy = ((packet[20] << 8) + packet[21])
        gz = ((packet[24] << 8) + packet[25])
        return (gx, gy, gz)

    # 获取俯仰角，偏航角。。。通过四元组
    def dmpGetEuler(self, w, x, y, z):
        yaw = atan2(2 * x * y - 2 * w * z, 2 * w * w + 2 * x * x - 1) * 180 / pi
        pitch = -safe_asin(2 * x * z + 2 * w * y) * 180 / pi
        roll = atan2(2 * y * z - 2 * w * x, 2 * w * w + 2 * z * z - 1) * 180 / pi
        return (yaw, pitch, roll)

    # x，y，z的加速度分量
    def dmpGetGravity(self, q):
        data = {
            'x': float(2 * (q['x'] * q['z'] - q['w'] * q['y'])),
            'y': float(2 * (q['w'] * q['x'] + q['y'] * q['z'])),
            'z': float(q['w'] * q['w'] - q['x'] * q['x'] - q['y'] * q['y'] + q['z'] * q['z'])}
        return data

    #结合了四元数和重力向量，通常用于更复杂或动态的环境中
    def dmpGetYawPitchRoll(self, q, g):
        data = {
            # yaw: (about Z axis)
            'yaw': atan2(2 * q['x'] * q['y'] - 2 * q['w'] * q['z'], 2 * q['w'] * q['w'] + 2 * q['x'] * q['x'] - 1),
            # pitch: (nose up/down, about Y axis)
            'pitch': atan(g['x'] / pow(g['y'] * g['y'] + g['z'] * g['z'], 0.5)),
            # roll: (tilt left/right, about X axis)
            'roll': atan(g['y'] / pow(g['x'] * g['x'] + g['z'] * g['z'], 0.5))}
        return data

    def dmpInitialize(self):
        # Resetting MPU6050
        self.reset()
        time.sleep_ms(500)  # wait after reset

        # Disable sleep mode
        self.setSleepEnabled(False)

        # get MPU hardware revision
        self.setMemoryBank(0x10, True, True)  # Selecting user bank 16
        self.setMemoryStartAddress(0x06)  # Selecting memory byte 6
        hwRevision = self.readMemoryByte()  # Checking hardware revision
        # print('Revision @ user[16][6] ='),
        # print(hex(hwRevision))
        self.setMemoryBank(0, False, False)  # Resetting memory bank selection to 0

        # get X/Y/Z gyro offsets
        xgOffset = self.getXGyroOffset()
        ygOffset = self.getYGyroOffset()
        zgOffset = self.getZGyroOffset()

        # Enable pass through mode
        self.setI2CBypassEnabled(True)

        # load DMP code into memory banks
        self.writeMemoryBlock(self.dmpMemory, self.MPU6050_DMP_CODE_SIZE, 0, 0, False)
        # print('Success! DMP code written and verified')

        # write DMP configuration
        self.writeDMPConfigurationSet(self.dmpConfig, self.MPU6050_DMP_CONFIG_SIZE, 0, 0, False)
        # print('Success! DMP configuration written and verified')

        # Setting clock source to Z Gyro
        self.setClockSource(self.MPU6050_CLOCK_PLL_ZGYRO)

        # Setting DMP and FIFO_OFLOW interrupts enabled
        self.setIntEnabled(0x12)

        # Setting sample rate to 200Hz
        self.setRate(4)  # 1khz / (1 + 4) = 200 Hz [9 = 100 Hz]

        # Setting external frame sync to TEMP_OUT_L[0]
        self.setExternalFrameSync(self.MPU6050_EXT_SYNC_TEMP_OUT_L)

        # Setting DLPF bandwidth to 42Hz
        self.setDLPFMode(self.MPU6050_DLPF_BW_42)

        # Setting gyro sensitivity to +/- 2000 deg/sec
        self.setFullScaleGyroRange(self.MPU6050_GYRO_FS_2000)

        # Setting DMP configuration bytes (function unknown)
        self.setDMPConfig1(0x03)
        self.setDMPConfig2(0x00)

        # Clearing OTP Bank flag
        self.setOTPBankValid(False)

        # Setting X/Y/Z gyro offsets to previous values
        # self.setXGyroOffset(xgOffset);
        # self.setYGyroOffset(ygOffset);
        # self.setZGyroOffset(zgOffset);

        # Setting X/Y/Z gyro user offsets to zero
        self.setXGyroOffsetUser(0)
        self.setYGyroOffsetUser(0)
        self.setZGyroOffsetUser(0)

        # Writing final memory update 1/7 (function unknown)
        pos = 0
        j = 0
        dmpUpdate = []
        while ((j < 4) or (j < dmpUpdate[2] + 3)):
            dmpUpdate.append(self.dmpUpdates[pos])
            j += 1
            pos += 1

        self.writeMemoryBlock(dmpUpdate[3:], dmpUpdate[2], dmpUpdate[0], dmpUpdate[1], True)

        # Writing final memory update 2/7 (function unknown)
        j = 0
        dmpUpdate = []
        while ((j < 4) or (j < dmpUpdate[2] + 3)):
            dmpUpdate.append(self.dmpUpdates[pos])
            j += 1
            pos += 1

        self.writeMemoryBlock(dmpUpdate[3:], dmpUpdate[2], dmpUpdate[0], dmpUpdate[1], True)

        # Resetting FIFO
        self.resetFIFO()

        # Reading FIFO count
        fifoCount = self.getFIFOCount()
        # print('Current FIFO count = %s' % fifoCount)

        # Setting motion detection threshold to 2
        self.setMotionDetectionThreshold(2)

        # Setting zero-motion detection threshold to 156
        self.setZeroMotionDetectionThreshold(156)

        # Setting motion detection duration to 80
        self.setMotionDetectionDuration(80)

        # Setting zero-motion detection duration to 0
        self.setZeroMotionDetectionDuration(0)

        # Resetting FIFO
        self.resetFIFO()

        # Enabling FIFO
        self.setFIFOEnabled(True)

        # Enabling DMP
        self.setDMPEnabled(True)

        # Resetting DMP
        self.resetDMP()

        # Writing final memory update 3/7 (function unknown)
        j = 0
        dmpUpdate = []
        while ((j < 4) or (j < dmpUpdate[2] + 3)):
            dmpUpdate.append(self.dmpUpdates[pos])
            j += 1
            pos += 1

        self.writeMemoryBlock(dmpUpdate[3:], dmpUpdate[2], dmpUpdate[0], dmpUpdate[1], True)

        # Writing final memory update 4/7 (function unknown)
        j = 0
        dmpUpdate = []
        while ((j < 4) or (j < dmpUpdate[2] + 3)):
            dmpUpdate.append(self.dmpUpdates[pos])
            j += 1
            pos += 1

        self.writeMemoryBlock(dmpUpdate[3:], dmpUpdate[2], dmpUpdate[0], dmpUpdate[1], True)

        # Writing final memory update 5/7 (function unknown)
        j = 0
        dmpUpdate = []
        while ((j < 4) or (j < dmpUpdate[2] + 3)):
            dmpUpdate.append(self.dmpUpdates[pos])
            j += 1
            pos += 1

        self.writeMemoryBlock(dmpUpdate[3:], dmpUpdate[2], dmpUpdate[0], dmpUpdate[1], True)

        # Waiting for FIFO count > 2
        while (self.getFIFOCount() < 3):
            fifoCount = self.getFIFOCount()
        # print('Current FIFO count ='),
        # print(fifoCount)

        # Reading FIFO data
        self.getFIFOBytes(fifoCount)

        # Writing final memory update 6/7 (function unknown)
        j = 0
        dmpUpdate = []
        while ((j < 4) or (j < dmpUpdate[2] + 3)):
            dmpUpdate.append(self.dmpUpdates[pos])
            j += 1
            pos += 1

        self.writeMemoryBlock(dmpUpdate[3:], dmpUpdate[2], dmpUpdate[0], dmpUpdate[1], True)

        # Writing final memory update 7/7 (function unknown)
        j = 0
        dmpUpdate = []
        while ((j < 4) or (j < dmpUpdate[2] + 3)):
            dmpUpdate.append(self.dmpUpdates[pos])
            j += 1
            pos += 1

        self.writeMemoryBlock(dmpUpdate[3:], dmpUpdate[2], dmpUpdate[0], dmpUpdate[1], True)

        # Disabling DMP (you turn it on later)
        self.setDMPEnabled(False)

        # Setting up internal 42-byte (default) DMP packet buffer
        self.dmpPacketSize = 42

        # Resetting FIFO and clearing INT status one last time
        self.resetFIFO()
        self.getIntStatus()


class mpuHelper:
    def __init__(self, bias=(-112, -5.4, 1)):
        self.mpu = MPU6050()
        self.mpu.dmpInitialize()
        self.mpu.setDMPEnabled(True)
        self.packetSize = self.mpu.dmpGetFIFOPacketSize()
        self.bias = bias

    def Wait4Ypr(self):
        while self.mpu.getIntStatus() < 2:
            time.sleep_ms(10)
        fifoCount = self.mpu.getFIFOCount()

        if fifoCount == 1024:
            self.mpu.resetFIFO()
            print('FIFO overflow!')
        fifoCount = self.mpu.getFIFOCount()

        while fifoCount < self.packetSize:
            fifoCount = self.mpu.getFIFOCount()

        result = self.mpu.getFIFOBytes(self.packetSize)
        q = self.mpu.dmpGetQuaternion(result)
        data = {
            "w": q[0],
            "x": q[1],
            "y": q[2],
            "z": q[3]
        }
        print(data['x'])
        g = self.mpu.dmpGetGravity(data)
        yqr = self.mpu.dmpGetYawPitchRoll(data, g)
        ypr = (yqr['yaw'] * 180 / math.pi + self.bias[0], yqr['pitch'] * 180 / math.pi + self.bias[1],
               yqr['roll'] * 180 / math.pi + self.bias[2])
        print(ypr[0], ypr[1], ypr[2])
        return ypr


# while True:
#     # MPU
#     mpuIntStatus = mpu.getIntStatus()
#     fifoCount = mpu.getFIFOCount()
#     if mpuIntStatus < 2 or fifoCount == 1024:
#         mpu.resetFIFO()
#
#         continue
#     while fifoCount < packetSize:
#         fifoCount = mpu.getFIFOCount()
#     fifoCount -= packetSize
#     fifoBuffer = mpu.getFIFOBytes(packetSize)
#     yaw, rol, pit = mpu.dmpGetEuler(*mpu.dmpGetQuaternion(fifoBuffer))
#     g_pit, g_rol, g_yaw = mpu.dmpGetGyro(fifoBuffer)
#     print(yaw, pit, rol)
helper = mpuHelper(bias=(0, -5.4, 1))
while True:
    helper.Wait4Ypr()
