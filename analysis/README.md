# WP Orders Analytics - Google Colab Notebooks

This folder contains Google Colab notebooks for comprehensive analysis of Work Package Order data.

## 📁 Notebooks

| # | Notebook | Purpose | Key Metrics |
|---|----------|---------|-------------|
| 1 | [01_sla_analysis.ipynb](./01_sla_analysis.ipynb) | SLA breach tracking | Breach %, Days overdue, At-risk orders |
| 2 | [02_order_status_metrics.ipynb](./02_order_status_metrics.ipynb) | Status distribution | Completion %, Approval rate, Pipeline |
| 3 | [03_volume_demand_analysis.ipynb](./03_volume_demand_analysis.ipynb) | Volume trends | Order trends, Product/Customer mix |
| 4 | [04_quality_satisfaction.ipynb](./04_quality_satisfaction.ipynb) | Quality metrics | On-time delivery, Satisfaction scores |
| 5 | [05_processing_time_analysis.ipynb](./05_processing_time_analysis.ipynb) | Efficiency | Cycle times, Bottlenecks, STD variance |
| 6 | [06_executive_dashboard.ipynb](./06_executive_dashboard.ipynb) | Monday presentations | All KPIs consolidated |

## 🚀 Quick Start

1. **Open in Colab**: Click on any notebook or upload to [Google Colab](https://colab.research.google.com/)
2. **Upload Data**: When prompted, upload your WP Orders Excel file (e.g., `11.25.WP Orders_25-11-2025_v01.xlsx`)
3. **Run All**: Execute all cells (`Runtime` → `Run all`)
4. **Export**: Download generated Excel reports

## 📊 Data Requirements

The notebooks expect Excel files with these columns:

| Column | Used In | Description |
|--------|---------|-------------|
| `WP Order ID` | All | Unique order identifier |
| `WP Order Status` | 1, 2, 6 | Status (8 values) |
| `WP Requested Delivery Date` | 1, 5, 6 | SLA target date |
| `Product` | All | Product category |
| `Customer` | 3, 6 | Customer name |
| `WP Quantity` | 2, 3, 6 | Ordered quantity |
| `WP Completed Qty` | 2, 6 | Completed quantity |
| `In-Time Delivery` | 4, 6 | On-time flag |
| `Added Date` | 3, 5 | Order creation date |
| `Acknowledged Date` | 5 | Acknowledgement date |
| `Submitted Date` | 5 | Submission date |
| `Approved Date` | 5 | Approval date |

## 📈 Status Values

| Status | Terminal? |
|--------|-----------|
| Pending Acknowledgement | No |
| Acknowledge | No |
| Waiting for order submission | No |
| Pending Approval | No |
| **Approved** | **Yes** |
| Objected | No |
| **Rejected** | **Yes** |
| **Cancelled** | **Yes** |

## 📅 Recommended Workflow

### For Monday Presentations:
1. Start with **06_executive_dashboard.ipynb** for KPI overview
2. Deep dive into specific areas using individual notebooks

### For Root Cause Analysis:
1. **01_sla_analysis.ipynb** → Identify SLA issues
2. **05_processing_time_analysis.ipynb** → Find bottlenecks
3. **04_quality_satisfaction.ipynb** → Check quality correlation

---

*Generated: December 2025*
