# Dry-Run Configuration Guide

This guide explains the workflow control flags available in the GeoIP Custom IP Blocker. These flags enable selective execution of workflow steps for testing, validation, and staged deployments.

## Overview

The application supports four configurable boolean flags that control different stages of the workflow:

1. **ENABLE_GEODB_DOWNLOAD** - Control GeoIP database download
2. **ENABLE_NETWORK_SUMMARIZATION** - Control network aggregation
3. **CONFIGURE_DEFENSEPRO** - Control DefensePro device configuration
4. **FILTER_TARGET_REGIONS** - Control region filtering

## Workflow Stages

The complete workflow consists of these stages:

```
1. GeoIP Database Download
   ↓
2. Region Filtering (optional)
   ↓
3. CSV Export (original networks)
   ↓
4. Network Summarization (optional)
   ↓
5. CSV Export (summarized networks, if enabled)
   ↓
6. DefensePro Push (optional)
```

## Configuration Flags

### 1. ENABLE_GEODB_DOWNLOAD

Controls whether to download fresh GeoIP database from Radware API.

**Values:**
- `true` (default) - Download fresh database and process
- `false` - Use existing cached database only

**Use Cases:**
- Set to `false` when testing with existing cached data
- Set to `false` to avoid unnecessary downloads during development
- Set to `true` for production runs to ensure latest data

**Behavior:**
- When `true`: Downloads database from Radware API, validates MD5, processes data
- When `false`: Uses cached database from `data/geodb_cache/`, fails if no cache exists

**Example:**
```bash
ENABLE_GEODB_DOWNLOAD=false  # Use cached database
```

**Logs:**
```
⊘ GEODB DOWNLOAD DISABLED (ENABLE_GEODB_DOWNLOAD=false)
Using cached GeoIP database only
```

---

### 2. FILTER_TARGET_REGIONS

Controls whether to filter GeoIP data by target regions or load from CSV.

**Values:**
- `true` (default) - Filter GeoIP database by TARGET_COUNTRY and TARGET_REGIONS
- `false` - Skip filtering, load networks from existing CSV files

**Use Cases:**
- Set to `false` when testing with pre-exported CSV data
- Set to `false` to avoid re-processing large GeoIP databases
- Set to `true` for initial data extraction or when regions change

**Behavior:**
- When `true`: Processes GeoIP database and filters by configured regions
- When `false`: Always loads from `data/original_network_ranges.csv` from previous run
  - Then applies summarization based on `ENABLE_NETWORK_SUMMARIZATION` setting
  - If summarization enabled: original → summarized → push summarized networks
  - If summarization disabled: original → push original networks as-is

**Requirements:**
- When `false`, `data/original_network_ranges.csv` must exist from a previous run
- Fails with clear error if CSV file not found

**Example:**
```bash
FILTER_TARGET_REGIONS=false  # Load from CSV instead of processing GeoIP
```

**Logs:**
```
⊘ REGION FILTERING DISABLED (FILTER_TARGET_REGIONS=false)
Skipping GeoIP processing - will load from previous run's CSV files
Loading networks from: data/original_network_ranges.csv
```

---

### 3. ENABLE_NETWORK_SUMMARIZATION

Controls whether to aggregate network ranges using CIDR summarization.

**Values:**
- `true` (default) - Summarize networks to reduce count
- `false` - Use original filtered networks without summarization

**Use Cases:**
- Set to `false` when testing with full network lists
- Set to `false` to validate summarization results
- Set to `true` for production to optimize DefensePro performance

**Behavior:**
- When `true`: Aggregates networks (e.g., 760 networks → 87 networks)
- When `false`: Uses original networks as-is

**Impact:**
- Summarization can reduce network count by 80-90%
- Reduces DefensePro memory and processing overhead
- Exports both original and summarized CSVs for comparison

**Example:**
```bash
ENABLE_NETWORK_SUMMARIZATION=false  # Use original networks
```

**Logs:**
```
⊘ NETWORK SUMMARIZATION DISABLED (ENABLE_NETWORK_SUMMARIZATION=false)
Using original filtered networks without summarization
Will use 760 original networks
```

**CSV Exports:**
- Always exports: `data/original_network_ranges.csv`
- When enabled, also exports: `data/summarized_network_ranges.csv`
- Comparison report: `data/network_summarization_report.csv`

---

### 4. CONFIGURE_DEFENSEPRO

Controls whether to push configurations to DefensePro devices.

