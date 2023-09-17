# MicroPython SSD1306 OLED driver, I2C and SPI interfaces Modified by Bigrich-Luo

import time
import framebuf
from micropython import const

# SET_DISP | 0x00: 关闭显示。
#
# SET_MEM_ADDR: 设置内存地址模式。该命令后通常跟一个字节，指定地址模式（水平、垂直、或页面）。
#
# SET_DISP_START_LINE | 0x00: 设置显示开始行。可以用于滚动显示。
#
# SET_SEG_REMAP | 0x01: 列地址重映射。该命令通常用于改变显示方向。
#
# SET_MUX_RATIO: 设置多路复用比例。此命令后通常跟一个字节，用于设置屏幕高度。
#
# SET_COM_OUT_DIR | 0x08: 设置COM输出扫描方向。用于设置OLED屏幕的扫描方向。
#
# SET_DISP_OFFSET: 设置显示偏移。可以用于垂直移动整个显示内容。
#
# SET_COM_PIN_CFG: 设置COM引脚硬件配置。此命令后通常跟一个字节，用于配置COM引脚。
#
# SET_DISP_CLK_DIV: 设置显示时钟分频因子和振荡器频率。
#
# SET_PRECHARGE: 设置预充电周期。用于设置像素点的预充电时间。
#
# SET_VCOM_DESEL: 设置VCOMH去选电平。
#
# SET_CONTRAST: 设置对比度。此命令后通常跟一个字节，用于设置显示对比度。
#
# SET_ENTIRE_ON: 全屏显示开/关。可以用于强制全屏显示。
#
# SET_NORM_INV: 设置显示模式为正常或反相。
#
# SET_CHARGE_PUMP: 设置电荷泵设置。此命令后通常跟一个字节，用于开启或关闭内置电荷泵。
#
# SET_DISP | 0x01: 打开显示。

# register definitions
SET_CONTRAST = const(0x81)
SET_ENTIRE_ON = const(0xa4)
SET_NORM_INV = const(0xa6)
SET_DISP = const(0xae)
SET_MEM_ADDR = const(0x20)
SET_COL_ADDR = const(0x21)
SET_PAGE_ADDR = const(0x22)
SET_DISP_START_LINE = const(0x40)
SET_SEG_REMAP = const(0xa0)
SET_MUX_RATIO = const(0xa8)
SET_COM_OUT_DIR = const(0xc0)
SET_DISP_OFFSET = const(0xd3)
SET_COM_PIN_CFG = const(0xda)
SET_DISP_CLK_DIV = const(0xd5)
SET_PRECHARGE = const(0xd9)
SET_VCOM_DESEL = const(0xdb)
SET_CHARGE_PUMP = const(0x8d)


