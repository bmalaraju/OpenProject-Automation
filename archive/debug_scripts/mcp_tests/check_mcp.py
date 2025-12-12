try:
    import mcp
    print(f"mcp version: {mcp.__version__}")
    print(f"mcp file: {mcp.__file__}")
    import mcp.types
    print("mcp.types imported successfully")
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")
