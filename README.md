# GestureLight

GestureLight turns a webcam into a gesture controller for a desk lamp. It runs
as a desktop application on Linux, recognizes hand gestures with OpenCV and
MediaPipe, and sends commands over your local Wi-Fi network to an ESP32.

The ESP32 uses PhotoMOS relays to briefly emulate presses of the lamp's
existing **low-voltage** buttons. The lamp keeps its original power supply and
physical controls.

## What you need

- An x86_64 Linux computer with a webcam
- An ESP32 connected to the same trusted 2.4 GHz Wi-Fi network
- The GestureLight relay circuit installed on a compatible lamp controller

## Install and configure

### NixOS (recommended)

Add this flake to your system flake. This example uses a local checkout; after
publishing the repository, replace the local path with its GitHub flake URL.

```nix
inputs.gesturelight.url = "path:/absolute/path/to/gesturelight";
```

Import the module and set the ESP32's address:

```nix
{
  outputs = { self, nixpkgs, gesturelight, ... }: {
    nixosConfigurations.my-host = nixpkgs.lib.nixosSystem {
      # Your normal system and platform settings go here.
      modules = [
        gesturelight.nixosModules.default
        {
          gesturelight = {
            enable = true;
            url = "192.168.1.50";
          };
        }
      ];
    };
  };
}
```

`gesturelight.url` can be an IP address, hostname, or hostname with a port.
You can include `http://`, but it is added automatically when omitted. Rebuild
your NixOS configuration, then launch **GestureLight** from your application
launcher. The configured ESP32 address is passed to the app automatically.

### Other NixOS/Linux setups

From a checkout of this repository, install the desktop application into your
Nix profile:

```bash
nix profile install path:.#gesturelight
```

You can then launch **GestureLight** from your desktop application menu. For
lamp control, start it once from a terminal with the ESP32 address:

```bash
gesturelight-hand-tracker --esp32-url http://192.168.1.50
```

Without `--esp32-url`, GestureLight works as a camera and hand-tracking preview
only; it will not send commands to a lamp.

## ESP32 setup

The firmware is in
[`src/gesturelight/gesturelight.ino`](src/gesturelight/gesturelight.ino).

1. Create a private Wi-Fi configuration file:

   ```bash
   cp src/gesturelight/wifi_secrets.example.h src/gesturelight/wifi_secrets.h
   ```

2. Edit `wifi_secrets.h` and enter your `WIFI_SSID` and `WIFI_PASSWORD`. Do not
   commit this file.
3. Open the `src/gesturelight` sketch in Arduino IDE, select your ESP32 board
   and serial port, then upload it.
4. Open the serial monitor at **115200 baud**. After joining Wi-Fi, the ESP32
   prints its local URL. Use that address for `gesturelight.url` or
   `--esp32-url`.

Giving the ESP32 a DHCP reservation is recommended so its address does not
change. The ESP32's control endpoint is intentionally limited to the trusted
local network; do not expose it to the public internet.

## Gestures

| Gesture | Lamp action |
| --- | --- |
| Close your fist, then open all four fingers | Toggle power |
| Pinch thumb and index finger, then move your hand up | Increase brightness |
| Pinch thumb and index finger, then move your hand down | Decrease brightness |
| Release the pinch | Stop brightness control |
| `q` or `Escape` | Close GestureLight |

The preview window shows the active gesture instructions while ESP32 control
is enabled.

## Circuit and wiring

> Add the completed circuit diagram and schematic to `docs/`, then replace the
> image paths below with their final filenames.

![Completed GestureLight wiring diagram](docs/gesturelight-wiring-diagram.png)

![GestureLight circuit schematic](docs/gesturelight-schematic.png)

The diagrams above are the authoritative wiring reference for this build. Each
PhotoMOS output is connected **in parallel** with one verified low-voltage
lamp-button contact pair, allowing the ESP32 to emulate a brief button press.

### Important safety notes

- Disconnect the lamp from power before opening it, testing continuity,
  soldering, or changing wiring.
- Work only with verified low-voltage button-controller contacts.
- Never connect an ESP32 GPIO to the lamp's LED, USB, mains, or power path.
- Keep the lamp's original power supply intact; the ESP32 uses separate USB
  power.
- Verify each target button contact pair with a multimeter. Do not assume the
  physical layout of a tactile switch identifies its switched terminals.

## Troubleshooting

| Problem | First thing to check |
| --- | --- |
| GestureLight cannot reach the ESP32 | Confirm its USB power, the serial-monitor URL, and that both devices are on the same trusted LAN. |
| A gesture is recognized but the lamp does nothing | With the lamp unplugged, re-check that the PhotoMOS output is across the verified button-contact pair. |
| Camera does not open | Close other camera apps and try a different camera with `--camera-index 1`. |
| Hand tracking is slow | Use better lighting or launch with `--width 640 --height 480 --model-complexity 0`. |

GestureLight is designed for compatible low-voltage lamp controllers only. Do
not use it on mains-voltage circuitry.