class SSD1306:
    # external_vcc 外部电源
    def __init__(self, width, height, external_vcc):
        self.width = width
        self.height = height
        self.external_vcc = external_vcc
        self.pages = self.height // 8
        # 子类必须将self.framebuf初始化为帧缓冲区。
        # 这是必要的，因为底层数据缓冲区不同 在I2C和SPI实现之间（I2C需要额外的字节）。
        self.poweron()
        self.init_display()

    # 初始化显示屏 init_display
    def init_display(self):
        for cmd in (
                SET_DISP | 0x00,  # off
                # address setting
                SET_MEM_ADDR, 0x00,  # horizontal
                # resolution and layout
                SET_DISP_START_LINE | 0x00,
                SET_SEG_REMAP | 0x01,  # column addr 127 mapped to SEG0
                SET_MUX_RATIO, self.height - 1,
                SET_COM_OUT_DIR | 0x08,  # scan from COM[N] to COM0
                SET_DISP_OFFSET, 0x00,
                SET_COM_PIN_CFG, 0x02 if self.height == 32 else 0x12,
                # timing and driving scheme
                SET_DISP_CLK_DIV, 0x80,
                SET_PRECHARGE, 0x22 if self.external_vcc else 0xf1,
                SET_VCOM_DESEL, 0x30,  # 0.83*Vcc
                # display
                SET_CONTRAST, 0xff,  # maximum
                SET_ENTIRE_ON,  # output follows RAM contents
                SET_NORM_INV,  # not inverted
                # charge pump
                SET_CHARGE_PUMP, 0x10 if self.external_vcc else 0x14,
                SET_DISP | 0x01):  # on
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    # 关闭电源 poweroff
    def poweroff(self):
        self.write_cmd(SET_DISP | 0x00)

    # 调整对比度 contrast
    def contrast(self, contrast):
        self.write_cmd(SET_CONTRAST)
        self.write_cmd(contrast)

    def invert(self, invert):
        self.write_cmd(SET_NORM_INV | (invert & 1))

    # 更新显示 show
    def show(self):
        x0 = 0
        x1 = self.width - 1
        if self.width == 64:
            # displays with width of 64 pixels are shifted by 32
            x0 += 32
            x1 += 32
        self.write_cmd(SET_COL_ADDR)
        self.write_cmd(x0)
        self.write_cmd(x1)
        self.write_cmd(SET_PAGE_ADDR)
        self.write_cmd(0)
        self.write_cmd(self.pages - 1)
        self.write_framebuf()

    # 填充屏幕 fill col 颜色
    def fill(self, col):
        self.framebuf.fill(col)

    # 设置像素 pixel
    def pixel(self, x, y, col):
        self.framebuf.pixel(x, y, col)

    # 滚动显示 scroll
    def scroll(self, dx, dy):
        self.framebuf.scroll(dx, dy)

    # 文字显示 text
    def text(self, string, x, y, col=1):
        self.framebuf.text(string, x, y, col)


class SSD1306_I2C(SSD1306):
    def __init__(self, width, height, i2c, addr=0x3c, external_vcc=False):
        self.i2c = i2c
        self.addr = addr
        self.temp = bytearray(2)
        # 向数据缓冲区添加一个额外的字节0x40以保存I2C数据/命令字节以使用硬件兼容的I2C接口。
        # python 创建一个切片会重新拷贝一份数据，所以这里使用memoryview，指向原始 buffer 的内存的一个“视图”。
        self.buffer = bytearray(((height // 8) * width) + 1)
        self.buffer[0] = 0x40  # Set first byte of data buffer to Co=0, D/C=1
        self.framebuf = framebuf.FrameBuffer1(memoryview(self.buffer)[1:], width, height)
        super().__init__(width, height, external_vcc)

    def write_cmd(self, cmd):
        self.temp[0] = 0x80  # Co=1, D/C#=0
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_framebuf(self):
        # Blast out the frame buffer using a single I2C transaction to support
        # hardware I2C interfaces.
        self.i2c.writeto(self.addr, self.buffer)

    def poweron(self):
        pass


class SSD1306_SPI(SSD1306):
    def __init__(self, width, height, spi, dc, res, cs, external_vcc=False):
        self.rate = 10 * 1024 * 1024
        dc.init(dc.OUT, value=0)
        res.init(res.OUT, value=0)
        cs.init(cs.OUT, value=1)
        self.spi = spi
        self.dc = dc
        self.res = res
        self.cs = cs
        self.buffer = bytearray((height // 8) * width)
        self.framebuf = framebuf.FrameBuffer1(self.buffer, width, height)
        super().__init__(width, height, external_vcc)

    def write_cmd(self, cmd):
        self.spi.init(baudrate=self.rate, polarity=0, phase=0)
        self.cs.on()
        self.dc.off()
        self.cs.off()
        self.spi.write(bytearray([cmd]))
        self.cs.on()

    def write_framebuf(self):
        self.spi.init(baudrate=self.rate, polarity=0, phase=0)
        self.cs.on()
        self.dc.on()
        self.cs.off()
        self.spi.write(self.buffer)
        self.cs.on()

    def poweron(self):
        self.res.on()
        time.sleep_ms(1)
        self.res.off()
        time.sleep_ms(10)
        self.res.on()
