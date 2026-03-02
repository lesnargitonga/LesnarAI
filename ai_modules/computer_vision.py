"""
Computer Vision Module for Lesnar AI Drone System
Advanced AI-powered image processing and object detection
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
import logging
from dataclasses import dataclass
import time
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class DetectedObject:
    """Represents a detected object in the camera feed"""
    object_id: str
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    center: Tuple[float, float]
    distance: Optional[float] = None
    timestamp: str = None

class ComputerVisionSystem:
    """
    Advanced computer vision system for drone applications
    Includes object detection, tracking, and obstacle avoidance
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.logger = logging.getLogger(__name__)
        self.is_initialized = False
        self.detection_threshold = 0.5
        self.tracking_objects = {}
        self.object_counter = 0
        self.config = config or {}
        self.backend = self.config.get('backend', 'sim')  # 'sim' or 'ultralytics'
        self.yolo_model = None
        # Segmentation optional
        self.segmentation = None
        self.seg_threshold = 0.5
        
        # Initialize object detection models (simulation)
        self.initialize_models()
    
    def initialize_models(self):
        """Initialize AI models for object detection"""
        try:
            # In a real implementation, you would load actual models like:
            # - YOLOv8 for object detection
            # - DeepSORT for object tracking
            # - Custom models for specific drone applications
            
            self.logger.info("Initializing computer vision models...")
            
            # Try to load Ultralytics YOLO if configured
            yolo_path = self.config.get('yolo_model')
            if yolo_path:
                try:
                    from ultralytics import YOLO  # type: ignore
                    self.yolo_model = YOLO(yolo_path)
                    self.backend = 'ultralytics'
                    self.logger.info(f"Loaded YOLO model: {yolo_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to load YOLO model '{yolo_path}', falling back to sim backend: {e}")
                    self.backend = 'sim'
                    self.yolo_model = None
            else:
                # Simulate model loading
                time.sleep(1)
            
            # Define object classes that can be detected
            self.object_classes = [
                'vehicle', 'building', 'tree', 'bird', 
                'aircraft', 'drone', 'powerline', 'tower', 'obstacle'
            ]
            
            # Initialize segmentation if configured
            try:
                seg_cfg = (self.config.get('segmentation') or {}) if isinstance(self.config, dict) else {}
                if seg_cfg.get('enabled'):
                    backend = seg_cfg.get('backend', 'torch')
                    if backend == 'torch':
                        from .segmentation_inference_torch import TorchSegmenter  # type: ignore
                        model_path = seg_cfg.get('model_path', 'models/unet_torch_synth/model.pt')
                        img_size = tuple(seg_cfg.get('img_size', [256, 256]))
                        self.seg_threshold = float(seg_cfg.get('threshold', 0.5))
                        self.segmentation = TorchSegmenter(model_path, img_size=img_size, classes=1)
                        self.logger.info(f"Segmentation enabled (torch): {model_path}")
            except Exception as se:
                self.logger.warning(f"Segmentation init failed: {se}")

            self.is_initialized = True
            self.logger.info("Computer vision system initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize CV models: {e}")
            self.is_initialized = False
    
    def detect_objects(self, image: np.ndarray) -> List[DetectedObject]:
        """
        Detect objects in the given image
        In a real implementation, this would use YOLO or similar models
        """
        if not self.is_initialized:
            return []
        
        detected_objects = []
        
        try:
            if self.backend == 'ultralytics' and self.yolo_model is not None:
                # Run YOLO inference on CPU
                try:
                    results = self.yolo_model(image, verbose=False)[0]
                    names = self.yolo_model.names if hasattr(self.yolo_model, 'names') else {}
                    for i, box in enumerate(results.boxes):
                        conf = float(box.conf.item()) if hasattr(box.conf, 'item') else float(box.conf)
                        if conf < self.detection_threshold:
                            continue
                        xyxy = box.xyxy[0].tolist() if hasattr(box.xyxy[0], 'tolist') else list(box.xyxy[0])
                        x1, y1, x2, y2 = map(int, xyxy)
                        cls_id = int(box.cls.item()) if hasattr(box.cls, 'item') else int(box.cls)
                        cls_name = names.get(cls_id, str(cls_id))
                        center_x = (x1 + x2) / 2
                        center_y = (y1 + y2) / 2
                        object_size = max(1, (x2 - x1) * (y2 - y1))
                        estimated_distance = max(5.0, 1000 / np.sqrt(object_size))
                        detected_objects.append(DetectedObject(
                            object_id=f"obj_{self.object_counter}",
                            class_name=cls_name,
                            confidence=conf,
                            bbox=(x1, y1, x2, y2),
                            center=(center_x, center_y),
                            distance=estimated_distance,
                            timestamp=datetime.now().isoformat()
                        ))
                        self.object_counter += 1
                    self.logger.debug(f"Detected {len(detected_objects)} objects (YOLO)")
                    return detected_objects
                except Exception as yerr:
                    self.logger.warning(f"YOLO inference failed, falling back to sim backend: {yerr}")
                    # Fall through to sim backend

            # Sim backend fallback: generate some random detections
            height, width = image.shape[:2]
            num_detections = np.random.poisson(2)
            
            for i in range(min(num_detections, 6)):
                class_name = np.random.choice(self.object_classes)
                
                confidence = np.random.uniform(0.6, 0.95)
                x1 = np.random.randint(0, max(1, width - 100))
                y1 = np.random.randint(0, max(1, height - 100))
                w = np.random.randint(50, max(51, min(200, width - x1)))
                h = np.random.randint(50, max(51, min(200, height - y1)))
                x2 = min(width - 1, x1 + w)
                y2 = min(height - 1, y1 + h)
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                object_size = max(1, w * h)
                estimated_distance = max(10, 1000 / np.sqrt(object_size))
                detected_objects.append(DetectedObject(
                    object_id=f"obj_{self.object_counter}",
                    class_name=class_name,
                    confidence=confidence,
                    bbox=(x1, y1, x2, y2),
                    center=(center_x, center_y),
                    distance=estimated_distance,
                    timestamp=datetime.now().isoformat()
                ))
                self.object_counter += 1
            self.logger.debug(f"Detected {len(detected_objects)} objects (sim)")

        except Exception as e:
            self.logger.error(f"Object detection failed: {e}")
        
        return detected_objects
    
    def track_objects(self, detections: List[DetectedObject]) -> List[DetectedObject]:
        """
        Track objects across frames
        In a real implementation, this would use DeepSORT or similar
        """
        # Simple tracking simulation
        # Update existing tracked objects or create new ones
        for detection in detections:
            # Simple distance-based tracking
            min_distance = float('inf')
            closest_tracked_id = None
            
            for tracked_id, tracked_obj in self.tracking_objects.items():
                distance = np.sqrt(
                    (detection.center[0] - tracked_obj['center'][0])**2 + 
                    (detection.center[1] - tracked_obj['center'][1])**2
                )
                
                if distance < min_distance and distance < 50:  # 50 pixel threshold
                    min_distance = distance
                    closest_tracked_id = tracked_id
            
            if closest_tracked_id:
                # Update existing tracked object
                self.tracking_objects[closest_tracked_id].update({
                    'center': detection.center,
                    'bbox': detection.bbox,
                    'confidence': detection.confidence,
                    'last_seen': time.time()
                })
                detection.object_id = closest_tracked_id
            else:
                # New tracked object
                self.tracking_objects[detection.object_id] = {
                    'center': detection.center,
                    'bbox': detection.bbox,
                    'class_name': detection.class_name,
                    'confidence': detection.confidence,
                    'first_seen': time.time(),
                    'last_seen': time.time()
                }
        
        # Remove old tracked objects (not seen for 5 seconds)
        current_time = time.time()
        to_remove = []
        for tracked_id, tracked_obj in self.tracking_objects.items():
            if current_time - tracked_obj['last_seen'] > 5.0:
                to_remove.append(tracked_id)
        
        for tracked_id in to_remove:
            del self.tracking_objects[tracked_id]
        
        return detections
    
    def analyze_threats(self, detections: List[DetectedObject]) -> List[Dict]:
        """
        Analyze detected objects for potential threats or obstacles
        """
        threats = []
        
        for obj in detections:
            threat_level = 0
            threat_type = "info"
            
            # Define threat levels based on object class and distance
            if obj.class_name in ['aircraft', 'drone']:
                threat_level = 8
                threat_type = "critical"
            elif obj.class_name in ['building', 'tower', 'powerline']:
                threat_level = 9 if obj.distance < 50 else 6
                threat_type = "critical" if obj.distance < 50 else "warning"
            elif obj.class_name in ['bird']:
                threat_level = 5 if obj.distance < 30 else 3
                threat_type = "warning" if obj.distance < 30 else "info"
            elif obj.class_name in ['person', 'vehicle']:
                threat_level = 4
                threat_type = "warning"
            
            if threat_level > 3:  # Only report significant threats
                threat = {
                    'object_id': obj.object_id,
                    'class_name': obj.class_name,
                    'threat_level': threat_level,
                    'threat_type': threat_type,
                    'distance': obj.distance,
                    'position': obj.center,
                    'confidence': obj.confidence,
                    'timestamp': obj.timestamp
                }
                threats.append(threat)
        
        return threats
    
    def calculate_avoidance_vector(self, threats: List[Dict], current_heading: float) -> Tuple[float, float]:
        """
        Calculate avoidance vector based on detected threats
        Returns: (new_heading, urgency_factor)
        """
        if not threats:
            return current_heading, 0.0
        
        # Find the most critical threat
        critical_threat = max(threats, key=lambda t: t['threat_level'])
        
        # Calculate avoidance heading
        threat_x, threat_y = critical_threat['position']
        
        # Simple avoidance: turn away from threat
        avoidance_angle = 90  # Turn 90 degrees away
        if threat_x > 320:  # Assuming 640px width, threat on right
            new_heading = (current_heading - avoidance_angle) % 360
        else:  # Threat on left
            new_heading = (current_heading + avoidance_angle) % 360
        
        # Urgency based on distance and threat level
        urgency = min(1.0, critical_threat['threat_level'] / 10.0)
        if critical_threat['distance'] < 20:
            urgency = 1.0  # Maximum urgency for close threats
        
        return new_heading, urgency
    
    def draw_detections(self, image: np.ndarray, detections: List[DetectedObject]) -> np.ndarray:
        """
        Draw detection results on the image
        """
        output_image = image.copy()
        
        for obj in detections:
            x1, y1, x2, y2 = obj.bbox
            
            # Color based on object class
            color_map = {
                'person': (0, 255, 0),
                'vehicle': (255, 0, 0),
                'aircraft': (255, 0, 255),
                'drone': (255, 255, 0),
                'building': (128, 128, 128),
                'bird': (0, 255, 255)
            }
            color = color_map.get(obj.class_name, (255, 255, 255))
            
            # Draw bounding box
            cv2.rectangle(output_image, (x1, y1), (x2, y2), color, 2)
            
            # Draw label
            label = f"{obj.class_name}: {obj.confidence:.2f}"
            if obj.distance:
                label += f" ({obj.distance:.1f}m)"
            
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(output_image, (x1, y1 - label_size[1] - 10), 
                         (x1 + label_size[0], y1), color, -1)
            cv2.putText(output_image, label, (x1, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
        
        return output_image

    def overlay_segmentation(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        overlay = image.copy()
        if mask.ndim == 2:
            colored = np.zeros_like(image)
            colored[:, :, 2] = mask  # red channel for obstacles
        else:
            colored = mask
        alpha = 0.3
        cv2.addWeighted(colored, alpha, overlay, 1 - alpha, 0, overlay)
        return overlay
    
    def process_frame(self, image: np.ndarray, current_heading: float = 0.0) -> Dict:
        """
        Process a single frame and return comprehensive analysis
        """
        if not self.is_initialized:
            return {'error': 'Computer vision system not initialized'}
        
        try:
            # Optional segmentation
            seg_mask = None
            if self.segmentation is not None:
                try:
                    seg_mask = self.segmentation.predict_mask(image)
                except Exception as se:
                    self.logger.warning(f"Segmentation inference failed: {se}")
                    seg_mask = None

            # Detect objects
            detections = self.detect_objects(image)
            
            # Track objects
            tracked_detections = self.track_objects(detections)
            
            # Analyze threats
            threats = self.analyze_threats(tracked_detections)
            
            # Calculate avoidance if needed
            avoidance_heading, urgency = self.calculate_avoidance_vector(threats, current_heading)
            
            # Draw results
            annotated_image = self.draw_detections(image, tracked_detections)
            if seg_mask is not None:
                annotated_image = self.overlay_segmentation(annotated_image, seg_mask)
            
            return {
                'success': True,
                'detections': [
                    {
                        'object_id': obj.object_id,
                        'class_name': obj.class_name,
                        'confidence': obj.confidence,
                        'bbox': obj.bbox,
                        'center': obj.center,
                        'distance': obj.distance,
                        'timestamp': obj.timestamp
                    }
                    for obj in tracked_detections
                ],
                'threats': threats,
                'avoidance': {
                    'recommended_heading': avoidance_heading,
                    'urgency': urgency
                },
                'annotated_image': annotated_image,
                'segmentation': bool(seg_mask is not None),
                'processing_time': time.time()
            }
            
        except Exception as e:
            self.logger.error(f"Frame processing failed: {e}")
            return {'success': False, 'error': str(e)}

# Example usage and testing
if __name__ == "__main__":
    # Initialize computer vision system
    cv_system = ComputerVisionSystem()
    
    # Create a test image (simulated camera feed)
    test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    print("Processing test frame...")
    result = cv_system.process_frame(test_image)
    
    if result['success']:
        print(f"Detected {len(result['detections'])} objects")
        print(f"Identified {len(result['threats'])} threats")
        
        if result['threats']:
            print("Threats detected:")
            for threat in result['threats']:
                print(f"  - {threat['class_name']}: Level {threat['threat_level']} at {threat['distance']:.1f}m")
        
        if result['avoidance']['urgency'] > 0.5:
            print(f"Avoidance recommended: Turn to {result['avoidance']['recommended_heading']:.1f}°")
    
    else:
        print(f"Processing failed: {result['error']}")
    
    print("Computer vision test completed")
