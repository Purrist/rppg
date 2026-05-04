# -*- coding: utf-8 -*-
import struct
import serial
import serial.tools.list_ports
import time

PORT = "COM9"
BAUD = 115200

def verify_cksum(buf, cksum):
    acc = 0
    for b in buf:
        acc ^= b
    return (~acc & 0xFF) == cksum

def float_le(b):
    return struct.unpack('<f', b)[0]

def list_ports():
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("未找到串口设备！")
        return []
    print("\n可用串口:")
    for i, p in enumerate(ports):
        print("  %d. %s - %s" % (i+1, p.device, p.description))
    return [p.device for p in ports]

def main():
    print("=" * 60)
    print("HLK-LD6002 雷达数据测试")
    print("=" * 60)
    
    list_ports()
    
    print("\n尝试连接 %s @ %s bps..." % (PORT, BAUD))
    
    ser = None
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.005)
        print("✓ 串口连接成功！")
    except Exception as e:
        print("✗ 串口连接失败:", e)
        return
    
    buf = b""
    print("\n开始接收数据... (按 Ctrl+C 退出)\n")
    print("-" * 60)
    
    try:
        while True:
            if ser.in_waiting > 0:
                buf += ser.read(ser.in_waiting)
                
                while len(buf) >= 8:
                    if buf[0] != 0x01:
                        buf = buf[1:]
                        continue
                    
                    dlen = (buf[3] << 8) | buf[4]
                    flen = 8 + dlen + (1 if dlen > 0 else 0)
                    
                    if len(buf) < flen or flen > 1024:
                        buf = buf[1:]
                        break
                    
                    frame = buf[:flen]
                    buf = buf[flen:]
                    
                    if not verify_cksum(frame[0:7], frame[7]):
                        continue
                    if dlen > 0 and not verify_cksum(frame[8:8+dlen], frame[8+dlen]):
                        continue
                    
                    tid = (frame[5] << 8) | frame[6]
                    fd = frame[8:8+dlen] if dlen > 0 else b""
                    
                    print("收到数据包: 0x%04X" % tid, end="")
                    
                    if tid == 0x0A13 and len(fd) >= 12:
                        total_phase = float_le(fd[0:4])
                        breath_phase = float_le(fd[4:8])
                        heart_phase = float_le(fd[8:12])
                        print(" - 相位数据: 心跳=%.4f, 呼吸=%.4f" % (heart_phase, breath_phase), end="")
                    
                    elif tid == 0x0A14 and len(fd) >= 4:
                        breath_rate = float_le(fd[:4])
                        print(" - 呼吸率: %.1f" % breath_rate, end="")
                    
                    elif tid == 0x0A15 and len(fd) >= 4:
                        heart_rate = float_le(fd[:4])
                        print(" - 心率: %.0f" % heart_rate, end="")
                    
                    elif tid == 0x0A16 and len(fd) >= 8:
                        flag = (fd[1] << 24) | (fd[2] << 16) | (fd[3] << 8) | fd[0]
                        distance = float_le(fd[4:8])
                        print(" - 距离: flag=%d, distance=%.2f" % (flag, distance), end="")
                    
                    elif tid == 0x0A17 and len(fd) >= 12:
                        x = float_le(fd[0:4])
                        y = float_le(fd[4:8])
                        z = float_le(fd[8:12])
                        print(" - 位置: x=%.3f, y=%.3f, z=%.3f" % (x, y, z), end="")
                    
                    elif tid == 0x0A18 and len(fd) >= 2:
                        target_count = (fd[1] << 8) | fd[0]
                        print(" - 目标数: %d" % target_count, end="")
                    
                    print()
            
            time.sleep(0.001)
    except KeyboardInterrupt:
        print("\n\n停止测试")
    finally:
        if ser and ser.is_open:
            ser.close()

if __name__ == '__main__':
    main()
