from pathlib import Path
import runpy
import signal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts/osrs-controller"))
CONFIG = MODULE["DEFAULTS"]


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

    def test_disconnect_reconnect_and_signal_release_held_keys(self):
        run = MODULE["run"]
        first, second = Mock(), Mock()
        first.name, second.name = "Xbox Controller", "Sunshine Xbox Controller"
        evdev = Mock()
        evdev.list_devices.return_value = ["/dev/input/event10"]
        evdev.InputDevice.side_effect = [first, second]
        x11 = Mock()
        x11.focus.return_value = 10
        handlers = {}

        def register(signum, callback):
            handlers[signum] = callback

        states = iter([(0, 0, 0, set()), (-1, 0, 0, set()), OSError("disconnected"),
                       (-1, 0, 0, set()), (0, 0, 0, set()), (1, 0, 0, set())])

        def state(device):
            value = next(states)
            if isinstance(value, Exception):
                raise value
            if value[0] == 1:
                handlers[signal.SIGTERM](signal.SIGTERM, None)
            return value

        with patch.dict(run.__globals__, is_controller=lambda *args: True, snapshot=state), \
                patch.object(MODULE["signal"], "signal", side_effect=register), \
                patch.object(MODULE["select"], "select", return_value=([], [], [])):
            run(CONFIG, evdev, x11)
        self.assertEqual([call.args for call in x11.emit.call_args_list],
                         [("Left", True), ("Left", False), ("Right", True), ("Right", False)])
        first.close.assert_called_once()
        second.close.assert_called_once()

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
        run = MODULE["run"]
        device = Mock()
        device.name = "Xbox Controller"
        device.absinfo.return_value = SimpleNamespace(min=-100, max=100, value=-100)
        device.read.return_value = [SimpleNamespace(type=0, code=3, value=0),
                                   SimpleNamespace(type=1, code=311, value=1)]
        evdev, x11 = Mock(), Mock()
        evdev.list_devices.return_value = ["/dev/input/event10"]
        evdev.InputDevice.return_value = device
        x11.focus.return_value = 10
        handlers = {}
        states = iter([(0, 0, 0, set()), (-1, 0, 0, set()),
                       (-1, 0, 0, set()), (-1, 0, 0, set()), (-1, 0, 0, set())])
        reads = iter([([], [], []), ([], [], []), ([device], [], []), ([], [], [])])

        def snapshot(device):
            value = next(states)
            if not list_count[0]:
                handlers[signal.SIGTERM](signal.SIGTERM, None)
            list_count[0] -= 1
            return value

        list_count = [4]
        with patch.dict(run.__globals__, is_controller=lambda *args: True, snapshot=snapshot), \
                patch.object(MODULE["signal"], "signal", side_effect=lambda s, h: handlers.update({s: h})), \
                patch.object(MODULE["select"], "select", side_effect=lambda *args: next(reads)):
            run(CONFIG, evdev, x11)
        self.assertEqual([call.args for call in x11.emit.call_args_list],
                         [("Left", True), ("Left", False)])


if __name__ == "__main__":
    unittest.main()
