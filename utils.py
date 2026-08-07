import re
import time
import httpx
import threading
from bot_client import client

pending_timers = {}

class VisualCountdownTimer(threading.Thread):
    def __init__(self, duration, callback, args):
        super().__init__()
        self.duration = int(duration)
        self.callback = callback
        self.args = args
        self.cancelled = False
        self.paused = False
        
    def cancel(self):
        self.cancelled = True
        
    def pause(self):
        self.paused = True
        
    def resume(self):
        self.paused = False
        
    def run(self):
        user_id_str, channel_id, sender_name = self.args
        for i in range(self.duration, 0, -1):
            for _ in range(10):
                if self.cancelled:
                    return
                time.sleep(0.1)
                
            if self.cancelled:
                return
                
            if not self.paused:
                try:
                    client.send_message(channel_id, f"⏳ {i}...")
                except Exception:
                    pass
            
        if not self.cancelled:
            self.callback(*self.args)

def extract_lat_lon_from_url(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        with httpx.Client(follow_redirects=True) as client_http:
            resp = client_http.get(url, headers=headers, timeout=10.0)
            final_url = str(resp.url)
            # Match variations like @lat,lon or q=lat,lon or place/lat,lon
            match = re.search(r'(?:@|q=|place/)(-?\d+\.\d+),(-?\d+\.\d+)', final_url)
            if match:
                return float(match.group(1)), float(match.group(2))
    except Exception as e:
        print(f"Failed to resolve Maps URL: {e}")
    return 0.0, 0.0
