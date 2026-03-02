import airsim
import time

client = airsim.MultirotorClient()
client.confirmConnection()

print("Available Scene Objects:", len(client.simListSceneObjects()))
print("Vehicles:", client.listVehicles())

# Try to get Lidar data
try:
    lidar_data = client.getLidarData(lidar_name="", vehicle_name="")
    if len(lidar_data.point_cloud) > 0:
        print(f"Lidar detected! Points: {len(lidar_data.point_cloud)//3}")
    else:
        print("Lidar returned 0 points (might not be in settings.json)")
except Exception as e:
    print(f"Lidar error: {e}")

# Check camera configurations
import json
try:
    # AirSim settings are sometimes accessible via simGetSettingsString()
    settings_str = client.simGetSettingsString()
    print("Settings found via simGetSettingsString")
    # settings = json.loads(settings_str)
except Exception:
    print("Could not get settings string")
