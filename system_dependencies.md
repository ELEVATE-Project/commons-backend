# System Dependencies

This project uses media processing libraries that rely on **system-level binaries**
(not installable via `requirements.txt`). These dependencies are required for
PDF previews, video/audio processing, and optional high-fidelity document rendering.
They must be installed on **all machines running Django or Celery workers**.

## Installation (Ubuntu / Debian)

```bash
# PDF preview (required)
sudo apt update
sudo apt install -y poppler-utils

# Video & audio processing (required)
sudo apt install -y ffmpeg

# Verification
pdfinfo -h
ffmpeg -version
