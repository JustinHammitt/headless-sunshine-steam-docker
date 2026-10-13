from pathlib import Path
import runpy
import signal
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts/stop-bolt-session"))
SELECT = MODULE["session_processes"]
STOP = MODULE["stop_session"]
GLOBALS = STOP.__globals__


def process(exe, args=(), parent=1, cwd="/home/gamer", started="100"):
    return {"exe": exe, "args": list(args), "parent": parent,
            "cwd": cwd, "started": started}


class StopBoltSessionTests(unittest.TestCase):
    def setUp(self):
        # The runtime is Linux; keep mocked signal tests runnable on Windows.
        sigkill = patch.object(signal, "SIGKILL", 9, create=True)
        sigkill.start()
        self.addCleanup(sigkill.stop)

    def test_detached_clients_and_descendants_without_unrelated_apps(self):
        processes = {
            10: process("/opt/bolt-launcher/bolt"),
            11: process("/opt/bolt-launcher/bolt", ["--type=renderer"], parent=10),
            20: process("/usr/bin/java", ["-jar", "/data/runelite.jar"]),
            21: process("/usr/bin/java", ["net.runelite.client.RuneLite"]),
            22: process("/usr/bin/java", ["-jar", "/custom/client.jar"],
                        cwd="/home/gamer/.local/share/bolt-launcher"),
            23: process("/usr/bin/wine", ["/data/osrswindows.exe"],
                        cwd="/home/gamer/.local/share/bolt-launcher"),
            24: process("/usr/bin/helper", parent=23),
            25: process("/usr/bin/helper", parent=24),
            30: process("/usr/bin/java", ["-jar", "/data/server.jar"]),
            31: process("/usr/bin/steam"),
            32: process("/usr/bin/python3", ["runelite.jar"]),
            33: process("/usr/bin/wine", ["other-game.exe"]),
        }
        self.assertEqual(set(SELECT(processes)), {10, 11, 20, 21, 22, 23, 24, 25})

    def test_proc_scan_parses_identity_and_filters_other_users_and_zombies(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc = Path(temporary)
            directory = proc / "20"
            directory.mkdir()
            uid = directory.stat().st_uid
            fields = ["S", "1"] + ["0"] * 17 + ["123"]
            (directory / "stat").write_text("20 (java worker) " + " ".join(fields))
            (directory / "cmdline").write_bytes(b"java\0-jar\0runelite.jar\0")
            links = {"exe": "/usr/bin/java", "cwd": "/home/gamer"}
            with patch.object(MODULE["os"], "readlink",
                              side_effect=lambda path: links[path.name]):
                result = MODULE["read_processes"](proc, uid=uid)
                self.assertEqual(result[20], process("/usr/bin/java",
                                 ["java", "-jar", "runelite.jar"], started="123"))
                self.assertEqual(MODULE["read_processes"](proc, uid=uid + 1), {})
                fields[0] = "Z"
                (directory / "stat").write_text("20 (java worker) " + " ".join(fields))
                self.assertEqual(MODULE["read_processes"](proc, uid=uid), {})

    def test_graceful_exit_does_not_force_kill(self):
        processes = {10: process("/opt/bolt-launcher/bolt")}
        with patch.dict(GLOBALS, read_processes=lambda: next(snapshots)), \
                patch.object(MODULE["os"], "kill") as kill:
            snapshots = iter([processes, {}])
            STOP()
        kill.assert_called_once_with(10, signal.SIGTERM)

    def test_stubborn_client_is_force_killed_with_bounded_wait(self):
        processes = {20: process("/usr/bin/java", ["-jar", "runelite.jar"])}
        with patch.dict(GLOBALS, read_processes=lambda: processes), \
                patch.object(MODULE["os"], "kill") as kill:
            STOP(grace=0)
        self.assertEqual([call.args for call in kill.call_args_list],
                         [(20, signal.SIGTERM), (20, signal.SIGKILL)])

    def test_reused_pid_of_unrelated_process_is_not_killed(self):
        original = {10: process("/opt/bolt-launcher/bolt")}
        reused = {10: process("/usr/bin/steam", started="200")}
        snapshots = iter([original, reused])
        with patch.dict(GLOBALS, read_processes=lambda: next(snapshots)), \
                patch.object(MODULE["os"], "kill") as kill:
            STOP(grace=0)
        kill.assert_called_once_with(10, signal.SIGTERM)

    def test_no_active_clients_is_a_noop(self):
        with patch.dict(GLOBALS, read_processes=lambda: {}), \
                patch.object(MODULE["os"], "kill") as kill:
            STOP()
        kill.assert_not_called()

    def test_client_spawned_during_shutdown_is_also_terminated(self):
        original = {10: process("/opt/bolt-launcher/bolt")}
        late = {20: process("/usr/bin/java", ["-jar", "runelite.jar"])}
        snapshots = iter([original, late])
        with patch.dict(GLOBALS, read_processes=lambda: next(snapshots)), \
                patch.object(MODULE["os"], "kill") as kill:
            STOP(grace=0)
        self.assertEqual([call.args for call in kill.call_args_list],
                         [(10, signal.SIGTERM), (20, signal.SIGKILL)])


if __name__ == "__main__":
    unittest.main()
