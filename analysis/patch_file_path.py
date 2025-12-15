"""
Patch notebooks to use hardcoded file path instead of upload.
"""
import json
import os

FILE_PATH = r"C:\Users\bmalaraju\Documents\WP-OP Agent\JIRA-Agent\11.25.WP Orders_25-11-2025_v01.xlsx"

notebooks = [
    '01_sla_analysis.ipynb',
    '02_order_status_metrics.ipynb',
    '03_volume_demand_analysis.ipynb',
    '04_quality_satisfaction.ipynb',
    '05_processing_time_analysis.ipynb',
    '06_executive_dashboard.ipynb'
]

def patch_notebook(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        nb = json.load(f)
    
    for i, cell in enumerate(nb['cells']):
        if cell['cell_type'] == 'code':
            src = ''.join(cell['source'])
            
            # Update file path cell
            if 'File path - update this to match your file location' in src or 'filename = r"' in src:
                cell['source'] = [
                    f"# File path - update this to match your file location\n",
                    f"filename = r\"{FILE_PATH}\"\n",
                    f"print(f\"📁 Using file: {{filename}}\")"
                ]
                print(f'  Updated file path in cell {i}')
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=4)
    print(f'  Saved {filename}')


if __name__ == '__main__':
    print(f'Updating file path to: {FILE_PATH}\n')
    for nb in notebooks:
        if os.path.exists(nb):
            print(f'Updating {nb}...')
            patch_notebook(nb)
        else:
            print(f'Skipping {nb} (not found)')
    print('\n✅ All notebooks updated with new file path!')
