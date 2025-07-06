# CCTV Monitoring System

A web-based CCTV monitoring system built with FastAPI and OpenCV, allowing users to view and record from connected cameras.

## Features

- Real-time video streaming through web interface
- Video recording
- Motion detection alerts
- User-friendly web dashboard
- Camera management(Add/Remove)

## Technology Stack

- **FastAPI**: High-performance web framework for building APIs
- **Uvicorn**: ASGI server for FastAPI
- **Jinja2**: Template engine for web interface
- **OpenCV**: Computer vision processing for camera feeds
- **NumPy**: Numerical processing for image analysis
- **Requests**: HTTP library for external API integration

## Installation

1. Clone this repository:
```
git clone https://github.com/yourusername/cctv-monitoring-system.git
cd cctv
```

2. Install dependencies:
```
pip install -r requirements.txt
```

3. Configure your camera settings in the configuration file (see configuration section).

## Usage

1. Start the server:
```
uvicorn main:app --reload
```

2. Open your browser and navigate to:
```
http://localhost:8000
```

3. Use the web interface to view camera feeds and manage settings.

## Development

To contribute to this project:

1. Create a virtual environment
2. Install dev dependencies
3. Follow coding standards in CONTRIBUTING.md


