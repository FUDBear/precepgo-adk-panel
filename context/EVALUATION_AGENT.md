# Evaluations Agent Documentation

## Overview

The `EvaluationsAgent` is an independent agent responsible for generating realistic demo evaluation data for anesthesia preceptor evaluations. It creates fake evaluation documents that match the structure from `evaluation_example.text` and saves them to Firestore.

## Scoring System

## Evaluation Metrics

### AC Metrics (Anesthesia Competency)

**Field Names:** `ac_0` through `ac_12` (13 total fields)

**Score Range:** 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100

**Metric Definitions:**
- `ac_0`: **Procedural Room Readiness**
- `ac_1`: **Pre-op Assessment**
- `ac_2`: **Safely Transfers Care**
- `ac_3`: **Medication Administration**
- `ac_4`: **Regional Technique**
- `ac_5`: **Anesthesia Induction**
- `ac_6`: **Airway Management**
- `ac_7`: **Ventilatory Management**
- `ac_8`: **Procedure(s) Performed**
- `ac_9`: **Patient Positioning**
- `ac_10`: **Anesthetic Maintenance**
- `ac_11`: **Responds to Condition Changes**
- `ac_12`: **Emergence Technique**

**Scale Description:**
- **0** = Worst performance
- **100** = Best performance
- Scores are **increments of 10 only** (no intermediate values like 75, 85, etc.)

**Usage:**
- Each AC score represents a specific anesthesia competency metric
- Scores are selected randomly from valid ranges based on **class standing**:
  - **class_standing 1** (First year): 0-40 (beginner level)
  - **class_standing 2** (Second year): 40-80 (intermediate level)
  - **class_standing 3** (Third year): 80-100 (advanced level)
  - **class_standing 4** (Fourth year): 80-100 (expert level)
- Higher class standing = better expected scores
- When generating comments, the agent calculates average AC scores to determine overall performance level
- The agent uses these metric definitions to understand what skills were evaluated and can reference specific metrics in comments

### PC Scores (Preceptor Competency / Stars)

**Field Names:** `pc_0` through `pc_10` (11 total fields)

**Score Range:** -1, 0, 1, 2, 3, 4

**Metric Definitions:**
- `pc_0`: **Appropriate Intervention**
- `pc_1`: **Appropriate Pain Control**
- `pc_2`: **Receptive to Instruction**
- `pc_3`: **Communicated Effectively**
- `pc_4`: **Troubleshoots Effectively**
- `pc_5`: **Calm/Professional Demeanor**
- `pc_6`: **Recognizes Limitations**
- `pc_7`: **Professionalism and Integrity**
- `pc_8`: **Accountable for Care**
- `pc_9`: **Documentation Reflects Care**
- `pc_10`: **Follows Universal Precautions**

**Scale Description:**
- **-1** = **Student is dangerous** - Safety concerns, requires immediate remediation
- **0** = **Not applicable** - This metric doesn't apply to this case/student
- **1** = ⭐ (1 star) - Poor performance
- **2** = ⭐⭐ (2 stars) - Below average performance
- **3** = ⭐⭐⭐ (3 stars) - Satisfactory/average performance
- **4** = ⭐⭐⭐⭐ (4 stars) - Excellent performance

**Probability Distribution:**
- **0.2% chance per field** for `-1` (dangerous) - Results in approximately **2% of evaluations** having at least one dangerous flag (1 in 50 evaluations)
- **5-10% chance** for `0` (not applicable) - Some metrics may not apply to certain case types
- **~90% chance** for `3` (3 stars) - Most common rating for behavior-based metrics
- **~5% chance** for `4` (4 stars) - Excellent behavior
- **~3% chance** for `2` (2 stars) - Below average behavior
- **~2% chance** for `1` (1 star) - Poor behavior

**Usage:**
- PC scores represent **behavior-based** preceptor competency ratings (star ratings)
- **90% of applicable PC metrics should be 3 stars** (satisfactory behavior)
- Remaining metrics are mostly 4 stars (excellent), with occasional 1-2 stars (below average)
- When calculating averages, `-1` and `0` values are **excluded** from the average calculation
- If **any** PC score is `-1`, the performance level is automatically set to "dangerous" regardless of other scores
- Some metrics may be marked as `0` (not applicable) if they don't apply to the specific case type
- The agent uses these metric definitions to understand what behaviors were evaluated and can reference specific metrics in comments
- This ensures safety concerns are always flagged appropriately and behavior ratings reflect typical clinical performance

