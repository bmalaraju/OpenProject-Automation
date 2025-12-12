try:
    from influxdb_client_3 import InfluxDBClient3
    print("Imported InfluxDBClient3 class successfully")
except ImportError as e:
    print(f"Failed to import InfluxDBClient3 class: {e}")
except Exception as e:
    print(f"Error: {e}")
