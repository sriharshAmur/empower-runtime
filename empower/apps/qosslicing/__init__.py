"""QoS Slicing app."""

from empower_core.app import EVERY
# 2000 ms

MANIFEST = {
    "label": "QoS Slicing",
    "desc": "Manages Slices and creates traffic rules",
    "params": {
        # "message": {
        #     "desc": "The message to be printed.",
        #     "mandatory": False,
        #     "default": "World",
        #     "type": "str"
        # },
        "every": {
            "desc": "The control loop period (in ms).",
            "mandatory": False,
            "default": EVERY,
            "type": "int"
        }
    }
}
