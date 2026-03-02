
import airsim
import os
import time

def capture():
    print("Connecting to AirSim...")
    client = airsim.MultirotorClient()
    try:
        client.confirmConnection()
    except Exception as e:
        print(f"Failed to connect: {e}")
        return False

    print("Connected! Capturing screenshot...")
    
    # Request scene image
    responses = client.simGetImages([
        airsim.ImageRequest("0", airsim.ImageType.Scene)
    ])
    
    if not responses:
        print("No images returned.")
        return False

    response = responses[0]
    
    # Save to known location
    # Note: AirSim returns raw bytes for Scene (png format allowed) or uncompressed
    filename = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "visual_evidence.png")
    
    if response.pixels_as_float:
        print("Type is float, expected bytes for simple png capture. Saving as PFM not supported for this demo.")
        return False
    else:
        # Write bytes
        airsim.write_file(filename, response.image_data_uint8)
        print(f"Screenshot saved to: {filename}")
        return True

if __name__ == "__main__":
    success = capture()
    if not success:
        print("Screenshot capture failed.")
        exit(1)
    else:
        exit(0)
