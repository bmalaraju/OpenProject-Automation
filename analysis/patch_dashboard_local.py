"""
Script to patch the comprehensive dashboard to work better locally
"""
import json

with open('00_comprehensive_dashboard.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Find and fix the first code cell (remove !pip install)
for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        src = ''.join(cell['source'])
        
        # Cell with !pip install
        if '!pip install pandas openpyxl plotly kaleido -q' in src:
            # Make pip install optional
            cell['source'] = [
                "# Install required packages (for Colab, uncomment if needed)\n",
                "# !pip install pandas openpyxl plotly kaleido -q\n",
                "\n",
                "import pandas as pd\n",
                "import numpy as np\n",
                "from datetime import datetime, timedelta\n",
                "import plotly.graph_objects as go\n",
                "from plotly.subplots import make_subplots\n",
                "import plotly.express as px\n",
                "\n",
                "pd.set_option('display.max_columns', None)\n",
                "print(\"✅ Libraries loaded!\")\n",
                "print(f\"📅 Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\")"
            ]
            print(f"Fixed cell {i} - Made pip install optional")
            break

with open('00_comprehensive_dashboard.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=4)

print("\n✅ Notebook patched!")
print("The !pip install line is now commented out for local use.")
print("Uncomment it if running in Google Colab.")
