#!/usr/bin/env python3
"""
Standalone test script to verify realistic benchmarks are loading correctly.
This script can run without Firestore or other dependencies.
"""

import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Load benchmarks directly
benchmarks_path = os.path.join(os.path.dirname(__file__), 'data', 'task-time-benchmarks.json')
benchmarks_path = os.path.normpath(benchmarks_path)

with open(benchmarks_path, 'r') as f:
    data = json.load(f)

# Create a dictionary mapping taskId to benchmark data
benchmarks = {}
for benchmark in data.get('taskBenchmarks', []):
    benchmarks[benchmark['taskId']] = benchmark

# Task ID mappings
TASK_MAPPINGS = {
    "evaluation_completion": "evaluation_completion",
    "admin_review": "admin_review_filing",
    "problem_identification": "problem_identification",
    "test_generation": "test_question_generation",
    "coa_compliance_check": "coa_standards_compliance",
    "scenario_generation": "scenario_generation",
    "notification_check": "notification_check",
}

def get_time_savings(task_id_key):
    """Get time savings for a task type"""
    task_id = TASK_MAPPINGS.get(task_id_key, task_id_key)
    benchmark = benchmarks.get(task_id)
    if benchmark:
        return benchmark.get('timeSavingsMinutes', 0)
    return 0

def get_baseline_time(task_id_key):
    """Get baseline manual time for a task type"""
    task_id = TASK_MAPPINGS.get(task_id_key, task_id_key)
    benchmark = benchmarks.get(task_id)
    if benchmark and 'manualTime' in benchmark:
        return benchmark['manualTime'].get('averageMinutes', 0)
    return 0

def get_ai_assisted_time(task_id_key):
    """Get AI-assisted time for a task type"""
    task_id = TASK_MAPPINGS.get(task_id_key, task_id_key)
    benchmark = benchmarks.get(task_id)
    if benchmark and 'aiAssistedTime' in benchmark:
        return benchmark['aiAssistedTime'].get('averageMinutes', 0)
    return 0

print("\n" + "="*60)
print("🧪 Testing Realistic Benchmarks")
print("="*60)

# Test evaluation completion - should save 42 minutes
eval_savings = get_time_savings("evaluation_completion")
eval_baseline = get_baseline_time("evaluation_completion")
eval_ai = get_ai_assisted_time("evaluation_completion")
print(f"\n✅ Evaluation Completion:")
print(f"   Baseline: {eval_baseline:.1f} min manual")
print(f"   AI-assisted: {eval_ai:.1f} min")
print(f"   Time saved: {eval_savings:.1f} min ({eval_savings/60:.2f} hours)")
assert eval_savings == 42, f"Expected 42 minutes saved, got {eval_savings}"

# Test problem identification - should save 83 minutes
problem_savings = get_time_savings("problem_identification")
problem_baseline = get_baseline_time("problem_identification")
problem_ai = get_ai_assisted_time("problem_identification")
print(f"\n✅ Problem Identification:")
print(f"   Baseline: {problem_baseline:.1f} min manual")
print(f"   AI-assisted: {problem_ai:.1f} min")
print(f"   Time saved: {problem_savings:.1f} min ({problem_savings/60:.2f} hours)")
assert problem_savings == 83, f"Expected 83 minutes saved, got {problem_savings}"

# Test scenario generation - should save 128 minutes
scenario_savings = get_time_savings("scenario_generation")
scenario_baseline = get_baseline_time("scenario_generation")
scenario_ai = get_ai_assisted_time("scenario_generation")
print(f"\n✅ Scenario Generation:")
print(f"   Baseline: {scenario_baseline:.1f} min manual")
print(f"   AI-assisted: {scenario_ai:.1f} min")
print(f"   Time saved: {scenario_savings:.1f} min ({scenario_savings/60:.2f} hours)")
assert scenario_savings == 128, f"Expected 128 minutes saved, got {scenario_savings}"

# Test admin review - should save 23 minutes
admin_savings = get_time_savings("admin_review")
admin_baseline = get_baseline_time("admin_review")
admin_ai = get_ai_assisted_time("admin_review")
print(f"\n✅ Admin Review:")
print(f"   Baseline: {admin_baseline:.1f} min manual")
print(f"   AI-assisted: {admin_ai:.1f} min")
print(f"   Time saved: {admin_savings:.1f} min ({admin_savings/60:.2f} hours)")
assert admin_savings == 23, f"Expected 23 minutes saved, got {admin_savings}"

# Test COA compliance - should save 62 minutes
coa_savings = get_time_savings("coa_compliance_check")
coa_baseline = get_baseline_time("coa_compliance_check")
coa_ai = get_ai_assisted_time("coa_compliance_check")
print(f"\n✅ COA Compliance Check:")
print(f"   Baseline: {coa_baseline:.1f} min manual")
print(f"   AI-assisted: {coa_ai:.1f} min")
print(f"   Time saved: {coa_savings:.1f} min ({coa_savings/60:.2f} hours)")
assert coa_savings == 62, f"Expected 62 minutes saved, got {coa_savings}"

# Test notification check - should save 44 minutes
notification_savings = get_time_savings("notification_check")
notification_baseline = get_baseline_time("notification_check")
notification_ai = get_ai_assisted_time("notification_check")
print(f"\n✅ Notification Check:")
print(f"   Baseline: {notification_baseline:.1f} min manual")
print(f"   AI-assisted: {notification_ai:.1f} min")
print(f"   Time saved: {notification_savings:.1f} min ({notification_savings/60:.2f} hours)")
assert notification_savings == 44, f"Expected 44 minutes saved, got {notification_savings}"

print("\n" + "="*60)
print("✅ All realistic benchmarks loaded correctly!")
print(f"   - Evaluation completion: {eval_savings} min saved ({eval_savings/60:.2f} hours)")
print(f"   - Problem identification: {problem_savings} min saved ({problem_savings/60:.2f} hours)")
print(f"   - Scenario generation: {scenario_savings} min saved ({scenario_savings/60:.2f} hours)")
print(f"   - Admin review: {admin_savings} min saved ({admin_savings/60:.2f} hours)")
print(f"   - COA compliance: {coa_savings} min saved ({coa_savings/60:.2f} hours)")
print(f"   - Notification check: {notification_savings} min saved ({notification_savings/60:.2f} hours)")
print("="*60 + "\n")

print("📊 Summary Comparison (Old vs New):")
print("   Evaluation completion: 12 min → 42 min saved (3.5x increase)")
print("   Problem identification: 7 min → 83 min saved (11.9x increase)")
print("   Scenario generation: 27 min → 128 min saved (4.7x increase)")
print("   Admin review: 8 min → 23 min saved (2.9x increase)")
print("   COA compliance: 22 min → 62 min saved (2.8x increase)")
print("   Notification check: ~7 min → 44 min saved (6.3x increase)")

