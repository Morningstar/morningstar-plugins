# Medalist Rating Analyzer Tools

## get_pillar_data_id

Query pillar rating input data and return matching data point IDs.

### Usage

```python
import sys
sys.path.insert(0, 'skills/medalist-rating-analyzer/tools')

from pillar_data_query import get_pillar_data_id

# Get Process pillar IDs for Active management type
active_process_ids = get_pillar_data_id("process", "active")
# Returns: ['ZS71V', 'ODA4H', 'MVD74', 'USMSQ', 'IRTWI', ...]

# Get People pillar IDs for Active management type  
active_people_ids = get_pillar_data_id("people", "active")
# Returns: ['A9SD3', 'E89P9', 'I4JKP', 'LGFDO', 'MYVT1', ...]

# Get Parent pillar IDs for Passive management type
# Note: Parent only has Passive/Active entries, which are returned for passive queries
passive_parent_ids = get_pillar_data_id("parent", "passive")
# Returns: ['CW7G7', 'DX37P', 'EO0U8', 'HXDS7', 'J25I9', ...]
```

### Parameters

- **pillar**: `Literal["parent", "people", "process"]`
  - The pillar type to query (case-insensitive)
  
- **manage_type**: `Literal["active", "passive"]`
  - The management type to filter by (case-insensitive)

### Returns

- `List[str]`: List of matching data point IDs

### Data Distribution

Based on the current `pillar_rating_input_data.xlsx`:

| Pillar  | Active | Passive |
|---------|--------|---------|
| Parent  | 0      | 8       |
| People  | 19     | 0       |
| Process | 14     | 35      |

**Total**: 76 data points

### Notes

- The tool automatically handles "Passive/Active" entries in the data, including them when querying for passive management type
- All IDs are cleaned (tabs and whitespace removed)
- Input parameters are case-insensitive
