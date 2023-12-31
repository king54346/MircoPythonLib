from machine import I2C

from common.MPU6050RPI import MPU6050

i2c_bus = I2C(scl=2, sda=4, freq=115200)
device_address = 0x68
# The offsets are different for each device and should be changed
# accordingly using a calibration procedure
x_accel_offset = 1340
y_accel_offset = -150
z_accel_offset = 3085
x_gyro_offset = 86
y_gyro_offset = 19
z_gyro_offset = 74
enable_debug_output = True

mpu = MPU6050(i2c_bus, device_address, x_accel_offset, y_accel_offset,
              z_accel_offset, x_gyro_offset, y_gyro_offset, z_gyro_offset,
              enable_debug_output)

mpu.dmp_initialize()
mpu.set_DMP_enabled(True)
mpu_int_status = mpu.get_int_status()
print(hex(mpu_int_status))

packet_size = mpu.DMP_get_FIFO_packet_size()
print(packet_size)
FIFO_count = mpu.get_FIFO_count()
print(FIFO_count)

count = 0
FIFO_buffer = [0] * 64

FIFO_count_list = list()
while count < 10000:
    FIFO_count = mpu.get_FIFO_count()
    mpu_int_status = mpu.get_int_status()

    # If overflow is detected by status or fifo count we want to reset
    if (FIFO_count == 1024) or (mpu_int_status & 0x10):
        mpu.reset_FIFO()
        # print('overflow!')
    # Check if fifo data is ready
    elif (mpu_int_status & 0x02):
        # Wait until packet_size number of bytes are ready for reading, default
        # is 42 bytes
        while FIFO_count < packet_size:
            FIFO_count = mpu.get_FIFO_count()
        FIFO_buffer = mpu.get_FIFO_bytes(packet_size)
        accel = mpu.DMP_get_acceleration_int16(FIFO_buffer)
        quat = mpu.DMP_get_quaternion_int16(FIFO_buffer)
        grav = mpu.DMP_get_gravity(quat)
        roll_pitch_yaw = mpu.DMP_get_euler_roll_pitch_yaw(quat, grav)
        if count % 10 == 0:
            print('roll: ' + str(roll_pitch_yaw.x))
            print('pitch: ' + str(roll_pitch_yaw.y))
            print('yaw: ' + str(roll_pitch_yaw.z))
        count += 1
