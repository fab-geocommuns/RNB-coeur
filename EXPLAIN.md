# EventDetail and BuildingEventDetail

## Why

The RNB (Référentiel National des Bâtiments) tracks changes to buildings over time through events. Each time a building is created, updated, merged, split, or deactivated, an event is recorded. However, the existing event tracking had limitations:

1. **No aggregated event metadata**: While each building record contains event information (event_id, event_type, event_origin, event_user_id), there was no centralized way to query events across multiple buildings or analyze events by geographic location.

2. **Missing change tracking**: The system stored versioned snapshots of buildings through `batid_building_history`, but didn't explicitly track what changed between versions. To understand what changed, you had to manually compare two versions.

3. **Analytics challenges**: Questions like "How many buildings were modified in Paris last month?" were difficult to answer. Getting the history of a building required on-the-fly computation for things that didn't change much.

EventDetail and BuildingEventDetail solve these problems by providing a dedicated, indexed structure for event metadata and change tracking.

## What

### EventDetail

A model that stores metadata about each unique event in the system:

- `event_id`: UUID identifying the event (one event can affect multiple buildings, e.g., in a merge)
- `event_type`: The type of event (creation, update, merge, split, deactivation)
- `event_origin`: JSON field describing where the event came from (API, admin interface, batch import, etc.)
- `city`: The city where the event occurred (based on building location)
- `department`: The department where the event occurred
- `user`: The user who triggered the event (nullable for system-generated events)

Key characteristics:
- One EventDetail per unique event_id (enforced by unique index)
- Indexed on event_id, city_id, department_id, and user_id for fast querying
- Enables geographic and user-based event analysis

### BuildingEventDetail

A model that stores the specific changes made to each building in an event:

- `event_id`: Links to the corresponding EventDetail
- `rnb_id`: The building identifier
- `changes`: JSON field containing a diff of what changed (field-by-field comparison)

Key characteristics:
- One record per (event_id, rnb_id) combination (enforced by unique constraint)
- The `changes` field contains only the fields that changed, formatted as: `{"field_name": [old_value, new_value]}`
- Tracks changes for: point, shape, ext_ids, is_active, addresses_id, status
- Raises if new columns are added and the trigger is not updated

## How

### Automatic Population via Trigger

The system uses PostgreSQL triggers to automatically populate these tables whenever a building is inserted or updated:

1. **Trigger**: `building_versioning_trigger_1_insert_or_update_event_detail_trigger`
   - Fires AFTER INSERT OR UPDATE on `batid_building`
   - Named to execute after the versioning trigger (ensuring history is written first)

2. **Main Function**: `insert_or_update_event_detail(building)`
   - Determines the city and department by finding where the building point intersects with geographic boundaries
   - Inserts or updates the EventDetail record (using ON CONFLICT for idempotency)
   - Computes the building changes using `compute_building_diff_from_last_version()`
   - Inserts the BuildingEventDetail record with the computed changes

3. **Diff Function**: `compute_building_diff_from_last_version(building)`
   - Fetches the most recent previous version from `batid_building_history`
   - Compares each tracked field (point, shape, ext_ids, is_active, addresses_id, status)
   - Returns a JSON object with only the changed fields in format: `{"field": [old, new]}`
   - Includes schema validation to ensure the function is updated when building columns change

### Caveats

- No test for now
- It duplicates much of the event attributes between `batid_building` and `batid_eventdetail`
- Stores only one city/department per event, even if a building overlaps multiple boundaries

### Backfilling

- Requires an estimated additional XXGb in the database
- Takes an estimated XX days to backfill 