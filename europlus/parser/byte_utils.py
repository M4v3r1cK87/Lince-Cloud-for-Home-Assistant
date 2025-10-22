
# byte_utils.py
"""
Funzioni di utilità per la manipolazione di byte e bit.
"""

class ByteUtils:
    @staticmethod
    def bindec(binary_string):
        return int(str(binary_string).replace(" ", "").replace("[01]", ""), 2)

    @staticmethod
    def bcd2str(bcd):
        high = (bcd & 0xf0) >> 4
        low = bcd & 0x0f
        return f"{high}{low}"

    @staticmethod
    def bcd2int(bcd):
        high = (bcd & 0xf0) >> 4
        return (bcd & 0x0f) + (high * 10)

    @staticmethod
    def int2bcd(data):
        temp = int(data) % 10
        d_temp = int(data) // 10
        temp |= d_temp << 4
        return temp

    @staticmethod
    def get_bits(n, p=0, q=1):
        arr = []
        nn = int(n)
        t = p + q
        for i in range(p + 1, t + 1):
            arr.append((nn >> (i - 1)) & 1)
        arr.reverse()
        return int(''.join(str(x) for x in arr), 2)

    @staticmethod
    def array_int_to_string(arr):
        return ''.join(chr(x) for x in arr if 32 <= x <= 122).strip()

    @staticmethod
    def hexstring_to_array_int(hexstring, check_ff=False):
        arr = [int(hexstring[i:i+2], 16) for i in range(0, len(hexstring), 2)]
        if check_ff:
            arr = [0 if x == 255 else x for x in arr]
        return arr

    @staticmethod
    def bytes2int(*args):
        return sum(cur << (idx * 8) for idx, cur in enumerate(args))

    @staticmethod
    def reverse_bits(b):
        b = ((b & 0xF0) >> 4) | ((b & 0x0F) << 4)
        b = ((b & 0xCC) >> 2) | ((b & 0x33) << 2)
        b = ((b & 0xAA) >> 1) | ((b & 0x55) << 1)
        return b