**Values:**
- `true` (default) - Connect to DefensePro and create configurations
- `false` - Skip DefensePro operations, only process data

**Use Cases:**
- Set to `false` for dry-run to validate data extraction
- Set to `false` when DefensePro devices are unavailable
- Set to `true` for production deployments

**Behavior:**
- When `true`: Connects to CyberController, creates network classes and blocklists
- When `false`: Processes data, exports CSVs, skips device operations

**Example:**
```bash
CONFIGURE_DEFENSEPRO=false  # Dry-run without pushing to devices
```

**Logs:**
```
⊘ DEFENSEPRO CONFIGURATION DISABLED (CONFIGURE_DEFENSEPRO=false)
Skipping DefensePro device configuration
Network ranges extracted and processed: 87 networks
CSV files exported for manual review in data/ directory
```

---

## Common Usage Scenarios

### Scenario 1: Full Production Run
```bash
ENABLE_GEODB_DOWNLOAD=true
FILTER_TARGET_REGIONS=true
ENABLE_NETWORK_SUMMARIZATION=true
CONFIGURE_DEFENSEPRO=true
```
**Result:** Complete workflow - download, filter, summarize, push to devices

---

### Scenario 2: Dry-Run Data Validation
```bash
ENABLE_GEODB_DOWNLOAD=true
FILTER_TARGET_REGIONS=true
ENABLE_NETWORK_SUMMARIZATION=true
CONFIGURE_DEFENSEPRO=false
```
**Result:** Process data and export CSVs without touching DefensePro devices

---

### Scenario 3: Test with Cached Data
```bash
ENABLE_GEODB_DOWNLOAD=false
FILTER_TARGET_REGIONS=true
ENABLE_NETWORK_SUMMARIZATION=true
CONFIGURE_DEFENSEPRO=false
```
**Result:** Use cached database, process and export, skip DefensePro

---

### Scenario 4: Test Without Summarization
```bash
ENABLE_GEODB_DOWNLOAD=true
FILTER_TARGET_REGIONS=true
ENABLE_NETWORK_SUMMARIZATION=false
CONFIGURE_DEFENSEPRO=false
```
**Result:** Process original networks without aggregation, export CSVs

---

### Scenario 5: Load from Pre-Exported CSV
```bash
ENABLE_GEODB_DOWNLOAD=false
FILTER_TARGET_REGIONS=false
ENABLE_NETWORK_SUMMARIZATION=true
CONFIGURE_DEFENSEPRO=false
```
**Result:** Load summarized networks from CSV, skip all processing
**Requires:** `data/summarized_network_ranges.csv` from previous run

---

### Scenario 6: Push Pre-Processed Data to Devices
```bash
ENABLE_GEODB_DOWNLOAD=false
FILTER_TARGET_REGIONS=false
ENABLE_NETWORK_SUMMARIZATION=true
CONFIGURE_DEFENSEPRO=true
```
**Result:** Load networks from CSV and push to DefensePro devices
**Requires:** `data/summarized_network_ranges.csv` from previous run

---

## Boolean Value Formats

All flags support multiple formats (case-insensitive):

```bash
# True values
ENABLE_GEODB_DOWNLOAD=true
ENABLE_GEODB_DOWNLOAD=True
ENABLE_GEODB_DOWNLOAD=TRUE
ENABLE_GEODB_DOWNLOAD=yes
ENABLE_GEODB_DOWNLOAD=1
ENABLE_GEODB_DOWNLOAD=on

# False values
ENABLE_GEODB_DOWNLOAD=false
ENABLE_GEODB_DOWNLOAD=False
ENABLE_GEODB_DOWNLOAD=FALSE
ENABLE_GEODB_DOWNLOAD=no
ENABLE_GEODB_DOWNLOAD=0
ENABLE_GEODB_DOWNLOAD=off
```

## Default Values

When not specified in `.env`, flags default to:
- `ENABLE_GEODB_DOWNLOAD=true`
- `FILTER_TARGET_REGIONS=true`
- `ENABLE_NETWORK_SUMMARIZATION=true`
- `CONFIGURE_DEFENSEPRO=true`

## Logging Behavior

Each disabled flag produces clear warning logs:

```
⊘ GEODB DOWNLOAD DISABLED (ENABLE_GEODB_DOWNLOAD=false)
⊘ REGION FILTERING DISABLED (FILTER_TARGET_REGIONS=false)
⊘ NETWORK SUMMARIZATION DISABLED (ENABLE_NETWORK_SUMMARIZATION=false)
⊘ DEFENSEPRO CONFIGURATION DISABLED (CONFIGURE_DEFENSEPRO=false)
```

