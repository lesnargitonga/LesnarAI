"""
Data Pipeline Manager for Lesnar AI
Coordinates data collection, processing, and model training workflows
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path
import asyncio
from dataclasses import dataclass, asdict

# --- New Imports ---
from PIL import Image
import random
# --- End New Imports ---

@dataclass
class DataMetrics:
    """Metrics for data quality and usage tracking"""
    timestamp: str
    data_type: str
    file_count: int
    total_size_mb: float
    quality_score: float
    processing_time_ms: float

class DataPipelineManager:
    """
    Manages the entire data pipeline for Lesnar AI
    - Ingests operational data from drones
    - Processes and validates data quality
    - Feeds data to training pipelines
    - Monitors data drift and model performance
    """
    
    def __init__(self, config_path: str = "config.json"):
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config(config_path)
        
        # --- Modified Paths ---
        self.data_root = Path(self.config.get('data_root', 'data'))
        self.models_root = Path(self.config.get('models_root', 'models'))
        self.logs_root = Path(self.config.get('logs_root', 'logs'))
        self.dataset_root = Path(self.config.get('data_pipeline', {}).get('dataset_root', 'datasets'))
        # --- End Modified Paths ---

        # Performance tracking
        self.metrics_history = []
        self.active_sessions = {}
        
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.warning(f"Config file {config_path} not found, using defaults")
            return {}
    
    async def collect_operational_data(self, drone_id: str, session_id: str) -> Dict:
        """
        Collect real-time operational data from active drone sessions
        """
        session_data = {
            'drone_id': drone_id,
            'session_id': session_id,
            'start_time': datetime.now().isoformat(),
            'telemetry': [],
            'vision_data': [],
            'autonomy_decisions': []
        }
        
        # Monitor autonomy logs for this session
        autonomy_logs = self._read_latest_autonomy_logs(drone_id)
        if autonomy_logs:
            session_data['telemetry'] = autonomy_logs
            
        # Process segmentation data
        seg_data = self._process_segmentation_data(session_id)
        if seg_data:
            session_data['vision_data'] = seg_data
            
        return session_data
    
    def _read_latest_autonomy_logs(self, drone_id: str) -> List[Dict]:
        """Read the most recent autonomy logs for analysis"""
        log_files = list(self.logs_root.glob(f"autonomy_*.csv"))
        if not log_files:
            return []
            
        # Get the most recent log file
        latest_log = max(log_files, key=lambda x: x.stat().st_mtime)
        
        try:
            df = pd.read_csv(latest_log)
            # Convert to list of dictionaries for processing
            return df.to_dict('records')
        except Exception as e:
            self.logger.error(f"Error reading autonomy logs: {e}")
            return []
    
    def _process_segmentation_data(self, session_id: str) -> List[Dict]:
        """Process segmentation performance data"""
        seg_files = ['seg_run_commit.csv', 'seg_run_fsm.csv', 'seg_run_geom.csv']
        processed_data = []
        
        for seg_file in seg_files:
            file_path = self.logs_root / seg_file
            if file_path.exists():
                try:
                    df = pd.read_csv(file_path)
                    # Extract meaningful metrics
                    metrics = {
                        'algorithm': seg_file.replace('.csv', '').replace('seg_run_', ''),
                        'avg_largest_area': df['largest_area_frac'].mean() if 'largest_area_frac' in df.columns else 0,
                        'detection_rate': (df['gap_center_deg'].notna()).mean() if 'gap_center_deg' in df.columns else 0,
                        'processing_fps': len(df) / (df['t'].max() - df['t'].min()) if len(df) > 1 else 0
                    }
                    processed_data.append(metrics)
                except Exception as e:
                    self.logger.error(f"Error processing {seg_file}: {e}")
        
        return processed_data
    
    def analyze_dataset_coverage(self) -> Dict:
        """
        Analyze which datasets are available and their completeness by scanning the dataset_root.
        """
        if not self.dataset_root.exists() or not self.dataset_root.is_dir():
            self.logger.warning(f"Dataset root {self.dataset_root} not found.")
            return {}

        coverage_analysis = {
            'dataset_root': str(self.dataset_root),
            'available_datasets': [],
            'missing_datasets': [], # This will be based on a predefined list of expected sets
            'data_types': {
                'vision': 0, 'slam': 0, 'synthetic': 0, 'real_world': 0, 'drone': 0, 'other': 0
            }
        }

        expected_datasets = ['coco', 'tum', 'euroc', 'airsim_synth', 'sdd', 'visdrone', 'uavdt', 'dota', 'isaid', 'cityscapes', 'mapillary_vistas', 'bdd100k', 'semantic_kitti', 'nuscenes', 'kitti', 'waymo_open', 'argoverse', 'tartanair', 'habitat']
        found_datasets = set()

        for item in self.dataset_root.iterdir():
            if not item.is_dir():
                continue

            dir_name = item.name.lower()
            found_datasets.add(dir_name)
            
            # Calculate directory size and file count
            total_size = 0
            file_count = 0
            try:
                for root, _, files in os.walk(item):
                    file_count += len(files)
                    for f in files:
                        total_size += (Path(root) / f).stat().st_size
            except FileNotFoundError:
                # Handles cases where a directory might be deleted during scan
                continue

            dataset_info = {
                'name': item.name,
                'path': str(item),
                'files': file_count,
                'size_bytes': total_size,
                'size_human': f"{total_size / (1024**3):.2f} GB"
            }
            coverage_analysis['available_datasets'].append(dataset_info)

            # Categorize by type
            if any(term in dir_name for term in ['visdrone', 'uavdt', 'sdd', 'dota', 'isaid']):
                coverage_analysis['data_types']['drone'] += 1
            elif any(term in dir_name for term in ['coco', 'cityscapes', 'bdd', 'mapillary']):
                coverage_analysis['data_types']['vision'] += 1
            elif 'tum' in dir_name or 'euroc' in dir_name:
                coverage_analysis['data_types']['slam'] += 1
            elif 'airsim' in dir_name or 'tartanair' in dir_name:
                coverage_analysis['data_types']['synthetic'] += 1
            elif any(term in dir_name for term in ['kitti', 'nuscenes', 'waymo', 'argoverse']):
                 coverage_analysis['data_types']['real_world'] += 1
            else:
                coverage_analysis['data_types']['other'] += 1
        
        coverage_analysis['missing_datasets'] = list(set(expected_datasets) - found_datasets)
        
        return coverage_analysis

    def get_dataset_loader(self, dataset_name: str, split: str = 'train', augment: bool = False):
        """
        Factory method to get a data loader for a specific dataset.
        
        :param dataset_name: The name of the dataset (e.g., 'coco').
        :param split: The dataset split, e.g., 'train' or 'val'.
        :param augment: Whether to apply data augmentation.
        :return: A data loader iterator.
        """
        if dataset_name.lower() == 'coco':
            coco_path = self.dataset_root / 'coco'
            if not coco_path.exists():
                self.logger.error(f"COCO dataset not found at {coco_path}")
                return None
            return self._load_coco_dataset(coco_path, split=split, augment=augment)
        else:
            self.logger.warning(f"Data loader for '{dataset_name}' is not yet implemented.")
            return None

    def _load_coco_dataset(self, coco_path: Path, split: str = 'train', augment: bool = False):
        """
        Loads the COCO dataset and provides an iterator.
        This is a generator function that yields individual data points.
        
        :param coco_path: Path to the COCO dataset root.
        :param split: 'train' or 'val' (e.g., 'train2017', 'val2017').
        :param augment: If True, applies basic data augmentation.
        """
        year = '2017' # Or could be parameterized
        image_dir = coco_path / f"{split}{year}"
        annotation_file = coco_path / 'annotations' / f"instances_{split}{year}.json"

        if not image_dir.exists() or not annotation_file.exists():
            self.logger.error(f"COCO {split} data not found in {coco_path}")
            return

        with open(annotation_file, 'r') as f:
            annotations = json.load(f)
        
        images = {img['id']: img for img in annotations['images']}
        
        # Create a map from image_id to annotations
        img_to_anns = {}
        for ann in annotations['annotations']:
            img_id = ann['image_id']
            if img_id not in img_to_anns:
                img_to_anns[img_id] = []
            img_to_anns[img_id].append(ann)

        self.logger.info(f"Loading COCO {split} set with {len(images)} images.")

        for img_id, img_info in images.items():
            img_path = image_dir / img_info['file_name']
            if not img_path.exists():
                continue

            image = Image.open(img_path).convert("RGB")
            
            # --- Data Augmentation Hook ---
            if augment:
                # Placeholder for real data augmentation library (e.g., Albumentations, torchvision.transforms)
                # 1. Random horizontal flip
                if random.random() > 0.5:
                    image = image.transpose(Image.FLIP_LEFT_RIGHT)
                
                # 2. Random color jitter (brightness, contrast)
                # This would typically be done with a library for better results.
                # For now, this is a conceptual placeholder.
                pass
            # --- End Augmentation Hook ---

            record = {
                'image_id': img_id,
                'file_name': img_info['file_name'],
                'image': image,
                'annotations': img_to_anns.get(img_id, [])
            }
            yield record

    def prioritize_training_data(self) -> List[Dict]:
        """
        Prioritize which datasets to use for training based on:
        1. Available data size
        2. Relevance to drone operations
        3. Data quality metrics
        """
        coverage = self.analyze_dataset_coverage()
        
        # Priority ranking for drone applications
        priority_weights = {
            'airsim_synthetic': 10,  # Synthetic drone data
            'visdrone': 9,          # Drone-specific vision
            'uavdt': 9,             # UAV detection and tracking
            'stanford_drone': 8,    # Drone behavior data
            'cityscapes': 7,        # Urban navigation
            'coco': 6,              # General object detection
            'bdd100k': 6,           # Driving scenes (similar to drone perspective)
            'tum': 5,               # SLAM data
            'euroc': 5              # Visual-inertial odometry
        }
        
        training_priorities = []
        for dataset in coverage['available_datasets']:
            dataset_name = dataset['name'].lower()
            priority = 0
            
            # Calculate priority score
            for key, weight in priority_weights.items():
                if key in dataset_name:
                    priority = weight
                    break
            
            # Adjust for data size (more data = higher priority)
            size_multiplier = min(dataset['files'] / 1000, 2.0)  # Cap at 2x
            final_priority = priority * (1 + size_multiplier)
            
            training_priorities.append({
                'dataset': dataset['name'],
                'priority_score': final_priority,
                'files': dataset['files'],
                'size': dataset['size'],
                'recommended_use': self._get_recommended_use(dataset_name)
            })
        
        # Sort by priority score
        training_priorities.sort(key=lambda x: x['priority_score'], reverse=True)
        return training_priorities
    
    def _get_recommended_use(self, dataset_name: str) -> str:
        """Recommend specific use cases for each dataset"""
        dataset_name = dataset_name.lower()
        
        if 'airsim' in dataset_name:
            return "Primary training for simulation-to-real transfer"
        elif 'visdrone' in dataset_name or 'uavdt' in dataset_name:
            return "Fine-tuning object detection for aerial perspective"
        elif 'stanford_drone' in dataset_name:
            return "Learning drone trajectory patterns and behaviors"
        elif 'cityscapes' in dataset_name:
            return "Semantic segmentation for urban environments"
        elif 'coco' in dataset_name:
            return "General object detection and classification"
        elif 'bdd100k' in dataset_name:
            return "Multi-class detection in complex scenes"
        elif 'tum' in dataset_name or 'euroc' in dataset_name:
            return "Visual-inertial navigation and SLAM"
        else:
            return "Additional training data for improved generalization"
    
    def generate_training_pipeline(self, target_capability: str) -> Dict:
        """
        Generate a specific training pipeline based on desired capability
        """
        priorities = self.prioritize_training_data()
        
        pipelines = {
            'object_detection': {
                'primary_datasets': ['visdrone', 'uavdt', 'coco'],
                'model_architecture': 'YOLOv8 or EfficientDet',
                'training_strategy': 'Transfer learning from COCO, fine-tune on drone data',
                'validation_split': 0.2,
                'expected_training_time': '2-4 hours on GPU'
            },
            'semantic_segmentation': {
                'primary_datasets': ['cityscapes', 'airsim_synthetic'],
                'model_architecture': 'DeepLabV3+ or U-Net',
                'training_strategy': 'Pre-train on Cityscapes, adapt to drone perspective',
                'validation_split': 0.15,
                'expected_training_time': '4-8 hours on GPU'
            },
            'visual_navigation': {
                'primary_datasets': ['tum', 'euroc', 'airsim_synthetic'],
                'model_architecture': 'Visual-Inertial Odometry CNN',
                'training_strategy': 'Multi-modal fusion training',
                'validation_split': 0.25,
                'expected_training_time': '6-12 hours on GPU'
            },
            'collision_avoidance': {
                'primary_datasets': ['stanford_drone', 'airsim_synthetic'],
                'model_architecture': 'Temporal CNN or LSTM',
                'training_strategy': 'Sequence-to-sequence prediction',
                'validation_split': 0.2,
                'expected_training_time': '3-6 hours on GPU'
            }
        }
        
        if target_capability not in pipelines:
            raise ValueError(f"Unknown capability: {target_capability}")
        
        pipeline = pipelines[target_capability]
        
        # Add available datasets and their priorities
        pipeline['available_datasets'] = [
            p for p in priorities 
            if any(ds in p['dataset'].lower() for ds in pipeline['primary_datasets'])
        ]
        
        # Add implementation steps
        pipeline['implementation_steps'] = self._generate_implementation_steps(target_capability)
        
        return pipeline
    
    def _generate_implementation_steps(self, capability: str) -> List[str]:
        """Generate step-by-step implementation guide"""
        base_steps = [
            "1. Prepare data loaders for prioritized datasets",
            "2. Set up model architecture and transfer learning",
            "3. Configure training hyperparameters",
            "4. Implement validation and testing pipeline",
            "5. Set up monitoring and logging",
            "6. Train model with early stopping",
            "7. Evaluate on test set and drone-specific metrics",
            "8. Deploy model and monitor performance"
        ]
        
        capability_specific = {
            'object_detection': [
                "9. Test detection accuracy at various altitudes",
                "10. Validate real-time inference speed requirements",
                "11. Implement non-maximum suppression optimization"
            ],
            'semantic_segmentation': [
                "9. Validate segmentation quality for landing zones",
                "10. Test performance in various lighting conditions",
                "11. Optimize for real-time processing"
            ],
            'visual_navigation': [
                "9. Test navigation accuracy in GPS-denied environments",
                "10. Validate drift correction mechanisms",
                "11. Implement fail-safe procedures"
            ],
            'collision_avoidance': [
                "9. Test with multiple moving objects",
                "10. Validate emergency maneuver capabilities",
                "11. Implement confidence thresholding"
            ]
        }
        
        return base_steps + capability_specific.get(capability, [])
    
    def create_implementation_plan(self) -> Dict:
        """
        Create a comprehensive implementation plan based on current data assets
        """
        coverage = self.analyze_dataset_coverage()
        priorities = self.prioritize_training_data()
        
        plan = {
            'timeline': '12 weeks',
            'phases': {
                'Phase 1 (Weeks 1-3): Foundation': {
                    'objectives': [
                        'Set up data processing pipelines',
                        'Implement model training infrastructure',
                        'Create baseline performance metrics'
                    ],
                    'deliverables': [
                        'Automated data ingestion system',
                        'Model training scripts',
                        'Performance monitoring dashboard'
                    ]
                },
                'Phase 2 (Weeks 4-8): Core Capabilities': {
                    'objectives': [
                        'Train object detection models',
                        'Implement semantic segmentation',
                        'Deploy collision avoidance system'
                    ],
                    'deliverables': [
                        'Real-time object detection (>30 FPS)',
                        'Landing zone assessment system',
                        'Automated collision avoidance'
                    ]
                },
                'Phase 3 (Weeks 9-12): Advanced Features': {
                    'objectives': [
                        'Implement predictive analytics',
                        'Deploy swarm coordination',
                        'Optimize performance and scaling'
                    ],
                    'deliverables': [
                        'Predictive maintenance system',
                        'Multi-drone coordination',
                        'Production-ready deployment'
                    ]
                }
            },
            'resource_requirements': {
                'compute': 'GPU cluster with 4+ V100 or A100 GPUs',
                'storage': '1TB+ for datasets and model checkpoints',
                'personnel': '2-3 ML engineers, 1 DevOps engineer',
                'timeline': '12 weeks for full implementation'
            },
            'success_metrics': {
                'object_detection_accuracy': '>90%',
                'real_time_processing': '<100ms latency',
                'collision_avoidance_success': '>99%',
                'predictive_accuracy': '>85%'
            },
            'next_immediate_steps': [
                'Run dataset audit and prepare training data',
                'Set up MLOps infrastructure (MLflow, DVC)',
                'Implement first object detection pipeline',
                'Create baseline performance benchmarks'
            ]
        }
        
        return plan

# Utility functions for immediate implementation
def create_training_config(capability: str) -> Dict:
    """Create a training configuration for immediate use"""
    manager = DataPipelineManager()
    pipeline = manager.generate_training_pipeline(capability)
    
    config = {
        'capability': capability,
        'datasets': [d['dataset'] for d in pipeline['available_datasets']],
        'model_config': {
            'architecture': pipeline['model_architecture'],
            'batch_size': 16,
            'learning_rate': 0.001,
            'epochs': 50,
            'validation_split': pipeline['validation_split']
        },
        'training_strategy': pipeline['training_strategy'],
        'implementation_steps': pipeline['implementation_steps']
    }
    
    return config

def get_immediate_priorities() -> List[str]:
    """Get the top 3 immediate priorities based on available data"""
    manager = DataPipelineManager()
    priorities = manager.prioritize_training_data()
    
    # Extract top capabilities we can implement immediately
    immediate_capabilities = []
    
    if any('visdrone' in d['dataset'].lower() or 'coco' in d['dataset'].lower() 
           for d in priorities[:3]):
        immediate_capabilities.append('object_detection')
    
    if any('cityscapes' in d['dataset'].lower() or 'airsim' in d['dataset'].lower() 
           for d in priorities[:3]):
        immediate_capabilities.append('semantic_segmentation')
    
    if any('tum' in d['dataset'].lower() or 'euroc' in d['dataset'].lower() 
           for d in priorities[:3]):
        immediate_capabilities.append('visual_navigation')
    
    return immediate_capabilities[:3]

if __name__ == "__main__":
    # Example usage
    manager = DataPipelineManager()
    
    # Analyze current situation
    print("--- Live Dataset Coverage Analysis ---")
    coverage = manager.analyze_dataset_coverage()
    print(json.dumps(coverage, indent=2))
    
    # Get training priorities based on live data
    print("\n--- Training Priorities (from live data) ---")
    priorities = manager.prioritize_training_data()
    for i, p in enumerate(priorities[:5]):
        print(f"{i+1}. {p['dataset']} (Score: {p['priority_score']:.2f}) - Use: {p['recommended_use']}")

    # --- Example: Using the new COCO data loader ---
    print("\n--- Testing COCO Data Loader ---")
    coco_loader = manager.get_dataset_loader('coco', split='val', augment=True)
    if coco_loader:
        print("Successfully created COCO validation loader.")
        # Fetch one sample
        try:
            sample_data = next(coco_loader)
            print(f"Sample loaded: Image '{sample_data['file_name']}' with {len(sample_data['annotations'])} annotations.")
            sample_data['image'].show(title=f"Sample: {sample_data['file_name']}")
        except StopIteration:
            print("COCO validation set is empty or could not be loaded.")
        except Exception as e:
            print(f"An error occurred while fetching a sample: {e}")
    
    # Create implementation plan
    plan = manager.create_implementation_plan()
    print("\n--- Implementation Plan ---")
    print(f"Timeline: {plan['timeline']}")
    print("Next Steps:")
    for step in plan['next_immediate_steps']:
        print(f"- {step}")