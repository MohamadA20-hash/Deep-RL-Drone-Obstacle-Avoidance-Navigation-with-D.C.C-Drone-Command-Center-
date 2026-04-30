"""
Test NavRL City Planner - A* + NavRL in AirSim City
=====================================================
Tests the global planner against pure hybrid controller to validate
that A* planning improves navigation in city environments.

Usage:
    python test_city_planner.py --test quick        # Quick single-goal test
    python test_city_planner.py --test compare      # Compare planner vs hybrid
    python test_city_planner.py --test mission      # Multi-waypoint city mission
    python test_city_planner.py --test all           # Run all tests
"""

import sys
import os
import time
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from navrl_city_planner import NavRLCityPlanner
from navrl_airsim_hybrid_controller import NavRLAirSimBridge, DEFAULT_FLIGHT_HEIGHT

import argparse


# ============================================================================
# TEST CONFIGURATIONS
# ============================================================================

# City navigation scenarios (longer distances, buildings in between)
CITY_GOALS = {
    'short': {
        'name': 'Short range (no planning needed)',
        'goal': [30, 20],
        'description': 'Close goal, NavRL should reach without A*',
    },
    'medium': {
        'name': 'Medium range (may need planning)',
        'goal': [80, 40],
        'description': 'Building may block direct path',
    },
    'long': {
        'name': 'Long range (likely needs planning)',
        'goal': [150, -30],
        'description': 'Must navigate around multiple buildings',
    },
    'behind_building': {
        'name': 'Goal behind building',
        'goal': [60, 0],
        'description': 'Requires going around obstacle',
    },
}

CITY_MISSION_WAYPOINTS = [
    [50, 30],
    [100, 0],
    [80, -50],
    [30, -30],
]


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

def test_quick(min_altitude: float = 5.0):
    """Quick test: navigate to a single goal with city planner."""
    print("\n" + "="*70)
    print("🧪 QUICK TEST: Single goal with A* planner + reactive altitude")
    print("="*70)
    
    planner = NavRLCityPlanner()
    goal = np.array([80, 40])
    
    result = planner.navigate_to_goal(goal, timeout=120, min_altitude=min_altitude)
    
    print(f"\nResult: {'PASS' if result['success'] else 'FAIL'}")
    return result


def test_compare(min_altitude: float = 5.0):
    """
    Compare city planner (A* + NavRL) vs hybrid controller (NavRL only).
    
    This is the key academic comparison:
    - Hybrid: NavRL + reactive altitude (reactive only, 4m vision)
    - City: A* global planning + NavRL local + reactive altitude
    """
    print("\n" + "="*70)
    print("🧪 COMPARISON TEST: City Planner vs Hybrid Controller")
    print("="*70)
    
    altitude_ned = -abs(min_altitude)  # NED for hybrid controller
    results = {}
    
    for scenario_key in ['short', 'medium', 'long']:
        scenario = CITY_GOALS[scenario_key]
        goal = np.array(scenario['goal'])
        
        print(f"\n{'='*60}")
        print(f"📍 Scenario: {scenario['name']}")
        print(f"   Goal: [{goal[0]}, {goal[1]}]")
        print(f"   {scenario['description']}")
        print('='*60)
        
        # --- Test 1: Hybrid Controller (no global planning) ---
        print(f"\n--- Hybrid Controller (reactive only) ---")
        try:
            hybrid = NavRLAirSimBridge()
            hybrid_result = hybrid.navigate_to_goal(
                np.array([goal[0], goal[1], altitude_ned]),
                timeout=90,
                target_altitude=altitude_ned
            )
        except Exception as e:
            print(f"   Error: {e}")
            hybrid_result = {'success': False, 'time': 0, 'path_length': 0}
        
        time.sleep(2)  # Brief pause between tests
        
        # --- Test 2: City Planner (A* + NavRL + reactive altitude) ---
        print(f"\n--- City Planner (A* + NavRL + Reactive Alt) ---")
        try:
            planner = NavRLCityPlanner()
            planner_result = planner.navigate_to_goal(
                goal, timeout=120, min_altitude=min_altitude
            )
        except Exception as e:
            print(f"   Error: {e}")
            planner_result = {'success': False, 'time': 0, 'path_length': 0}
        
        results[scenario_key] = {
            'scenario': scenario['name'],
            'hybrid': hybrid_result,
            'planner': planner_result,
        }
        
        time.sleep(2)
    
    # Print comparison
    print("\n" + "="*70)
    print("📊 COMPARISON RESULTS")
    print("="*70)
    print(f"{'Scenario':<25} {'Hybrid':^20} {'City Planner':^20}")
    print(f"{'':25} {'Success Time':^20} {'Success Time':^20}")
    print("-"*70)
    
    for key, data in results.items():
        h = data['hybrid']
        p = data['planner']
        h_str = f"{'✅' if h.get('success') else '❌'} {h.get('time', 0):.1f}s"
        p_str = f"{'✅' if p.get('success') else '❌'} {p.get('time', 0):.1f}s"
        print(f"{data['scenario']:<25} {h_str:^20} {p_str:^20}")
    
    print("="*70)
    
    # Save results
    save_path = os.path.join(os.path.dirname(__file__), 
                              'test_results_city_comparison.json')
    with open(save_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {save_path}")
    
    return results


def test_mission(min_altitude: float = 5.0):
    """Run multi-waypoint city mission."""
    print("\n" + "="*70)
    print("🧪 CITY MISSION TEST: Multi-waypoint navigation")
    print("="*70)
    
    planner = NavRLCityPlanner()
    result = planner.run_city_mission(
        CITY_MISSION_WAYPOINTS,
        return_to_base=True,
        min_altitude=min_altitude,
        timeout_per_wp=120
    )
    
    # Save results
    save_path = os.path.join(os.path.dirname(__file__), 
                              'test_results_city_mission.json')
    with open(save_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nResults saved to {save_path}")
    
    return result


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Test NavRL City Planner')
    parser.add_argument('--test', type=str, default='quick',
                       choices=['quick', 'compare', 'mission', 'all'],
                       help='Test to run')
    parser.add_argument('--min-altitude', type=float, default=5.0,
                       help='Minimum safe altitude in meters. Drone starts here '
                            'and climbs reactively based on LiDAR.')
    
    args = parser.parse_args()
    min_alt = abs(args.min_altitude)
    
    if args.test == 'quick':
        test_quick(min_alt)
    elif args.test == 'compare':
        test_compare(min_alt)
    elif args.test == 'mission':
        test_mission(min_alt)
    elif args.test == 'all':
        print("Running all city planner tests...")
        test_quick(min_alt)
        test_compare(min_alt)
        test_mission(min_alt)


if __name__ == "__main__":
    main()
