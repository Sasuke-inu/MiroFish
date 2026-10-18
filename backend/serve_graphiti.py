"""Graphiti's privacy opt-out must be set before importing its library."""
import os

os.environ['GRAPHITI_TELEMETRY_ENABLED'] = 'false'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['DO_NOT_TRACK'] = '1'
os.environ['OTEL_SDK_DISABLED'] = 'true'

from app.local_graph.server import main

if __name__ == '__main__':
    main()
