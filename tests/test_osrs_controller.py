from pathlib import Path
import runpy
import signal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts/osrs-controller"))
CONFIG = MODULE["DEFAULTS"]


def event(event_type, code, value):
    return SimpleNamespace(type=event_type, code=code, value=value)


class FakeDevice:
    def __init__(self, path, axis=0):
        self.path, self.name = path, "Sunshine Xbox Controller"
        self.axes = {0: axis, 16: 0, 17: 0}
        self.buttons = set()
        self.pending = []
        self.dead = False
        self.closed = 0

    def capabilities(self, **kwargs):
        return {3: [0, 16, 17], 1: [310, 311, 544, 545, 546, 547]}

    def absinfo(self, code):
        if self.dead:
            raise OSError("disconnected")
        return SimpleNamespace(min=-100, max=100, value=self.axes[code])

    def active_keys(self):
        return list(self.buttons)

    def read(self):
        if self.dead:
            raise OSError("disconnected")
        for item in self.pending:
            if item.type == 3:
                self.axes[item.code] = item.value
            elif item.type == 1:
                if item.value:
                    self.buttons.add(item.code)
                else:
                    self.buttons.discard(item.code)
            yield item
        self.pending = []

    def close(self):
        self.closed += 1


class ControllerTests(unittest.TestCase):
    def mapping(self):
        return MODULE["Mapping"](CONFIG)

    def test_bindings_and_unmapped_buttons(self):
        mapper = self.mapping()
        self.assertEqual(mapper.keys(-0.8, 0, -1, {310}), {"Left", "Up", "F1"})
        self.assertEqual(mapper.keys(0.8, 1, 0, {311}), {"Right", "Down", "F2"})
        self.assertEqual(mapper.keys(0, 0, 1, set()), {"F3"})
        self.assertEqual(mapper.keys(0, -1, 0, set()), {"F4"})
        # Face buttons, trigger buttons and stick clicks have no mapping.
        self.assertEqual(mapper.keys(0, 0, 0, {304, 305, 307, 308, 312, 313, 317, 318}), set())

    def test_dpad_buttons_are_supported_as_well_as_hats(self):
        self.assertEqual(self.mapping().keys(0, 0, 0, {544, 547}), {"F1", "F2"})

    def test_deadzone_hysteresis_and_reversal(self):
        mapper = self.mapping()
        self.assertEqual(mapper.keys(0.24, 0, 0, set()), set())
        self.assertEqual(mapper.keys(0.26, 0, 0, set()), {"Right"})
        self.assertEqual(mapper.keys(0.20, 0, 0, set()), {"Right"})
        self.assertEqual(mapper.keys(-0.20, 0, 0, set()), set())
        self.assertEqual(mapper.keys(-0.26, 0, 0, set()), {"Left"})
        self.assertEqual(mapper.keys(-0.17, 0, 0, set()), set())

    def test_signed_and_unsigned_stick_ranges(self):
        normalize = MODULE["normalized_axis"]
        for minimum, maximum in ((-32768, 32767), (0, 65535), (0, 255)):
            self.assertEqual(normalize(SimpleNamespace(min=minimum, max=maximum, value=minimum)), -1)
            self.assertEqual(normalize(SimpleNamespace(min=minimum, max=maximum, value=maximum)), 1)
            self.assertEqual(normalize(SimpleNamespace(min=minimum, max=maximum,
                                                      value=(minimum + maximum) / 2)), 0)

    def test_focus_switch_releases_keys_and_requires_neutral(self):
        events = []
        output = MODULE["Output"](lambda *event: events.append(event))
        output.update({"Left"}, 10)  # Already held when entering game: ignore.
        output.update(set(), 10)
        output.update({"Left"}, 10)
        output.update({"Left"}, 11)  # Switching between two account windows.
        output.update({"Left"}, 11)
        self.assertEqual(events, [("Left", True), ("Left", False)])
        output.update(set(), 11)
        output.update({"Right"}, 11)
        output.update({"Right"}, None)
        self.assertEqual(events[-2:], [("Right", True), ("Right", False)])

    def test_fkeys_pulse_once_and_camera_is_held_without_repeat_injection(self):
        events = []
        output = MODULE["Output"](lambda *event: events.append(event))
        output.update(set(), 10)
        for _ in range(10):
            output.update({"Up", "F2"}, 10)
        self.assertEqual(events, [("Up", True), ("F2", True), ("F2", False)])
        output.update({"Up"}, 10)
        output.update({"Up", "F2"}, 10)
        output.release()
        self.assertEqual(events[-3:], [("F2", True), ("F2", False), ("Up", False)])
        output.update({"Up"}, 10)
        self.assertFalse(output.held)

    def test_button_dpad_does_not_query_missing_hat_axes(self):
        device = Mock()
        device.capabilities.return_value = {3: [0], 1: [310, 311, 544]}
        device.absinfo.return_value = SimpleNamespace(min=-100, max=100, value=0)
        device.active_keys.return_value = [544]
        self.assertEqual(MODULE["snapshot"](device), (0, 0, 0, {544}))
        device.absinfo.assert_called_once_with(0)

    def test_device_filter_excludes_physical_gamepads_and_virtual_mouse(self):
        device = Mock(path="/dev/input/event10")
        device.name = "Xbox Series Controller"
        device.capabilities.return_value = {3: [0], 1: [310, 311]}
        eligible = MODULE["is_controller"]
        with patch.object(Path, "resolve", return_value=Path("/sys/devices/virtual/input/input10")):
            self.assertTrue(eligible(device, CONFIG["device_name"]))
            device.name = "Sunshine Mouse"
            device.capabilities.return_value = {3: [0], 1: [272]}
            self.assertFalse(eligible(device, CONFIG["device_name"]))
        with patch.object(Path, "resolve", return_value=Path("/sys/devices/pci0000/input/input10")):
            device.name = "Xbox Controller"
            device.capabilities.return_value = {3: [0], 1: [310, 311]}
            self.assertFalse(eligible(device, CONFIG["device_name"]))

    def simulate(self, devices, frames):
        run = MODULE["run"]
        available = {device.path: device for device in devices}
        evdev = SimpleNamespace(list_devices=lambda: list(available),
                                InputDevice=lambda path: available[path])
        x11 = Mock()
        handlers = {}
        clock, focus = [10], [10]
        x11.focus.side_effect = lambda: focus[0]
        frames = iter(frames)

        def poll(watched, *args):
            clock[0] += 1.1
            frame = next(frames, None)
            if frame is None:
                handlers[signal.SIGTERM](signal.SIGTERM, None)
                return [], [], []
            focus[0] = frame.get("focus", focus[0])
            for device in frame.get("add", []):
                available[device.path] = device
            for path in frame.get("remove", []):
                available.pop(path).dead = True
            for path, events in frame.get("events", {}).items():
                available[path].pending = events
            return [d for d in watched if d.pending or d.dead], [], []

        with patch.dict(run.__globals__, is_controller=lambda *args: True), \
                patch.object(MODULE["signal"], "signal", side_effect=lambda s, h: handlers.update({s: h})), \
                patch.object(MODULE["time"], "monotonic", side_effect=lambda: clock[0]), \
                patch.object(MODULE["select"], "select", side_effect=poll):
            run(CONFIG, evdev, x11)
        return [call.args for call in x11.emit.call_args_list]

    def test_disconnect_reconnect_and_signal_release_held_keys(self):
        first = FakeDevice("/dev/input/event26")
        second = FakeDevice("/dev/input/event29")
        events = self.simulate([first], [{},
            {"events": {first.path: [event(3, 0, -100)]}},
            {"remove": [first.path]}, {"add": [second]}, {},
            {"events": {second.path: [event(3, 0, 100)]}}])
        self.assertEqual(events,
                         [("Left", True), ("Left", False), ("Right", True), ("Right", False)])
        self.assertEqual((first.closed, second.closed), (1, 1))

    def test_idle_first_controller_does_not_hide_active_second_controller(self):
        old, handheld = FakeDevice("/dev/input/event26"), FakeDevice("/dev/input/event29")
        events = self.simulate([old, handheld], [{},
            {"events": {handheld.path: [event(3, 0, -100)]}},
            {"events": {handheld.path: [event(3, 0, 0), event(1, 310, 1), event(1, 310, 0)]}},
            {"events": {handheld.path: [event(1, 544, 1), event(1, 544, 0)]}}])
        self.assertEqual(events, [("Left", True), ("Left", False),
                                 ("Up", True), ("Up", False), ("F1", True), ("F1", False)])

    def test_hotplug_is_discovered_while_old_controller_remains_connected(self):
        old, handheld = FakeDevice("/dev/input/event26"), FakeDevice("/dev/input/event29")
        events = self.simulate([old], [{}, {"add": [handheld]}, {},
            {"events": {handheld.path: [event(1, 311, 1), event(1, 311, 0)]}}])
        self.assertEqual(events, [("Down", True), ("Down", False)])

    def test_switch_releases_previous_camera_and_ignores_inactive_release(self):
        first, second = FakeDevice("/dev/input/event26"), FakeDevice("/dev/input/event29")
        events = self.simulate([first, second], [{},
            {"events": {first.path: [event(3, 0, -100)]}},
            {"events": {second.path: [event(3, 0, 100)]}},
            {"events": {first.path: [event(3, 0, 0)]}}])
        self.assertEqual(events, [("Left", True), ("Left", False),
                                 ("Right", True), ("Right", False)])

    def test_stale_held_input_and_right_stick_do_not_select_controller(self):
        stale, handheld = FakeDevice("/dev/input/event26", axis=-100), FakeDevice("/dev/input/event29")
        events = self.simulate([stale, handheld], [{},
            {"events": {handheld.path: [event(1, 310, 1)]}},
            {"events": {stale.path: [event(3, 0, -90), event(3, 3, 100)]}}])
        self.assertEqual(events, [("Up", True), ("Up", False)])

    def test_inactive_button_release_does_not_steal_selection_with_other_button_held(self):
        first, second = FakeDevice("/dev/input/event26"), FakeDevice("/dev/input/event29")
        events = self.simulate([first, second], [{},
            {"events": {first.path: [event(1, 310, 1), event(1, 311, 1)]}},
            {"events": {second.path: [event(3, 0, 100)]}},
            {"events": {first.path: [event(1, 310, 0)]}}])
        self.assertEqual(events, [("Up", True), ("Down", True),
                                 ("Down", False), ("Up", False),
                                 ("Right", True), ("Right", False)])

    def test_focus_loss_and_return_require_neutral_on_active_controller(self):
        pad = FakeDevice("/dev/input/event29")
        events = self.simulate([pad], [{},
            {"events": {pad.path: [event(3, 0, -100)]}},
            {"focus": None}, {"focus": 11}, {},
            {"events": {pad.path: [event(3, 0, 0)]}},
            {"events": {pad.path: [event(3, 0, 100)]}}])
        self.assertEqual(events, [("Left", True), ("Left", False),
                                 ("Right", True), ("Right", False)])

    def test_config_validation_and_partial_overrides(self):
        load = MODULE["load_config"]
        with patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "read_text", return_value='{"dpad": {"up": "F4"}}'):
            self.assertEqual(load(Path("unused"))["dpad"],
                             {"up": "F4", "right": "F2", "down": "F3", "left": "F4"})
        for text in ('{"deadzone": 0.1}', '{"unknown": 1}',
                     '{"enabled": "yes"}', '{"dpad": {"up": "Escape"}}'):
            with self.subTest(text=text), patch.object(Path, "exists", return_value=True), \
                    patch.object(Path, "read_text", return_value=text), self.assertRaises(ValueError):
                load(Path("unused"))

    def test_batched_short_dpad_tap_is_not_lost(self):
        state = [0, 0, 0, set()]
        events = []
        output = MODULE["Output"](lambda *event: events.append(event))
        output.update(set(), 10)
        mapper = self.mapping()
        for value in (1, 0, 1, 2, 0):
            event = SimpleNamespace(type=1, code=544, value=value)
            if MODULE["apply_event"](state, event, None):
                output.update(mapper.keys(*state), 10)
        self.assertEqual(events, [("F1", True), ("F1", False)] * 2)

    def test_focus_checks_parent_class_and_handles_destroyed_window(self):
        x11 = object.__new__(MODULE["X11"])
        x11.x, x11.display = Mock(), 123
        x11.pattern = MODULE["re"].compile(CONFIG["window_class"])
        c = MODULE["C"]
        classname = c.create_string_buffer(b"net-runelite-client-RuneLite")

        def focus(display, window, revert):
            window._obj.value = 100
            return 1

        def classhint(display, window, hint):
            if window.value == 200:
                hint._obj.res_class = c.cast(classname, c.c_void_p).value
                return 1
            return 0

        def tree(display, window, root, parent, children, count):
            parent._obj.value = 200
            return 1

        x11.x.XGetInputFocus.side_effect = focus
        x11.x.XGetClassHint.side_effect = classhint
        x11.x.XQueryTree.side_effect = tree
        self.assertEqual(x11.focus(), 100)
        x11.x.XFree.assert_called_once()
        x11.x.XSync.side_effect = lambda *args: setattr(x11, "error", True)
        self.assertIsNone(x11.focus())

    def test_dropped_events_release_camera_and_require_neutral(self):
        pad = FakeDevice("/dev/input/event29")
        events = self.simulate([pad], [{},
            {"events": {pad.path: [event(3, 0, -100)]}},
            {"events": {pad.path: [event(0, 3, 0), event(1, 311, 1)]}}, {},
            {"events": {pad.path: [event(3, 0, 0), event(1, 311, 0)]}},
            {"events": {pad.path: [event(1, 311, 1)]}}])
        self.assertEqual(events, [("Left", True), ("Left", False),
                                 ("Down", True), ("Down", False)])


if __name__ == "__main__":
    unittest.main()
