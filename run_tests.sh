#!/bin/bash
# Script to run tests with proper PYTHONPATH

export PYTHONPATH="services/analytics:services/capital-allocator:services/opportunity-detector:services/position-manager:services/risk-manager:services/gateway:services/data-collector:services/execution-engine:services/funding-aggregator:services/notification:shared:$PYTHONPATH"

python -m pytest "$@"
