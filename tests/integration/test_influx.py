import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import pandas as pd
from wpr_agent.cli.upload_excel_to_influx import ingest_file

@pytest.fixture
def mock_influx_client():
    with patch("influxdb_client.InfluxDBClient") as mock:
        yield mock

@pytest.fixture
def sample_excel(tmp_path):
    # Create a sample Excel file
    df = pd.DataFrame({
        "BP ID": ["BP-1"],
        "WP Order ID": ["ORD-1"],
        "Product": ["Prod A"],
        "Project Name": ["Proj X"],
        "Domain": ["Dom 1"],
        "Customer": ["Cust Y"],
        "WP ID": ["WP-100"],
        "WP Name": ["Work Pkg 1"],
        "WP Quantity": [10],
        "WP Order Status": ["Approved"]
    })
    p = tmp_path / "test.xlsx"
    df.to_excel(p, index=False)
    return p

@patch("wpr_agent.cli.upload_excel_to_influx.InfluxStore")
@patch.dict("os.environ", {
    "INFLUX_URL": "http://localhost:8086",
    "INFLUX_TOKEN": "tok",
    "INFLUX_ORG": "org",
    "INFLUX_BUCKET": "buck"
})
def test_ingest_file(mock_store_cls, sample_excel, mock_influx_client):
    # Setup mocks
    mock_client_instance = mock_influx_client.return_value
    mock_write_api = mock_client_instance.write_api.return_value
    mock_query_api = mock_client_instance.query_api.return_value
    
    # Mock query response for verification
    mock_table = MagicMock()
    mock_record = MagicMock()
    mock_record.get_value.return_value = 1
    mock_table.records = [mock_record]
    mock_query_api.query.return_value = [mock_table]
    
    # Run ingestion
    res = ingest_file(sample_excel, batch_id="BATCH-1")
    
    # Verify
    assert res["ok"] is True
    assert res["rows"] == 1
    assert res["batch_id"] == "BATCH-1"
    
    # Verify write called
    mock_write_api.write.assert_called_once()
    call_args = mock_write_api.write.call_args
    assert call_args.kwargs["bucket"] == "buck"
    assert call_args.kwargs["org"] == "org"
    points = call_args.kwargs["record"]
    assert len(points) == 1
    
    # Verify store registration
    mock_store_instance = mock_store_cls.return_value
    mock_store_instance.register_ingestion_run.assert_called_once()
