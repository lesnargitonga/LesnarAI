# GPS-Denied PX4 Configuration

This configuration sets EKF2 to fuse Optical Flow and Rangefinder height, ignoring GPS.

Prerequisites:
- Optical flow sensor (e.g., PX4Flow) wired and enabled.
- Rangefinder (lidar/sonar) mounted and calibrated.

Apply via QGroundControl:
1. Vehicle → Parameters → Tools → Manage Parameter Files → select `gps_denied.params`.
2. Reboot the autopilot.
3. Verify: Mavlink console → `ekf2 status`; check AID_MASK and height mode.

Bench Test:
- Disable GPS or simulate jamming.
- Arm in `ALTCTL`/`POSCTL` with flow; confirm stable hover without GPS.