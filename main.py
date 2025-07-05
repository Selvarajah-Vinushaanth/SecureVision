from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import cv2
import requests
import numpy as np
import uvicorn
import threading
import time
import os
from datetime import datetime
import json

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Create static files directory if it doesn't exist
os.makedirs("static", exist_ok=True)
os.makedirs("recordings", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

CAMERAS_FILE = "cameras.json"

# Load cameras from file
if os.path.exists(CAMERAS_FILE):
    with open(CAMERAS_FILE, "r") as f:
        CAMERAS = json.load(f)
else:
    CAMERAS = {}

# Dictionary of camera name -> IP camera URL
# CAMERAS = {
#     "phone": "http://192.168.209.218:8080/video",
#     "laptop": "http://192.168.209.224:8080/video",
#     # Add more cameras here
# }

# Global variables for advanced features
camera_status = {}
camera_recordings = {}
motion_alerts = {}
recording_states = {}
camera_settings = {}
system_stats = {
    "start_time": datetime.now(),
    "total_recordings": 0,
    "total_motion_events": 0,
    "data_usage": 0
}

def save_cameras():
    """Save cameras to file"""
    with open(CAMERAS_FILE, "w") as f:
        json.dump(CAMERAS, f, indent=4)

def check_camera_health():
    """Background task to monitor camera health"""
    while True:
        for cam_name, cam_url in CAMERAS.items():
            try:
                response = requests.head(cam_url, timeout=3)
                camera_status[cam_name] = {
                    "status": "online" if response.status_code == 200 else "offline",
                    "last_check": datetime.now().isoformat(),
                    "response_time": response.elapsed.total_seconds() if response.elapsed else 0
                }
            except Exception as e:
                camera_status[cam_name] = {
                    "status": "offline",
                    "last_check": datetime.now().isoformat(),
                    "error": str(e)
                }
        time.sleep(30)  # Check every 30 seconds

def detect_motion(frame1, frame2, threshold=500):
    """Enhanced motion detection"""
    try:
        diff = cv2.absdiff(frame1, frame2)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, thresh = cv2.threshold(blur, 20, 255, cv2.THRESH_BINARY)
        dilated = cv2.dilate(thresh, None, iterations=3)
        contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        motion_area = sum(cv2.contourArea(contour) for contour in contours)
        return motion_area > threshold
    except Exception:
        return False

def generate_frames(camera_url: str, camera_name: str = None):
    previous_frame = None
    recording = False
    video_writer = None
    
    while True:
        try:
            response = requests.get(camera_url, stream=True, timeout=5)
            if response.status_code != 200:
                continue
            bytes_data = bytes()
            for chunk in response.iter_content(chunk_size=8192):
                bytes_data += chunk
                a = bytes_data.find(b'\xff\xd8')
                b = bytes_data.find(b'\xff\xd9')
                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]
                    try:
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is None:
                            continue
                        
                        # Motion detection
                        if camera_name and previous_frame is not None:
                            if detect_motion(previous_frame, frame):
                                motion_alerts[camera_name] = {
                                    "timestamp": datetime.now().isoformat(),
                                    "status": "motion_detected"
                                }
                                system_stats["total_motion_events"] += 1
                        
                        previous_frame = frame.copy()
                        
                        # Recording logic
                        if camera_name and camera_name in camera_recordings and camera_recordings[camera_name]:
                            if not recording:
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                filename = f"recordings/{camera_name}_{timestamp}.mp4"
                                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                                video_writer = cv2.VideoWriter(filename, fourcc, 20.0, (frame.shape[1], frame.shape[0]))
                                recording = True
                                system_stats["total_recordings"] += 1
                            
                            if video_writer and video_writer.isOpened():
                                video_writer.write(frame)
                        else:
                            if recording and video_writer:
                                video_writer.release()
                                recording = False
                                video_writer = None
                        
                        # Add timestamp overlay
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cv2.putText(frame, timestamp, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        # Add recording indicator
                        if recording:
                            cv2.circle(frame, (frame.shape[1] - 30, 30), 10, (0, 0, 255), -1)
                            cv2.putText(frame, "REC", (frame.shape[1] - 60, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                        
                    except Exception as e:
                        print("OpenCV decode error:", e)
                        continue
                    
                    ret, buffer = cv2.imencode('.jpg', frame)
                    if not ret:
                        continue
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            print(f"Camera stream error ({camera_url}):", e)
            time.sleep(5)

# Start background health monitoring
threading.Thread(target=check_camera_health, daemon=True).start()

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "datetime": datetime,
        "cameras": list(CAMERAS.keys())
    })

@app.post("/api/camera/add")
def add_camera(data: dict):
    """Add a new camera to the system"""
    try:
        name = data.get("name", "").strip()
        url = data.get("url", "").strip()
        
        if not name or not url:
            raise HTTPException(status_code=400, detail="Camera name and URL are required")
        
        # Check for duplicate names (case-insensitive)
        existing_names = [cam_name.lower() for cam_name in CAMERAS.keys()]
        if name.lower() in existing_names:
            raise HTTPException(status_code=400, detail=f"Camera name '{name}' already exists. Please choose a different name.")
        
        # Validate URL format
        if not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
        
        # Add camera to the system
        CAMERAS[name] = url
        save_cameras()  # Persist changes
        
        # Initialize camera status
        camera_status[name] = {
            "status": "unknown",
            "last_check": "never",
            "error": "Not checked yet"
        }
        
        return {
            "status": "success",
            "message": f"Camera '{name}' added successfully",
            "camera": {
                "name": name,
                "url": url,
                "status": "unknown"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add camera: {str(e)}")

@app.delete("/api/camera/{camera_name}")
def remove_camera(camera_name: str):
    """Remove a camera from the system"""
    try:
        if camera_name not in CAMERAS:
            raise HTTPException(status_code=404, detail="Camera not found")
        
        # Stop recording if active
        if camera_recordings.get(camera_name, False):
            camera_recordings[camera_name] = False
            recording_states[camera_name] = False
        
        # Remove camera from all dictionaries
        del CAMERAS[camera_name]
        save_cameras()  # Persist changes
        camera_status.pop(camera_name, None)
        camera_recordings.pop(camera_name, None)
        motion_alerts.pop(camera_name, None)
        recording_states.pop(camera_name, None)
        camera_settings.pop(camera_name, None)
        
        return {
            "status": "success",
            "message": f"Camera '{camera_name}' removed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove camera: {str(e)}")

@app.get("/video_feed/{camera_name}")
def video_feed(camera_name: str):
    if camera_name not in CAMERAS:
        raise HTTPException(status_code=404, detail="Camera not found")
    return StreamingResponse(generate_frames(CAMERAS[camera_name], camera_name),
                             media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/camera_status")
def get_camera_status():
    """Get status of all cameras"""
    # Initialize status for cameras that haven't been checked yet
    for cam_name in CAMERAS.keys():
        if cam_name not in camera_status:
            camera_status[cam_name] = {
                "status": "unknown",
                "last_check": "never",
                "error": "Not checked yet"
            }
    return JSONResponse(camera_status)

@app.get("/api/motion_alerts")
def get_motion_alerts():
    """Get and clear motion alerts"""
    alerts = motion_alerts.copy()
    motion_alerts.clear()
    return JSONResponse(alerts)

@app.post("/api/recording/{camera_name}/{action}")
def control_recording(camera_name: str, action: str):
    """Start or stop recording for a specific camera"""
    if camera_name not in CAMERAS:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    try:
        if action == "start":
            camera_recordings[camera_name] = True
            recording_states[camera_name] = True
            print(f"Started recording for camera: {camera_name}")
        elif action == "stop":
            camera_recordings[camera_name] = False
            recording_states[camera_name] = False
            print(f"Stopped recording for camera: {camera_name}")
        else:
            raise HTTPException(status_code=400, detail="Invalid action. Use 'start' or 'stop'")
        
        return {
            "status": "success", 
            "recording": camera_recordings.get(camera_name, False),
            "camera": camera_name,
            "action": action
        }
    except Exception as e:
        print(f"Error controlling recording for {camera_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to {action} recording: {str(e)}")

@app.get("/recordings/{filename}")
def serve_recording(filename: str):
    """Serve recording files for playback"""
    try:
        filepath = os.path.join("recordings", filename)
        if os.path.exists(filepath) and filename.endswith(".mp4"):
            from fastapi.responses import FileResponse
            return FileResponse(
                filepath,
                media_type="video/mp4",
                headers={
                    "Content-Disposition": f"inline; filename={filename}",
                    "Accept-Ranges": "bytes"
                }
            )
        else:
            raise HTTPException(status_code=404, detail="Recording not found or unsupported format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to serve recording: {str(e)}")

@app.get("/api/recordings/thumbnail/{filename}")
def get_recording_thumbnail(filename: str):
    """Generate and serve thumbnail for recording"""
    try:
        filepath = os.path.join("recordings", filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Recording not found")
        
        # Generate thumbnail from video
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            raise HTTPException(status_code=500, detail="Failed to open video file")
        
        ret, frame = cap.read()
        cap.release()
        
        if ret:
            # Resize frame for thumbnail
            height, width = frame.shape[:2]
            aspect_ratio = width / height
            thumb_height = 60
            thumb_width = int(thumb_height * aspect_ratio)
            
            thumbnail = cv2.resize(frame, (thumb_width, thumb_height))
            
            # Convert to JPEG
            ret, buffer = cv2.imencode('.jpg', thumbnail, [cv2.IMWRITE_JPEG_QUALITY, 80])
            
            if ret:
                from fastapi.responses import Response
                return Response(
                    content=buffer.tobytes(),
                    media_type="image/jpeg"
                )
        
        raise HTTPException(status_code=500, detail="Could not generate thumbnail")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate thumbnail: {str(e)}")

@app.get("/api/recordings")
def get_recordings():
    """Get list of all recordings with detailed info"""
    recordings = []
    try:
        if os.path.exists("recordings"):
            for file in os.listdir("recordings"):
                if file.endswith(".mp4"):
                    filepath = os.path.join("recordings", file)
                    stat = os.stat(filepath)
                    
                    # Get video duration using OpenCV
                    try:
                        cap = cv2.VideoCapture(filepath)
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                        duration_seconds = frame_count / fps if fps > 0 else 0
                        cap.release()
                        
                        hours = int(duration_seconds // 3600)
                        minutes = int((duration_seconds % 3600) // 60)
                        seconds = int(duration_seconds % 60)
                        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    except:
                        duration_str = "00:00:00"
                    
                    recordings.append({
                        "filename": file,
                        "size": stat.st_size,
                        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "camera": file.split('_')[0],
                        "duration": duration_str,
                        "url": f"/recordings/{file}",
                        "thumbnail": f"/api/recordings/thumbnail/{file}"
                    })
            
            # Sort by creation time, newest first
            recordings.sort(key=lambda x: x['created'], reverse=True)
    except Exception as e:
        print(f"Error reading recordings: {e}")
    
    return JSONResponse(recordings)

@app.get("/api/system_stats")
def get_system_stats():
    """Get comprehensive system statistics"""
    online_cameras = sum(1 for status in camera_status.values() if status.get("status") == "online")
    recording_cameras = sum(1 for recording in camera_recordings.values() if recording)
    motion_count = len(motion_alerts)
    
    # Calculate uptime
    uptime_seconds = (datetime.now() - system_stats["start_time"]).total_seconds()
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    uptime_str = f"{hours}h {minutes}m"
    
    return {
        "total_cameras": len(CAMERAS),
        "online_cameras": online_cameras,
        "offline_cameras": len(CAMERAS) - online_cameras,
        "recording_cameras": recording_cameras,
        "motion_alerts": motion_count,
        "total_recordings": system_stats["total_recordings"],
        "total_motion_events": system_stats["total_motion_events"],
        "uptime": uptime_str,
        "system_health": "healthy" if online_cameras > 0 else "degraded"
    }

@app.post("/api/camera/{camera_name}/settings")
def update_camera_settings(camera_name: str, settings: dict):
    """Update camera-specific settings"""
    if camera_name not in CAMERAS:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    camera_settings[camera_name] = settings
    return {"status": "success", "settings": camera_settings[camera_name]}

@app.get("/api/camera/{camera_name}/settings")
def get_camera_settings(camera_name: str):
    """Get camera-specific settings"""
    if camera_name not in CAMERAS:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return camera_settings.get(camera_name, {
        "motion_sensitivity": 500,
        "recording_quality": "high",
        "auto_record_motion": False,
        "notification_enabled": True
    })

@app.post("/api/cameras/bulk_action")
def bulk_camera_action(action_data: dict):
    """Perform bulk actions on multiple cameras"""
    action = action_data.get("action")
    cameras = action_data.get("cameras", [])
    
    results = {}
    
    for camera in cameras:
        if camera not in CAMERAS:
            results[camera] = {"status": "error", "message": "Camera not found"}
            continue
            
        try:
            if action == "start_recording":
                camera_recordings[camera] = True
                recording_states[camera] = True
                results[camera] = {"status": "success", "recording": True}
            elif action == "stop_recording":
                camera_recordings[camera] = False
                recording_states[camera] = False
                results[camera] = {"status": "success", "recording": False}
            else:
                results[camera] = {"status": "error", "message": "Invalid action"}
        except Exception as e:
            results[camera] = {"status": "error", "message": str(e)}
    
    return {"results": results}

@app.delete("/api/recording/{filename}")
def delete_recording(filename: str):
    """Delete a specific recording file"""
    try:
        filepath = os.path.join("recordings", filename)
        if os.path.exists(filepath) and filename.endswith(".mp4"):
            os.remove(filepath)
            return {"status": "success", "message": f"Recording {filename} deleted"}
        else:
            raise HTTPException(status_code=404, detail="Recording not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete recording: {str(e)}")

@app.post("/api/system/restart")
def restart_system():
    """Restart the CCTV system"""
    try:
        # Clear all states
        global motion_alerts, camera_recordings, recording_states
        motion_alerts.clear()
        camera_recordings.clear()
        recording_states.clear()
        
        # Reset stats
        system_stats["start_time"] = datetime.now()
        
        return {"status": "success", "message": "System restarted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart system: {str(e)}")

@app.get("/api/health")
def health_check():
    """System health check endpoint"""
    online_cameras = sum(1 for status in camera_status.values() if status.get("status") == "online")
    
    health_status = {
        "status": "healthy" if online_cameras > 0 else "unhealthy",
        "timestamp": datetime.now().isoformat(),
        "cameras_online": online_cameras,
        "total_cameras": len(CAMERAS),
        "services": {
            "camera_monitor": "running",
            "motion_detection": "running",
            "recording_service": "running"
        }
    }
    
    return health_status

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

