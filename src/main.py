from requests import get, post
from json import loads, dumps
from typing import List, Dict, Tuple, Union
from collections import defaultdict
from time import sleep


def rec_dd():
    return defaultdict(rec_dd)


class WLED(object):
    """
    Base class responsible for the storage of device state and the ability to load/save states from a file

    """

    def __init__(self, ip_addr: str):
        self.ip_addr = ip_addr

        self.state: Dict = defaultdict(rec_dd)
        self.info: Dict = {}
        self.effects: List[str] = []
        self.palettes: List[str] = []

        self.pull_state()

    @property
    def _state_url(self):
        return "/".join(("http:/", self.ip_addr, "json", "state"))

    @property
    def loaded(self):
        state_valid = len(self.state.keys()) != 0
        info_valid = len(self.info.keys()) != 0
        effects_valid = len(self.effects) != 0
        palettes_valid = len(self.palettes) != 0
        return state_valid and info_valid and effects_valid and palettes_valid

    def get_json(self, endpoint):
        r = get("/".join(("http:/", self.ip_addr, "json", endpoint)))
        # print(r.text)
        return loads(r.text)

    def pull_state(self):
        self.state = self.get_json("state")
        self.info = self.get_json("info")
        self.effects: List[str] = self.get_json("eff")
        self.palettes = self.get_json("pal")

    def push_state(self, get_resp: bool = False):
        if get_resp:
            self.state.update({"v": get_resp})

        r = post(self._state_url, json=self.state)

        if get_resp:
            # print(self.state)
            self.state = loads(r.text)

    def save_state_file(self, file_name: str):
        with open(f"./saved_states/{file_name}.json", mode="w") as f:
            f.write(dumps(self.state))

    def load_state_file(self, file_name: str):
        with open(f"./saved_states/{file_name}.json", mode="r") as f:
            self.state = loads(f.read())


class TypeVerificationMixin(object):
    @staticmethod
    def _verify_bool(val: bool):
        return bool(val)

    @staticmethod
    def _verify_int8bit(val: int):
        val = int(val)
        if (val > 255) or (val < 1):
            raise ValueError
        return val

    @staticmethod
    def _verify_range(val: int, min_val: int, max_val: int):
        val = int(val)
        if (val > max_val) or (val < min_val):
            raise ValueError
        return val


class ParentAccessor(object):
    def __init__(self, accessor, setter):
        self._accessor = accessor
        self._setter = setter


class NightlightProperty(ParentAccessor, TypeVerificationMixin):
    MODE_INSTANT = "instant"
    MODE_FADE = "fade"
    MODE_COLOR_FADE = "color fade"
    MODE_SUNRISE = "sunrise"

    _MODE_MAP = {
        MODE_INSTANT: 0,
        MODE_FADE: 1,
        MODE_COLOR_FADE: 2,
        MODE_SUNRISE: 3
    }

    @property
    def on(self) -> bool:
        return self._accessor("on")

    @on.setter
    def on(self, value: bool):
        self._setter("on", self._verify_bool(value))

    @property
    def duration_minutes(self) -> int:
        return self._accessor("dur")

    @duration_minutes.setter
    def duration_minutes(self, value: int):
        self._setter("dur", self._verify_int8bit(value))

    @property
    def mode(self):
        return self._accessor("mode")

    @mode.setter
    def mode(self, value):
        try:
            value = self._MODE_MAP[value]
        except KeyError:
            pass
        value = int(value)
        self._setter("mode", self._verify_range(value, 0, 3))

    @property
    def target_brightness(self) -> int:
        return self._accessor("tbri")

    @target_brightness.setter
    def target_brightness(self, value: int):
        self._setter("tbri", self._verify_int8bit(value))

    @property
    def remaining_seconds(self) -> int:
        return self._accessor("rem")


class SegmentItem(ParentAccessor, TypeVerificationMixin):
    """
    Due to indexing complications, the segment ID is passed into the constructor
    and is used to get the segment index when getting/setting
    """

    def __init__(self, accessor, setter, info_accessor, seg_id):
        super().__init__(accessor, setter)
        self._info_accessor = info_accessor
        self._seg_id = seg_id

    @property
    def _this_item(self):
        return self._accessor(self._seg_id)

    @property
    def start(self) -> int:
        return self._this_item["start"]

    @start.setter
    def start(self, value: int):
        self._setter(self._seg_id, self._verify_int8bit(value))


class SegmentListProperty(ParentAccessor, TypeVerificationMixin):

    def __init__(self, accessor, setter, info_accessor):
        super().__init__(accessor, setter)
        self._info_accessor = info_accessor

    def __getitem__(self, item: int):
        max_seg = self._info_accessor("leds")["maxseg"]
        print(f"max_seg: {max_seg}")
        if item < max_seg:
            return SegmentItem(
                self._accessor,
                self._setter,
                self._info_accessor,
                item
            )

    @property
    def duration_minutes(self) -> int:
        return self._accessor("dur")

    @duration_minutes.setter
    def duration_minutes(self, value: int):
        self._setter("dur", self._verify_int8bit(value))


class PropertyWLED(WLED, TypeVerificationMixin):
    """
    Written referencing: https://kno.wled.ge/interfaces/json-api/


    #todo:
    tt
    ps
    pss
    psave
    pl

    udpn.send
    udpn.recv
    udpn.nn

    rb
    lor
    time
    mainseg
    seg
    playlist
    """

    def __init__(self, ip_addr: str):
        super().__init__(ip_addr)

        self._nightlight_interface = NightlightProperty(
            accessor=lambda k: self.state["nl"].__getitem__(k),
            setter=lambda k, v: self.state["nl"].__setitem__(k, v)
        )

        self._segment_interface = SegmentListProperty(
            accessor=lambda k: self.state["seg"].__getitem__(k),
            setter=lambda k, v: self.state["seg"].__setitem__(k, v),
            info_accessor=lambda k: self.info.__getitem__(k)
        )

    @property
    def on(self) -> bool:
        return self.state["on"]

    @on.setter
    def on(self, value: bool):
        self.state["on"] = self._verify_bool(value)

    @property
    def brightness(self) -> int:
        return self.state["bri"]

    @brightness.setter
    def brightness(self, value: int):
        self.state["bri"] = self._verify_int8bit(value)

    @property
    def transition(self) -> int:
        return self.state["transition"]

    @transition.setter
    def transition(self, value: int):
        self.state["transition"] = self._verify_int8bit(value)

    @property
    def nightlight(self):
        return self._nightlight_interface

    @property
    def segment(self):
        return self._segment_interface

    def reboot_wled(self):
        self.state = {"rb": True}
        self.push_state()


if __name__ == '__main__':
    led = PropertyWLED("10.10.10.125")

    led.segment[0]


    def reboot():
        led.reboot_wled()


    def run_app():
        led.on = True
        led.brightness = 100


    # reboot()
    led.save_state_file("comp2")

    # led.nightlight.on = False

    # led.nightlight.duration_minutes = 1
    # led.nightlight.mode = NightlightProperty.MODE_FADE

    # led.push_state(get_resp=True)

    # led.save_state_file("testing2")

    # print(led.nightlight.remaining_seconds)

    # led.load_state_file("police")

    # led.save_state_file("nightlight test")

    # led.turn_off()

    # rdd = defaultdict(rec_dd)
