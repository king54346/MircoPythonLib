from machine import Pin

from common.uln2003 import Uln2003

motor = Uln2003(pin1=Pin(13), pin2=Pin(12), pin3=Pin(14), pin4=Pin(27), delay=2, mode='HALF_STEP')

motor.angle(360, 1)
