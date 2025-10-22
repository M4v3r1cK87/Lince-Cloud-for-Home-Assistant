"""Parser per centrali Lince Europlus."""

# Esponi le classi principali per import più puliti
from .parser import europlusParser

# Questo permette di fare:
# from europlus.parser import europlusParser
# invece di:
# from europlus.parser.parser import europlusParser

__all__ = [
    "europlusParser"
]