## Performance Level Determination

The agent determines performance level based on averaged scores **with adjusted expectations based on class standing**. Higher class standing students are evaluated more strictly, as they should be closer to independent practitioner level.

### Performance Thresholds by Class Standing

| Class Standing | Excellent | Good | Satisfactory | Needs Improvement | Poor |
|---------------|-----------|------|--------------|-------------------|------|
| **1 (Brand new)** | AC ≥ 85, PC ≥ 3.5 | AC ≥ 70, PC ≥ 3.0 | AC ≥ 50, PC ≥ 2.5 | AC ≥ 30 | AC < 30 |
| **2 (Building skills)** | AC ≥ 90, PC ≥ 3.5 | AC ≥ 80, PC ≥ 3.0 | AC ≥ 65, PC ≥ 2.5 | AC ≥ 45 | AC < 45 |
| **3 (Close to independent)** | AC ≥ 95, PC ≥ 3.7 | AC ≥ 85, PC ≥ 3.3 | AC ≥ 75, PC ≥ 3.0 | AC ≥ 60 | AC < 60 |
| **4 (Should be independent)** | AC ≥ 98, PC ≥ 3.8 | AC ≥ 90, PC ≥ 3.5 | AC ≥ 80, PC ≥ 3.2 | AC ≥ 70 | AC < 70 |

**Key Points:**
- **Class Standing 1**: Brand new to clinical rotations - more lenient evaluation, learning basics
- **Class Standing 2**: Building clinical skills - moderate expectations
- **Class Standing 3**: Close to independent practitioner - stricter evaluation, should demonstrate near-independent decision-making
- **Class Standing 4**: Should be independent practitioner - strictest evaluation, near graduation level

**Note:** PC average calculation excludes `-1` (dangerous) and `0` (not applicable) values. Any PC score of `-1` automatically sets performance level to "dangerous" regardless of other scores.

## Comment Generation

The agent generates realistic preceptor comments based on:

1. **Performance Level** - Determined from AC/PC averages with class-standing-adjusted thresholds
2. **Case Type** - Specific medical case from `cases.json`
3. **Case Keywords** - Keywords associated with the case
4. **Class Standing** - Student's year (1-4) - **affects evaluation strictness**
5. **Safety Flags** - If any PC score is -1
6. **Vector Search Research** - Case-specific anesthesia considerations from Barash Clinical Anesthesia

### Evaluation Strictness by Class Standing

- **Class Standing 1 (Brand new)**: More lenient, supportive evaluation - students are learning basics
- **Class Standing 2 (Building skills)**: Moderate expectations - should show progression
- **Class Standing 3 (Close to independent)**: Stricter evaluation - should demonstrate near-independent decision-making
- **Class Standing 4 (Should be independent)**: Strictest evaluation - near graduation, expected to manage cases independently

**Example:** A student with AC score of 80 might receive:
- **Class Standing 1**: "Good" performance (above 70 threshold)
- **Class Standing 2**: "Good" performance (meets 80 threshold)
- **Class Standing 3**: "Satisfactory" performance (below 85 threshold for "good")
- **Class Standing 4**: "Satisfactory" performance (below 90 threshold for "good")

### Comment Structure

Comments are built with multiple parts:

1. **Case Explanation** - Describes what the case involves and key anesthesia considerations
2. **Performance Description** - Explains how the student performed specifically during THIS case
3. **Case-Specific Details** - References specific aspects of the case that were relevant
4. **Metric References** - Mentions specific metrics where relevant (e.g., "Airway Management", "Medication Administration")
5. **Performance Level Context** - Appropriate for student's year level and expectations

### Focus Areas

The `focus_areas` field provides **actionable guidance for future learning and improvement**. These are areas the student should practice or learn more about for future clinical rotations.

**Purpose:**
- Helps students know what to practice/learn for future rotations
- Based on weak performance areas identified in the evaluation
- Provides specific, actionable guidance (not generic advice)
- Helps students avoid mistakes in future clinical rotations

