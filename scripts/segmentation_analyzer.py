"""
Segmentation Performance Analyzer for Lesnar AI
Analyzes segmentation logs to identify performance patterns and optimization opportunities
"""

import csv
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import statistics

class SegmentationAnalyzer:
    """
    Analyzes segmentation performance data to identify improvement opportunities
    """
    
    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = Path(logs_dir)
        self.algorithms = ['commit', 'fsm', 'geom']
        self.data = {}
        self.analysis_results = {}
        
    def load_segmentation_data(self) -> Dict:
        """Load all segmentation log files"""
        print("Loading segmentation data...")
        
        for algorithm in self.algorithms:
            filename = f"seg_run_{algorithm}.csv"
            filepath = self.logs_dir / filename
            
            if filepath.exists():
                self.data[algorithm] = self._load_csv_file(filepath)
                print(f"  Loaded {filename}: {len(self.data[algorithm])} records")
            else:
                print(f"  Warning: {filename} not found")
                self.data[algorithm] = []
        
        return self.data
    
    def _load_csv_file(self, filepath: Path) -> List[Dict]:
        """Load CSV file and convert to list of dictionaries"""
        data = []
        try:
            with open(filepath, 'r') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    # Convert numeric fields
                    for key, value in row.items():
                        if key != 't':  # Skip timestamp for now
                            try:
                                if value.lower() == 'nan':
                                    row[key] = None
                                else:
                                    row[key] = float(value)
                            except (ValueError, AttributeError):
                                pass
                    data.append(row)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
        
        return data
    
    def analyze_gap_detection_performance(self) -> Dict:
        """Analyze gap detection success rates and patterns"""
        print("\\nAnalyzing gap detection performance...")
        
        results = {}
        
        for algorithm in self.algorithms:
            if algorithm not in self.data or not self.data[algorithm]:
                continue
                
            data = self.data[algorithm]
            total_records = len(data)
            
            # Count successful gap detections (not NaN)
            successful_detections = sum(1 for record in data 
                                     if record.get('gap_center_deg') is not None)
            
            # Calculate detection rate
            detection_rate = successful_detections / total_records if total_records > 0 else 0
            
            # Analyze gap sizes when detected
            gap_widths = [record['gap_width_m'] for record in data 
                         if record.get('gap_width_m') is not None]
            
            # Analyze largest area fractions
            area_fractions = [record['largest_area_frac'] for record in data 
                            if record.get('largest_area_frac') is not None]
            
            results[algorithm] = {
                'total_records': total_records,
                'successful_detections': successful_detections,
                'detection_rate': detection_rate,
                'avg_gap_width': statistics.mean(gap_widths) if gap_widths else 0,
                'avg_area_fraction': statistics.mean(area_fractions) if area_fractions else 0,
                'max_area_fraction': max(area_fractions) if area_fractions else 0,
                'gap_width_variance': statistics.variance(gap_widths) if len(gap_widths) > 1 else 0
            }
            
            print(f"  {algorithm.upper()}:")
            print(f"    Detection Rate: {detection_rate:.2%}")
            print(f"    Avg Gap Width: {results[algorithm]['avg_gap_width']:.2f}m")
            print(f"    Avg Area Fraction: {results[algorithm]['avg_area_fraction']:.3f}")
        
        self.analysis_results['gap_detection'] = results
        return results
    
    def analyze_processing_performance(self) -> Dict:
        """Analyze processing speed and timing patterns"""
        print("\\nAnalyzing processing performance...")
        
        results = {}
        
        for algorithm in self.algorithms:
            if algorithm not in self.data or not self.data[algorithm]:
                continue
                
            data = self.data[algorithm]
            
            # Calculate processing frequency from timestamps
            timestamps = [float(record['t']) for record in data if record.get('t')]
            
            if len(timestamps) > 1:
                # Calculate time differences
                time_diffs = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                avg_interval = statistics.mean(time_diffs)
                processing_fps = 1.0 / avg_interval if avg_interval > 0 else 0
                
                results[algorithm] = {
                    'avg_processing_interval': avg_interval,
                    'processing_fps': processing_fps,
                    'total_duration': timestamps[-1] - timestamps[0],
                    'consistency': statistics.stdev(time_diffs) if len(time_diffs) > 1 else 0
                }
                
                print(f"  {algorithm.upper()}:")
                print(f"    Processing FPS: {processing_fps:.1f}")
                print(f"    Avg Interval: {avg_interval:.3f}s")
                print(f"    Consistency (stdev): {results[algorithm]['consistency']:.3f}s")
        
        self.analysis_results['processing'] = results
        return results
    
    def identify_failure_patterns(self) -> Dict:
        """Identify patterns in detection failures"""
        print("\\nIdentifying failure patterns...")
        
        results = {}
        
        for algorithm in self.algorithms:
            if algorithm not in self.data or not self.data[algorithm]:
                continue
                
            data = self.data[algorithm]
            
            # Analyze conditions during failures
            failures = [record for record in data if record.get('gap_center_deg') is None]
            successes = [record for record in data if record.get('gap_center_deg') is not None]
            
            failure_analysis = {
                'failure_count': len(failures),
                'success_count': len(successes),
                'failure_rate': len(failures) / len(data) if data else 0
            }
            
            # Analyze area fractions during failures vs successes
            if failures and successes:
                failure_areas = [f['largest_area_frac'] for f in failures 
                               if f.get('largest_area_frac') is not None]
                success_areas = [s['largest_area_frac'] for s in successes 
                               if s.get('largest_area_frac') is not None]
                
                failure_analysis.update({
                    'avg_failure_area': statistics.mean(failure_areas) if failure_areas else 0,
                    'avg_success_area': statistics.mean(success_areas) if success_areas else 0,
                    'area_threshold_hypothesis': statistics.mean(success_areas) if success_areas else 0.5
                })
            
            results[algorithm] = failure_analysis
            
            print(f"  {algorithm.upper()}:")
            print(f"    Failure Rate: {failure_analysis['failure_rate']:.2%}")
            if 'avg_failure_area' in failure_analysis:
                print(f"    Avg Area During Failures: {failure_analysis['avg_failure_area']:.3f}")
                print(f"    Avg Area During Success: {failure_analysis['avg_success_area']:.3f}")
        
        self.analysis_results['failures'] = results
        return results
    
    def compare_algorithms(self) -> Dict:
        """Compare performance across different algorithms"""
        print("\\nComparing algorithm performance...")
        
        if 'gap_detection' not in self.analysis_results:
            self.analyze_gap_detection_performance()
        
        comparison = {}
        metrics = ['detection_rate', 'avg_gap_width', 'avg_area_fraction']
        
        for metric in metrics:
            comparison[metric] = {}
            values = []
            
            for algorithm in self.algorithms:
                if algorithm in self.analysis_results['gap_detection']:
                    value = self.analysis_results['gap_detection'][algorithm][metric]
                    comparison[metric][algorithm] = value
                    values.append((algorithm, value))
            
            # Rank algorithms for this metric
            if metric == 'detection_rate':
                values.sort(key=lambda x: x[1], reverse=True)  # Higher is better
            else:
                values.sort(key=lambda x: x[1], reverse=True)  # Higher is generally better
            
            comparison[metric]['ranking'] = values
            
            print(f"  {metric.replace('_', ' ').title()}:")
            for i, (alg, val) in enumerate(values):
                print(f"    {i+1}. {alg.upper()}: {val:.3f}")
        
        self.analysis_results['comparison'] = comparison
        return comparison
    
    def generate_optimization_recommendations(self) -> List[str]:
        """Generate specific optimization recommendations"""
        print("\\nGenerating optimization recommendations...")
        
        recommendations = []
        
        if 'gap_detection' in self.analysis_results:
            gap_results = self.analysis_results['gap_detection']
            
            # Find best performing algorithm
            best_algorithm = max(gap_results.keys(), 
                               key=lambda x: gap_results[x]['detection_rate'])
            best_rate = gap_results[best_algorithm]['detection_rate']
            
            recommendations.append(
                f"Primary Algorithm: Use '{best_algorithm}' as primary algorithm "
                f"(detection rate: {best_rate:.2%})"
            )
            
            # Check for low detection rates
            for algorithm, results in gap_results.items():
                if results['detection_rate'] < 0.5:
                    recommendations.append(
                        f"Critical Issue: {algorithm} has low detection rate "
                        f"({results['detection_rate']:.2%}) - needs immediate attention"
                    )
                elif results['detection_rate'] < 0.8:
                    recommendations.append(
                        f"Improvement Opportunity: {algorithm} detection rate "
                        f"({results['detection_rate']:.2%}) can be improved"
                    )
        
        if 'failures' in self.analysis_results:
            failure_results = self.analysis_results['failures']
            
            for algorithm, results in failure_results.items():
                if 'area_threshold_hypothesis' in results:
                    threshold = results['area_threshold_hypothesis']
                    recommendations.append(
                        f"Threshold Optimization: For {algorithm}, consider area threshold "
                        f"of {threshold:.3f} to reduce false negatives"
                    )
        
        if 'processing' in self.analysis_results:
            proc_results = self.analysis_results['processing']
            
            # Check processing speed
            for algorithm, results in proc_results.items():
                fps = results['processing_fps']
                if fps < 10:
                    recommendations.append(
                        f"Performance Issue: {algorithm} processing at {fps:.1f} FPS "
                        f"- consider optimization for real-time performance"
                    )
                elif fps > 30:
                    recommendations.append(
                        f"Good Performance: {algorithm} processing at {fps:.1f} FPS "
                        f"- sufficient for real-time operation"
                    )
        
        # General recommendations
        recommendations.extend([
            "Implement ensemble method: Combine multiple algorithms for better reliability",
            "Add confidence scoring: Implement confidence metrics for gap detections",
            "Real-time monitoring: Set up automated performance monitoring",
            "Adaptive thresholding: Implement dynamic threshold adjustment based on conditions"
        ])
        
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
        
        return recommendations
    
    def save_analysis_report(self, output_file: str = "segmentation_analysis_report.json"):
        """Save complete analysis report to JSON file"""
        report = {
            'analysis_timestamp': datetime.now().isoformat(),
            'data_summary': {
                algorithm: len(data) for algorithm, data in self.data.items()
            },
            'analysis_results': self.analysis_results,
            'recommendations': self.generate_optimization_recommendations()
        }
        
        output_path = self.logs_dir / output_file
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\\nAnalysis report saved to: {output_path}")
        return report

def main():
    """Run complete segmentation analysis"""
    print("LESNAR AI - SEGMENTATION PERFORMANCE ANALYSIS")
    print("=" * 50)
    
    analyzer = SegmentationAnalyzer()
    
    # Load data
    analyzer.load_segmentation_data()
    
    # Run analyses
    analyzer.analyze_gap_detection_performance()
    analyzer.analyze_processing_performance()
    analyzer.identify_failure_patterns()
    analyzer.compare_algorithms()
    
    # Generate recommendations
    print("\\n" + "=" * 50)
    print("OPTIMIZATION RECOMMENDATIONS")
    print("=" * 50)
    recommendations = analyzer.generate_optimization_recommendations()
    
    # Save report
    analyzer.save_analysis_report()
    
    print("\\n" + "=" * 50)
    print("NEXT STEPS")
    print("=" * 50)
    print("1. Review the analysis report")
    print("2. Implement recommended algorithm optimizations")
    print("3. Set up real-time performance monitoring")
    print("4. Test optimizations in simulation environment")
    print("5. Deploy improvements to production system")

if __name__ == "__main__":
    main()