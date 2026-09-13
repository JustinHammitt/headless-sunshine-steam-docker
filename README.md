# headless-sunshine-steam-docker

A Dockerized, headless Linux Sunshine and Steam host built around:

- [Sunshine](https://github.com/LizardByte/Sunshine) — hosts and streams the desktop and games
- [Steam](https://store.steampowered.com/about/) — installs, manages and launches games
- [Moonlight](https://moonlight-stream.org/) — connects clients to the Sunshine host
- NVIDIA NVENC + NvFBC — provides hardware encoding and display capture
- Headless Xorg — creates the virtual display without a physical monitor
- Openbox — provides a lightweight window manager
- Picom — composites the virtual desktop
- PipeWire — provides headless game audio

The goal is to turn a Linux server with an NVIDIA GPU into a console-like Sunshine and Steam appliance with a single command (with prerequisites installed):

```bash
docker compose up -d --build
```

Steam is installed and updated automatically. Sunshine starts with a fresh default configuration, and all persistent data is stored under `./data`.

---

## Features

- Fully headless virtual X11 display
- NVIDIA NvFBC capture
- NVIDIA NVENC hardware encoding
- Steam Big Picture / Gamepad UI
- Automatic Steam bootstrap and client updates
- Persistent Steam login, settings and Proton state
- Persistent Sunshine configuration and pairing state
- Automatic Moonlight client-resolution switching
- Mouse, keyboard and controller passthrough through Sunshine
- Selectable NVIDIA GPU for multi-GPU hosts

---

# Prerequisites

You need a Linux host with:

### 1. NVIDIA GPU

A recent NVIDIA GPU with NVENC support is recommended.

This project is designed around NVIDIA's Linux stack and uses **NvFBC** for capture and **NVENC** for encoding.

### 2. NVIDIA driver

Install a recent proprietary NVIDIA driver on the **host**.

The container uses the host kernel driver; the driver itself is not installed inside Docker.

Verify:

```bash
nvidia-smi
```

### 3. Docker Engine + Docker Compose

Install Docker Engine with the Compose plugin:

https://docs.docker.com/engine/install/

Verify:

```bash
docker --version
docker compose version
```

### 4. NVIDIA Container Toolkit

Docker must be able to expose the NVIDIA GPU to containers.

Install NVIDIA Container Toolkit:

https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

### 5. `/dev/uinput`

Sunshine uses `uinput` for virtual mouse, keyboard and controller devices.

Check:

```bash
ls -l /dev/uinput
```

If it does not exist:

```bash
sudo modprobe uinput
```

This loads the module until the next reboot. To load it automatically on every boot, run once:

```bash
echo uinput | sudo tee /etc/modules-load.d/uinput.conf
```

---

# Installation

## 1. Clone the project

```bash
git clone https://github.com/numsu/headless-sunshine-steam-docker.git
cd headless-sunshine-steam-docker
```

---

## 2. Configure `.env`

Create the environment file:

```bash
cp .env.example .env
```

Set the Sunshine Web UI origin to the LAN address you will use to access Sunshine.

Example:

```dotenv
SUNSHINE_CORS_ORIGIN=https://192.168.1.100:47990
NVIDIA_GPU_ID=0
```

Replace `192.168.1.100` with the IP address of your Docker host.

Set `NVIDIA_GPU_ID` to the GPU index reported by `nvidia-smi`; this is normally `0` on a single-GPU server.

You can find the host IP with, for example:

```bash
hostname -I
```

Use a stable/static LAN address if possible.

---

Persistent storage requires no configuration. The default Compose file stores the fresh Sunshine and Steam state in `./data` and the game library in `./data/games/SteamLibrary`.

### Optional: Use an existing Steam library

To reuse an existing library, change only the host path of the `/games` mount in `docker-compose.yml`:

```yaml
volumes:
  - /path/to/SteamLibrary:/games
```

---

# Start the server

Build and start everything:

```bash
docker compose up -d --build
```

Follow the logs:

```bash
docker compose logs -f sunshine-steam
```
On the first start, Steam may take some time to install/update.

---

# Sunshine setup

## 1. Open the Web UI

From another computer on your LAN, open:

```text
https://HOST_IP:47990
```
Sunshine uses a locally generated TLS certificate, so your browser may show a certificate warning. This is expected for a local installation.

Create/login with your Sunshine Web UI credentials.

---

## 2. Configure NVIDIA capture and encoding

In the Sunshine Web UI, open the audio/video configuration.

Recommended values:

```text
Capture: nvfbc
Encoder: nvenc
```
Save the configuration.

---

# Connect Moonlight

## 1. Add the server

Open Moonlight.

Sunshine may be discovered automatically on the LAN.

If it is not, manually add the Docker host IP:

```text
192.168.1.100
```

Do not add port `47990`; Moonlight uses the Sunshine streaming ports automatically.

---

## 2. Pair the client

Select the server in Moonlight.

Moonlight will display a PIN.

Open:

```text
https://HOST_IP:47990
```

In the Sunshine Web UI:

1. Open **PIN**
2. Select the pending pairing request if necessary
3. Enter the PIN shown by Moonlight
4. Give the device a name
5. Confirm

Moonlight should now show the applications published by Sunshine.

Select **Steam Big Picture** or **Steam Desktop**.

---

## 3. Set the Moonlight streaming resolution

Configure the desired resolution, FPS and bitrate in the Moonlight client.

The container automatically changes the virtual Xorg desktop to the client-requested resolution when the stream starts.

---

## Add the game library to Steam

The game library is mounted in the container at:

```text
/games
```

Add `/games` as a Steam library.

Normally this can be done from:

```text
Steam -> Settings -> Storage
```

If Steam's Linux Storage UI does not respond to the **Add Drive** button, use the Steam console.

Open the Steam console inside the running graphical session:

```bash
docker compose exec -u gamer sunshine-steam \
  bash -lc 'DISPLAY=:0 steam steam://open/console'
```

Then run in the Steam Console:

```text
library_folder_add /games
```

After that, Steam should see the mounted library normally.

---

# Optional: Old School RuneScape with Bolt

Native Bolt support is experimental and disabled by default. Enable it in `.env`:

```dotenv
ENABLE_BOLT=true
```

Then rebuild and recreate the container:

```bash
docker compose build sunshine-steam
docker compose up -d sunshine-steam
```

The `bolt-builder` stage compiles [Bolt 0.24.0 from Codeberg](https://codeberg.org/Adamcake/Bolt/src/tag/0.24.0)
at commit `d8589d80f9849e51f121646e31daa5be7038da28`, including its pinned
submodules. It uses the committed `app/dist` frontend and builds the CEF C++
wrapper from [Adamcake's native Linux CEF distribution](https://adamcake.com/cef).
The archive is `cef-139.0.7258.139-linux-x86_64-minimal-ungoogled.tar.xz`,
verified with SHA-256
`aeb98ff1f621c8f7c5f0be6c34acefaf4fe4be763004a9d2a9e933d1cd914650`.

Both stages use Ubuntu 24.04. CMake installs Bolt and that same CEF bundle under
`/opt/bolt-launcher`, with its launcher at `/usr/local/bin/bolt`. Only the installed
output is copied into the gaming image; compiler, CMake, Git, source trees, and
development headers stay in the builder. Runtime libraries and OpenJDK 17 for
RuneLite are installed only when enabled. This build supports Linux amd64.
Bolt's optional RuneScape plugin library is omitted; RuneLite plugins are independent.

The build defaults to two compilation jobs to limit memory use. To change it:

```bash
docker compose build --build-arg BOLT_BUILD_JOBS=4 sunshine-steam
```

Bolt and CEF source pins are recorded in `/opt/bolt-launcher/build-info.txt`.
Changing the CEF version also requires updating its checksum and rebuilding Bolt;
do not replace `libcef.so` independently. These pins do not freeze Ubuntu package
repositories or RuneLite's downloaded client updates.

## Validate the native launcher first

Connect to Sunshine's **Desktop** application in Moonlight, then run Bolt as the
existing gamer user inside the running container:

```bash
docker compose exec -u gamer \
  -e DISPLAY=:0 \
  -e XDG_RUNTIME_DIR=/run/user/1000 \
  -e PULSE_SERVER=unix:/run/user/1000/pulse/native \
  sunshine-steam /usr/local/bin/bolt
```

Check that the launcher renders and accepts mouse/keyboard input, sign in with
your Jagex Account, select a character, and launch RuneLite. Close both normally,
recreate the container, and verify settings and login state persist. Bolt's XDG
configuration/data and RuneLite's files remain under the mounted `/home/gamer`.
At startup, the container repairs ownership of the XDG parent directories and
Bolt's own config/data/runtime directories. This also handles directories left
by earlier root-run launcher attempts; it does not recursively change Steam data.
Account login is performed interactively; no credentials belong in the image or
build arguments.

Image builds check shared-library resolution, including GLIBC symbol errors.
A successful build does not validate X11 rendering, CEF subprocess startup,
Jagex login, or RuneLite launch. These require the running server test above.
Adamcake's CEF 139 uses a namespace sandbox; if startup reports sandbox errors,
capture the terminal output before proceeding. This integration adds no sandbox
bypass flags, capabilities, host configuration, or changes to the existing
Compose security settings.

## Launch from Moonlight

When Bolt is installed, container startup registers **Old School RuneScape** in
Sunshine, including installations with an existing persistent app list. Refresh
Moonlight's applications and select **Old School RuneScape**. The **Desktop** app
continues to open only the desktop.

Registration preserves other applications and custom settings. For an existing
**Old School RuneScape** entry, it clears **Command** and updates **Detached
Command** to launch Bolt directly and record startup errors:

```text
setsid env DISPLAY=:0 /usr/local/bin/bolt >> /home/gamer/.local/state/bolt-launcher.log 2>&1
```

Global preparation commands are enabled by default for resolution switching. Bolt inherits
the existing gamer session's runtime and audio environment. A detached application
continues running after the stream ends; close RuneLite and Bolt from the desktop
when finished.

The app object is provided in `sunshine-config/osrs-app.json`. Registration does
not prove Bolt can launch: complete the native validation above. If Moonlight
shows only the desktop after selecting **Old School RuneScape**, read the log:

```bash
docker compose exec -u gamer sunshine-steam \
  tail -n 100 /home/gamer/.local/state/bolt-launcher.log
```

If the log is missing, confirm the image was rebuilt with `ENABLE_BOLT=true`
and the container recreated, then inspect the app's Detached Command in Sunshine.
To see startup errors directly, use the foreground native-launch command above.
Changing `.env` followed by `docker compose restart` does not rebuild the image.

If you later rebuild with `ENABLE_BOLT=false`, remove the app in the Sunshine Web
UI; the persistent home remains intact.

---

# Networking

The supplied Compose configuration uses host networking so Sunshine discovery and streaming traffic work naturally on the LAN.

Sunshine's default ports include:

| Purpose | Port |
| --- | --- |
| Sunshine HTTPS | TCP 47984 |
| Sunshine HTTP | TCP 47989 |
| Web UI | TCP 47990 |
| RTSP | TCP 48010 |
| Video | UDP 47998 |
| Control | UDP 47999 |
| Audio | UDP 48000 |

If the host firewall blocks these, allow them on your trusted LAN.

Example with UFW:

```bash
sudo ufw allow 47984/tcp
sudo ufw allow 47989/tcp
sudo ufw allow 47990/tcp
sudo ufw allow 48010/tcp
sudo ufw allow 47998/udp
sudo ufw allow 47999/udp
sudo ufw allow 48000/udp
```

Do not blindly expose these ports through your Internet router.

---

# Logs and diagnostics

Follow all container output:

```bash
docker compose logs -f sunshine-steam
```

Check the selected GPU:

```bash
docker compose exec sunshine-steam nvidia-smi
```

Check the virtual display:

```bash
docker compose exec sunshine-steam \
  bash -lc 'DISPLAY=:0 xrandr'
```

Check Sunshine processes:

```bash
docker compose exec sunshine-steam pgrep -a sunshine
```

Check Steam:

```bash
docker compose exec sunshine-steam \
  pgrep -a -f 'steam|steamwebhelper'
```
---

# Recommended Steam settings

Once the system is working, there are a few Steam settings worth changing.

## Enable Vulkan shader pre-caching

Open:

```text
Steam -> Settings -> Downloads
```

Enable:

```text
Enable Shader Pre-Caching
```

and:

```text
Allow background processing of Vulkan shaders
```

The second option is particularly useful for an always-on game server: Steam can process Vulkan shader caches while the machine is idle instead of waiting until game launch.

This can reduce shader-compilation pauses and stutter.

---

## Compatibility / Proton

For Windows-only games:

```text
Game -> Properties -> Compatibility
```

Start with either:

- the current stable Proton release, or
- Proton Experimental
