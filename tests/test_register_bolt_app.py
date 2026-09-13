import copy
import json
from pathlib import Path
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]
merge_app = runpy.run_path(str(ROOT / "scripts/register-bolt-app"))["merge_app"]
deduplicate_desktops = runpy.run_path(str(ROOT / "scripts/register-bolt-app"))["deduplicate_desktops"]


class RegisterBoltAppTests(unittest.TestCase):
    def setUp(self):
        self.app = json.loads((ROOT / "sunshine-config/osrs-app.json").read_text())

    def test_existing_apps_and_environment_survive_registration(self):
        config = {"apps": [{"name": "Steam", "cmd": "steam"}], "env": {"FOO": "bar"}}
        original = copy.deepcopy(config)
        self.assertTrue(merge_app(config, self.app))
        self.assertEqual(config["apps"][:-1], original["apps"])
        self.assertEqual(config["env"], original["env"])
        self.assertEqual(config["apps"][-1], self.app)
        self.assertFalse(merge_app(config, self.app))
        self.assertEqual(len(config["apps"]), 2)

    def test_repairs_launch_fields_without_losing_custom_settings(self):
        config = {"apps": [{
            "name": "Old School RuneScape",
            "cmd": "steam",
            "detached": [],
            "image-path": "custom.png",
            "prep-cmd": [{"do": "custom-prep"}],
        }]}
        self.assertTrue(merge_app(config, self.app))
        actual = config["apps"][0]
        self.assertEqual(actual["cmd"], "")
        self.assertEqual(actual["detached"], self.app["detached"])
        self.assertEqual(actual["image-path"], "custom.png")
        self.assertEqual(actual["prep-cmd"], [{"do": "custom-prep"}])
        self.assertFalse(merge_app(config, self.app))

    def test_rejects_invalid_app_list_without_changing_it(self):
        for apps in ({}, ["invalid"]):
            config = {"apps": apps}
            original = copy.deepcopy(config)
            with self.assertRaises(ValueError):
                merge_app(config, self.app)
            self.assertEqual(config, original)

    def test_keeps_first_desktop_and_preserves_other_launchers(self):
        retained = [
            {"name": "Low Res Desktop", "image-path": "desktop.png"},
            self.app,
            {"name": "Steam Desktop", "cmd": "steam"},
            {"name": "Desktop", "cmd": "custom-launcher"},
            {"name": "Desktop", "detached": ["custom-launcher"]},
        ]
        config = {"apps": [
            {"name": "Desktop", "image-path": "desktop.png"},
            {"name": "Desktop", "cmd": "", "detached": []},
        ] + copy.deepcopy(retained), "env": {"FOO": "bar"}}
        first_desktop = copy.deepcopy(config["apps"][0])
        self.assertTrue(deduplicate_desktops(config))
        self.assertEqual(config["apps"], [first_desktop] + retained)
        self.assertEqual(config["env"], {"FOO": "bar"})
        self.assertFalse(deduplicate_desktops(config))

    def test_single_desktop_is_unchanged(self):
        config = {"apps": [{"name": "Desktop", "image-path": "custom.png"}]}
        original = copy.deepcopy(config)
        self.assertFalse(deduplicate_desktops(config))
        self.assertEqual(config, original)


if __name__ == "__main__":
    unittest.main()
