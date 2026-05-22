#!/usr/bin/env bash
# WMN 5G Core Chaos Script - Restore NRF Failure
set -e
NAMESPACE="open5gs"
kubectl scale deployment open5gs-nrf -n $NAMESPACE --replicas=1

echo "NRF Service Registry restored."