**Generation:**
- Analyzes scores to identify weak areas (AC scores < 70, PC scores < 3 stars)
- Uses Vector Search to identify case-specific learning opportunities
- Generates 1-3 specific focus areas using AI or templates
- Focuses on practical skills that can be improved

**Example Focus Areas:**
- "Practice difficult airway management algorithms; Review hemodynamic monitoring for cardiac cases"
- "Improve medication dose calculations; Develop problem-solving skills for clinical scenarios"
- "Review preoperative assessment skills; Practice recognizing when to seek help"

### Safety Concerns

If any PC score is `-1` (dangerous):
- Comment includes prominent safety warning
- Performance level automatically set to "dangerous"
- Closing statement includes required remediation actions
- Overrides all other performance indicators

## Case Selection

- Cases are selected from `data/cases.json`
- Uses actual case names (not codes) for `case_type` field
- Example: `"ALIF with Posterior Fusion"` (not `"Case #5246521"`)
- Case selection considers case type for generating relevant comments

## Firestore Structure

### Default Storage Location
- **Collection:** `agent_evaluations` (top-level)
- **Document ID:** Auto-generated random string

### Alternative Storage (Subcollection)
- **Path:** `{parent_collection}/{parent_doc_id}/agent_evaluations/{doc_id}`
- Use `use_top_level_collection=False` in `save_evaluation_to_firestore()`

### Document Fields

All documents include:
- All AC scores (`ac_0` through `ac_12`)
- All PC scores (`pc_0` through `pc_10`)
- Metadata: `created_at`, `modified_at`, `created_by`
- Evaluation data: `case_type`, `comments`, `class_standing`, `app_version`, etc.
- User info: `preceptee_user_name`, `preceptor_name`, etc.
- Timestamps: `request_date`, `completion_date`
- Location: `geopoint` (random US coordinates)

## Usage Examples

### Basic Usage

```python
from agents.evaluations_agent import EvaluationsAgent

# Initialize agent
agent = EvaluationsAgent()

# Generate and save a demo evaluation
evaluation = agent.create_and_save_demo_evaluation()
```

### Custom Parameters

```python
# Generate evaluation with specific parameters
evaluation = agent.create_and_save_demo_evaluation(
    preceptee_name="John Doe",
    preceptor_name="Dr. Jane Smith",
    case_type="Cardiac Surgery",
    class_standing=2,
    app_version="0.1.32"
)
```

### Score Validation

```python
# Generate evaluation data
evaluation_data = agent.generate_demo_evaluation()

# Validate AC scores (should be 0, 10, 20, ..., 100)
ac_scores = [evaluation_data[f"ac_{i}"] for i in range(13)]
assert all(score in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100] for score in ac_scores)

# Validate PC scores (should be -1, 0, 1, 2, 3, or 4)
pc_scores = [evaluation_data[f"pc_{i}"] for i in range(11)]
assert all(score in [-1, 0, 1, 2, 3, 4] for score in pc_scores)
```

## Integration with main.py

The agent is integrated into the FastAPI dashboard:

- **Endpoint:** `POST /mentor/create-demo-evaluation`
- **Dashboard Button:** "Create Demo Evaluation"
- **Response:** Returns evaluation data with `firestore_doc_id`

## Important Notes

1. **AC Scores:** Always use increments of 10 (0, 10, 20, ..., 100)
2. **PC Scores:** Include special values -1 (dangerous) and 0 (not applicable)
3. **Safety First:** Any PC score of -1 triggers dangerous performance level
4. **Case Names:** Use actual case names from `cases.json`, not codes
5. **Comment Quality:** Comments are case-specific and performance-appropriate
6. **Probability:** Dangerous scores occur in approximately 2% of evaluations overall (1 in 50 evaluations) and are critical safety flags

## File Dependencies

- `data/cases.json` - Source of case data for `case_type` selection
- `data/evaluation_example.text` - Reference structure for evaluation documents
- `firestore_service.py` - Firestore connection utilities (optional)

## Agent Initialization

The agent requires:
- `FIREBASE_PROJECT_ID` or `GOOGLE_CLOUD_PROJECT` environment variable
- Valid Firestore credentials (Application Default Credentials or service account)
- `data/cases.json` file in the project root

If Firestore is unavailable, the agent will initialize but cannot save evaluations.