## CSV Export Files

The workflow exports several CSV files for audit and reuse:

1. **data/original_network_ranges.csv** - Always exported when filtering enabled
   - Contains: All networks matching target regions before summarization
   - Format: `network_cidr,note`

2. **data/summarized_network_ranges.csv** - Exported when summarization enabled
   - Contains: Aggregated networks after CIDR summarization
   - Format: `network_cidr,note`

3. **data/network_summarization_report.csv** - Exported when summarization enabled
   - Contains: Comparison statistics (original count, summarized count, reduction %)
   - Format: `original_count,summarized_count,reduction_count,reduction_percentage`

4. **data/working_network_ranges.csv** - Exported when summarization disabled
   - Contains: Original networks marked as working set
   - Format: `network_cidr,note`

## File Selection Logic

When `FILTER_TARGET_REGIONS=false`, the application workflow is:

```
1. Always load from: data/original_network_ranges.csv
   ↓
2. Check ENABLE_NETWORK_SUMMARIZATION:
   ├─ true  → Summarize original networks → Push summarized networks
   └─ false → Use original networks as-is → Push original networks
```

**Key Points:**
- Only `original_network_ranges.csv` is required when `FILTER_TARGET_REGIONS=false`
- Summarization happens dynamically based on `ENABLE_NETWORK_SUMMARIZATION` setting
- This allows flexibility: load once, then decide whether to summarize or not

## Error Handling

### Missing CSV File
```
Error: Region filtering disabled but CSV file not found: data/original_network_ranges.csv
Enable FILTER_TARGET_REGIONS=true to process GeoIP database, or ensure CSV file exists from a previous run.
```

### Missing Cached Database
```
Error: GeoIP database download disabled but no cached database found
Enable ENABLE_GEODB_DOWNLOAD=true to download database
```

## Testing Recommendations

1. **Initial Setup**: Run with all flags `true` to validate full workflow
2. **Data Validation**: Set `CONFIGURE_DEFENSEPRO=false` to verify CSV exports
3. **Performance Testing**: Use `FILTER_TARGET_REGIONS=false` to test with pre-loaded data
4. **Summarization Testing**: Toggle `ENABLE_NETWORK_SUMMARIZATION` to compare results
5. **Production Deployment**: Enable all flags for complete workflow

## Configuration Examples

### Development .env
```bash
ENABLE_GEODB_DOWNLOAD=false         # Use cached data
FILTER_TARGET_REGIONS=true          # Process regions
ENABLE_NETWORK_SUMMARIZATION=true   # Aggregate networks
CONFIGURE_DEFENSEPRO=false          # Don't touch devices
```

### Testing .env
```bash
ENABLE_GEODB_DOWNLOAD=true          # Fresh data
FILTER_TARGET_REGIONS=true          # Process regions
ENABLE_NETWORK_SUMMARIZATION=true   # Aggregate networks
CONFIGURE_DEFENSEPRO=false          # Validate before pushing
```

### Production .env
```bash
ENABLE_GEODB_DOWNLOAD=true          # Fresh data
FILTER_TARGET_REGIONS=true          # Process regions
ENABLE_NETWORK_SUMMARIZATION=true   # Aggregate networks
CONFIGURE_DEFENSEPRO=true           # Push to devices
```

### Emergency Rollback .env
```bash
ENABLE_GEODB_DOWNLOAD=false         # Don't download
FILTER_TARGET_REGIONS=false         # Load from last good CSV
ENABLE_NETWORK_SUMMARIZATION=true   # Use summarized version
CONFIGURE_DEFENSEPRO=true           # Push to devices
```

## Troubleshooting

### Issue: Flag not taking effect
**Solution:** Ensure `.env` file is in the project root and contains no syntax errors

### Issue: CSV file not found
**Solution:** Run with `FILTER_TARGET_REGIONS=true` first to generate CSV files

### Issue: Cached database not found
**Solution:** Run with `ENABLE_GEODB_DOWNLOAD=true` first to download database

### Issue: All flags show as enabled
**Solution:** Check `.env` file is being loaded correctly, verify file permissions

## Related Documentation

- [README.md](../README.md) - Main project documentation
- [.env.example](../.env.example) - Configuration template
- [CONTRIBUTING.md](../CONTRIBUTING.md) - Development guidelines
