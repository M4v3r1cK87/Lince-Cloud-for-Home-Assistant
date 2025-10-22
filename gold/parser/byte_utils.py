"""Byte manipulation utilities for Gold parser."""
import logging
from typing import List, Union, Optional

_LOGGER = logging.getLogger(__name__)


def hexstring_to_bcd(hexstring: str) -> str:
    """Convert hex string to BCD representation."""
    try:
        # Implementazione semplificata - da verificare con dati reali
        return hexstring
    except Exception as e:
        _LOGGER.error(f"Error in hexstring_to_bcd: {e}")
        return hexstring


def bcd2int(value: int) -> int:
    """Convert BCD to integer."""
    try:
        # BCD: ogni nibble (4 bit) rappresenta una cifra decimale
        result = 0
        multiplier = 1
        while value > 0:
            digit = value & 0x0F
            if digit > 9:
                _LOGGER.warning(f"Invalid BCD digit: {digit}")
                return 0
            result += digit * multiplier
            multiplier *= 10
            value >>= 4
        return result
    except Exception as e:
        _LOGGER.error(f"Error in bcd2int: {e}")
        return 0


def int2bcd(value: int) -> int:
    """Convert integer to BCD."""
    try:
        result = 0
        shift = 0
        while value > 0:
            digit = value % 10
            result |= (digit << shift)
            shift += 4
            value //= 10
        return result
    except Exception as e:
        _LOGGER.error(f"Error in int2bcd: {e}")
        return 0


def array_int_to_string(arr: List[int]) -> str:
    """Convert array of integers to string."""
    try:
        # Filtra valori 0 e converti in caratteri
        result = ''.join(chr(x) for x in arr if x != 0 and x < 128)
        return result.strip()
    except Exception as e:
        _LOGGER.error(f"Error in array_int_to_string: {e}")
        return ""


def string_to_array_int(length: int, text: str) -> List[int]:
    """Convert string to fixed-length array of integers."""
    try:
        result = [0] * length
        for i, char in enumerate(text[:length]):
            result[i] = ord(char)
        return result
    except Exception as e:
        _LOGGER.error(f"Error in string_to_array_int: {e}")
        return [0] * length


def hexstring_to_array_int(hexstring: Union[str, List[int]], reverse: bool = False) -> List[int]:
    """
    Convert hex string to array of integers.
    If already a list, return as-is.
    """
    try:
        if isinstance(hexstring, list):
            return hexstring
            
        if isinstance(hexstring, str):
            # Rimuovi spazi e converti hex string in array di byte
            hexstring = hexstring.replace(" ", "")
            result = []
            for i in range(0, len(hexstring), 2):
                byte = int(hexstring[i:i+2], 16)
                result.append(byte)
            
            if reverse:
                result.reverse()
            
            return result
        
        return []
    except Exception as e:
        _LOGGER.error(f"Error in hexstring_to_array_int: {e}")
        return []
    