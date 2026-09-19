#!/usr/bin/env python3
"""Register the shared Steam library folder in the Steam client.

The current Steam client keeps its library folder list in
~/.steam/debian-installation/config/libraryfolders.vdf. This script makes
sure /games/SteamLibrary is registered so users do not have to add it by
hand in Steam settings.

Safety rules:
  * Idempotent: an already registered folder leaves the file untouched.
  * A file with an unrecognized structure is left untouched.
  * Intended to run at boot only, while no Steam process is running.
"""

import os
import pwd
import re
import sys
import tempfile

GAMER_HOME = "/home/gamer"
STEAM_LIB = "/games/SteamLibrary"
VDF_PATH = os.path.join(
    GAMER_HOME, ".steam", "debian-installation", "config", "libraryfolders.vdf"
)


def make_entry(index, path):
    return (
        '\t"%d"\n'
        '\t{\n'
        '\t\t"path"\t\t"%s"\n'
        '\t\t"label"\t\t""\n'
        '\t\t"contentid"\t\t"0"\n'
        '\t\t"totalsize"\t\t"0"\n'
        '\t\t"update_clean_bytes_tally"\t\t"0"\n'
        '\t\t"time_last_update_verified"\t\t"0"\n'
        '\t\t"apps"\n'
        '\t\t{\n'
        '\t\t}\n'
        '\t}\n'
    ) % (index, path)


def registered_paths(text):
    return re.findall(r'"path"\s+"([^"]*)"', text)


def write_vdf(text):
    directory = os.path.dirname(VDF_PATH)
    os.makedirs(directory, exist_ok=True)
    user = pwd.getpwnam("gamer")
    # The entrypoint runs as root; make sure the config directory (which we
    # may just have created) is owned by gamer, or the client cannot write
    # its own files there.
    os.chown(directory, user.pw_uid, user.pw_gid)
    fd, tmp = tempfile.mkstemp(prefix=".libraryfolders.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chown(tmp, user.pw_uid, user.pw_gid)
        os.chmod(tmp, 0o644)
        os.replace(tmp, VDF_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main():
    if not os.path.isdir(STEAM_LIB):
        print("%s not found; skipping Steam library registration." % STEAM_LIB)
        return 0

    if not os.path.isfile(VDF_PATH):
        print("Creating Steam library registration for %s ..." % STEAM_LIB)
        # A single-library list: the shared /games mount is the only Steam
        # library. Steam does not require its own install directory to be a
        # library (it must simply have at least one), so no client-dir entry
        # is added.
        text = '"libraryfolders"\n{\n'
        text += make_entry(0, STEAM_LIB)
        text += "}\n"
        write_vdf(text)
        print("Steam library registered.")
        return 0

    with open(VDF_PATH, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    if STEAM_LIB in registered_paths(text):
        print("Steam library already registered; nothing to do.")
        return 0

    # Only touch files with the expected single-root structure: the root
    # object closes with a single column-0 '}' line at the end of the file.
    closing_lines = [line for line in text.splitlines() if line == "}"]
    if len(closing_lines) != 1 or not text.rstrip().endswith("}"):
        print(
            "Refusing to modify %s: unrecognized structure." % VDF_PATH,
            file=sys.stderr,
        )
        return 1

    indices = [int(m) for m in re.findall(r'\n\t"(\d+)"\n\t\{', text)]
    entry = make_entry(max(indices) + 1 if indices else 0, STEAM_LIB)
    root_close = text.rstrip().rfind("}")
    write_vdf(text[:root_close] + entry + text[root_close:])
    print("Steam library registered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
