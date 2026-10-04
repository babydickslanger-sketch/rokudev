# Windows Backend Server Setup Guide (Python & `uv`)

This guide walks you through setting up and running the lightweight Roku middleware backend server silently in the background on your Windows laptop using Python 3.12 and `uv`.

---

## 💡 System Impact

Because this server only extracts media links and cleans playlist manifests (no video rendering or heavy encoding occurs on your laptop), system resource usage is minimal:

* **CPU Usage:** < 1% (spikes briefly for ~100ms when selecting a video on Roku).
* **RAM Footprint:** ~30 MB to 50 MB total.
* **Battery Impact:** Imperceptible during normal laptop usage.

---

## Prerequisites & Environment Setup

### 1. Selected Python Version
We will use **Python 3.12** (or **3.11**), as both provide optimal performance and compatibility with web scraping and async web servers.

### 2. Initialize Project & Virtual Environment with `uv`

Open Command Prompt or PowerShell in your desired directory:

```cmd
:: Create project folder and enter it
mkdir roku-backend
cd roku-backend

:: Create a virtual environment pinned to Python 3.12
uv venv --python 3.12

:: Activate the virtual environment
.venv\Scripts\activate