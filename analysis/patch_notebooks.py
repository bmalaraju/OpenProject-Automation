"""
Patch notebooks to add timezone handling for date parsing.
Run this script from the analysis folder.
"""
import json

def add_timezone_fix_to_sla():
    """Fix 01_sla_analysis.ipynb"""
    with open('01_sla_analysis.ipynb', 'r', encoding='utf-8') as f:
        nb = json.load(f)
    
    # Cell index 5 has the date parsing code
    for i, cell in enumerate(nb['cells']):
        if cell['cell_type'] == 'code':
            src = ''.join(cell['source'])
            if "analysis_df['target_date'] = pd.to_datetime" in src:
                cell['source'] = [
                    "# Parse dates and prepare analysis dataframe\n",
                    "analysis_df = df.copy()\n",
                    "\n",
                    "# Helper to strip timezone from dates\n",
                    "def parse_date(series):\n",
                    "    dt = pd.to_datetime(series, errors='coerce')\n",
                    "    if dt.dt.tz is not None:\n",
                    "        dt = dt.dt.tz_localize(None)\n",
                    "    return dt\n",
                    "\n",
                    "# Parse requested delivery date\n",
                    "analysis_df['target_date'] = parse_date(analysis_df[COLUMN_MAP['requested_date']])\n",
                    "\n",
                    "# Fallback to readiness date if requested date is missing\n",
                    "if COLUMN_MAP['readiness_date'] in analysis_df.columns:\n",
                    "    readiness = parse_date(analysis_df[COLUMN_MAP['readiness_date']])\n",
                    "    analysis_df['target_date'] = analysis_df['target_date'].fillna(readiness)\n",
                    "\n",
                    "# Parse added date for trend analysis\n",
                    "analysis_df['added_date'] = parse_date(analysis_df[COLUMN_MAP['added_date']])\n",
                    "\n",
                    "# Current date for SLA calculation\n",
                    "TODAY = pd.Timestamp.now().normalize()\n",
                    "\n",
                    "# Terminal statuses (orders that are complete and shouldn't count as breached)\n",
                    "TERMINAL_STATUSES = ['Approved', 'Cancelled', 'Rejected']\n",
                    "\n",
                    "# Calculate SLA metrics\n",
                    "analysis_df['is_terminal'] = analysis_df[COLUMN_MAP['status']].isin(TERMINAL_STATUSES)\n",
                    "analysis_df['has_target_date'] = analysis_df['target_date'].notna()\n",
                    "analysis_df['is_past_due'] = (analysis_df['target_date'] < TODAY) & analysis_df['has_target_date']\n",
                    "analysis_df['is_breached'] = analysis_df['is_past_due'] & ~analysis_df['is_terminal']\n",
                    "analysis_df['days_overdue'] = np.where(\n",
                    "    analysis_df['is_past_due'],\n",
                    "    (TODAY - analysis_df['target_date']).dt.days,\n",
                    "    0\n",
                    ")\n",
                    "\n",
                    "# At-risk: due within 7 days, not terminal\n",
                    "analysis_df['is_at_risk'] = (\n",
                    "    (analysis_df['target_date'] >= TODAY) & \n",
                    "    (analysis_df['target_date'] <= TODAY + timedelta(days=7)) &\n",
                    "    ~analysis_df['is_terminal'] &\n",
                    "    analysis_df['has_target_date']\n",
                    ")\n",
                    "\n",
                    "print(f\"✅ Data prepared successfully!\")\n",
                    "print(f\"\\n📅 Analysis date: {TODAY.strftime('%Y-%m-%d')}\")\n",
                    "print(f\"📊 Orders with target dates: {analysis_df['has_target_date'].sum():,}\")"
                ]
                print(f'  Fixed cell {i}')
                break
    
    with open('01_sla_analysis.ipynb', 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=4)
    print('  Saved 01_sla_analysis.ipynb')


def add_timezone_fix_to_processing():
    """Fix 05_processing_time_analysis.ipynb"""
    with open('05_processing_time_analysis.ipynb', 'r', encoding='utf-8') as f:
        nb = json.load(f)
    
    for i, cell in enumerate(nb['cells']):
        if cell['cell_type'] == 'code':
            src = ''.join(cell['source'])
            if "analysis_df[f'{key}_date'] = pd.to_datetime" in src:
                cell['source'] = [
                    "# Prepare analysis dataframe with parsed dates\n",
                    "analysis_df = df.copy()\n",
                    "\n",
                    "# Helper to strip timezone from dates\n",
                    "def parse_date(series):\n",
                    "    dt = pd.to_datetime(series, errors='coerce')\n",
                    "    if dt.dt.tz is not None:\n",
                    "        dt = dt.dt.tz_localize(None)\n",
                    "    return dt\n",
                    "\n",
                    "# Parse all date columns with timezone normalization\n",
                    "for key, col in DATE_COLUMNS.items():\n",
                    "    if col in analysis_df.columns:\n",
                    "        analysis_df[f'{key}_date'] = parse_date(analysis_df[col])\n",
                    "    else:\n",
                    "        analysis_df[f'{key}_date'] = pd.NaT\n",
                    "\n",
                    "# Parse STD (Standard Time in Days)\n",
                    "std_col = OTHER_COLUMNS.get('std')\n",
                    "if std_col and std_col in analysis_df.columns:\n",
                    "    analysis_df['std_days'] = pd.to_numeric(analysis_df[std_col], errors='coerce').fillna(0)\n",
                    "else:\n",
                    "    analysis_df['std_days'] = 0\n",
                    "\n",
                    "print(\"\\n✅ Dates parsed successfully!\")"
                ]
                print(f'  Fixed cell {i}')
                break
    
    with open('05_processing_time_analysis.ipynb', 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=4)
    print('  Saved 05_processing_time_analysis.ipynb')


if __name__ == '__main__':
    print('Patching notebooks with timezone fix...')
    print('\\n1. Fixing 01_sla_analysis.ipynb...')
    add_timezone_fix_to_sla()
    print('\\n2. Fixing 05_processing_time_analysis.ipynb...')
    add_timezone_fix_to_processing()
    print('\\n✅ All notebooks patched!')
