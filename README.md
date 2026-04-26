# Internet Speed Test GUI

A beautiful, Figma-accurate GUI for testing internet speed using Cloudflare's speed test CLI.

## Prerequisites

- Docker
- X11 server (for GUI display)

## Setup

This container now downloads the Linux `cloudflare-speed-cli` binary automatically during build.

If you want to use a different binary version, update the download URL in `Dockerfile`.

## Building the Docker Image

```bash
docker build -t speed-test-gui .
```

## Running the Application

The application automatically detects if a display is available:

### GUI Mode (with display)
To run the GUI application in Docker with X11 forwarding:

```bash
docker run -it --rm \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  --network host \
  speed-test-gui
```

**Note:** Ensure your X11 server allows connections from the container. You may need to run `xhost +` on your host before running the container.

### Headless Mode (without display)
If no display is available, the container automatically runs in headless mode and prints results to the console:

```bash
docker run --rm speed-test-gui
```

This is useful for servers, CI/CD pipelines, or automated testing.

## Files

- `speed_test_gui.py`: The main Python script with Tkinter GUI
- `Dockerfile`: Docker configuration
- `cloudflare-speed-cli`: The speed test binary (you need to provide this)

## Features

- Real-time speed testing with Cloudflare's infrastructure
- Beautiful, modern GUI design (when display available)
- Automatic headless mode for console output (when no display)
- Detailed results including ping, jitter, packet loss
- Network analysis and recommendations
- Connection quality assessment