#!/usr/bin/env python3

import asyncio
from miio import Device, DeviceException
import logging
import json
import time
from datetime import datetime
import argparse
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class XiaomiAirPurifier4Mini:
    def __init__(self, ip, token):
        self.ip = ip
        self.token = token
        self.device = None
    
    async def connect(self):
        """Connect to the Air Purifier device."""
        try:
            self.device = Device(self.ip, self.token)
            info = self.device.info()
            logger.info(f"Connected to {info.model} at {self.ip}")
            logger.info(f"Firmware version: {info.firmware_version}")
            return True
        except DeviceException as ex:
            logger.error(f"Connection error: {ex}")
            return False
    
    async def get_air_quality(self):
        """Get air quality data from the device."""
        try:
            # Get status from the device
            status = self.device.status()
            
            # The exact property names might vary by model and firmware version
            # Common properties for air quality
            air_quality = {
                'timestamp': datetime.now().isoformat(),
                'aqi': self._get_property(status, 'aqi'),
                'pm2.5': self._get_property(status, 'pm2_5'),
                'temperature': self._get_property(status, 'temperature'),
                'humidity': self._get_property(status, 'humidity'),
                'mode': self._get_property(status, 'mode'),
                'power': self._get_property(status, 'power'),
                'filter_life_remaining': self._get_property(status, 'filter_life_remaining')
            }
            
            return air_quality
        except DeviceException as ex:
            logger.error(f"Error getting air quality: {ex}")
            return None
    
    def _get_property(self, status, property_name):
        """Safely extract a property from the status object."""
        try:
            return getattr(status, property_name)
        except AttributeError:
            return None

class FirebaseManager:
    def __init__(self, credential_path, database_url, device_id):
        """Initialize Firebase connection."""
        self.device_id = device_id
        self.initialized = False
        
        try:
            cred = credentials.Certificate(credential_path)
            firebase_admin.initialize_app(cred, {
                'databaseURL': database_url
            })
            self.initialized = True
            logger.info("Firebase connection established successfully")
        except Exception as ex:
            logger.error(f"Firebase initialization error: {ex}")
    
    def send_data(self, air_quality_data):
        """Send air quality data to Firebase."""
        if not self.initialized:
            logger.error("Firebase not initialized")
            return False
        
        try:
            # Create a reference to the air quality data location
            ref = db.reference(f'/devices/{self.device_id}/air_quality')
            
            # Store the current reading with timestamp as key
            timestamp_key = datetime.now().strftime('%Y%m%d%H%M%S')
            ref.child(timestamp_key).set(air_quality_data)
            
            # Also update the latest reading
            latest_ref = db.reference(f'/devices/{self.device_id}/latest')
            latest_ref.set(air_quality_data)
            
            logger.info("Data sent to Firebase successfully")
            return True
        except Exception as ex:
            logger.error(f"Error sending data to Firebase: {ex}")
            return False

async def monitor_air_quality(ip, token, interval=60, output_file=None, 
                             firebase_cred=None, firebase_url=None, device_id=None):
    """Monitor air quality at given intervals."""
    purifier = XiaomiAirPurifier4Mini(ip, token)
    
    # Initialize Firebase if credentials are provided
    firebase_manager = None
    if firebase_cred and firebase_url and device_id:
        firebase_manager = FirebaseManager(firebase_cred, firebase_url, device_id)
    
    if not await purifier.connect():
        logger.error("Failed to connect to the device")
        return
    
    data_points = []
    
    try:
        while True:
            air_quality = await purifier.get_air_quality()
            if air_quality:
                logger.info(f"Air Quality: PM2.5={air_quality.get('pm2.5')}, AQI={air_quality.get('aqi')}, "
                           f"Temperature={air_quality.get('temperature')}°C, Humidity={air_quality.get('humidity')}%")
                
                data_points.append(air_quality)
                
                # Save to local file if specified
                if output_file:
                    with open(output_file, 'w') as f:
                        json.dump(data_points, f, indent=2)
                
                # Send to Firebase if initialized
                if firebase_manager:
                    firebase_manager.send_data(air_quality)
            
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as ex:
        logger.error(f"Error during monitoring: {ex}")

def main():
    parser = argparse.ArgumentParser(description='Monitor Xiaomi Air Purifier 4 Mini air quality')
    parser.add_argument('--ip', required=True, help='IP address of the Air Purifier')
    parser.add_argument('--token', required=True, help='Token for authentication')
    parser.add_argument('--interval', type=int, default=60, help='Monitoring interval in seconds (default: 60)')
    parser.add_argument('--output', help='Output file for storing data (JSON format)')
    parser.add_argument('--firebase-cred', help='Path to Firebase credentials JSON file')
    parser.add_argument('--firebase-url', help='Firebase database URL')
    parser.add_argument('--device-id', help='Unique identifier for this device in Firebase')
    
    args = parser.parse_args()
    
    # Check if Firebase parameters are properly set
    if any([args.firebase_cred, args.firebase_url, args.device_id]) and not all([args.firebase_cred, args.firebase_url, args.device_id]):
        logger.error("When using Firebase, you must provide all three Firebase parameters: --firebase-cred, --firebase-url, and --device-id")
        return
    
    asyncio.run(monitor_air_quality(
        args.ip, 
        args.token, 
        args.interval, 
        args.output,
        args.firebase_cred,
        args.firebase_url,
        args.device_id
    ))

if __name__ == "__main__":
    main()
