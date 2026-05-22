#!/usr/bin/env bash

# WMN Chaos Engineering Orchestration Menu

set -e

DIR="$(dirname "$0")"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

show_status() {
    echo -e "\n\033[0;34m=== Current Network Chaos Status ===\033[0m"
    
    # 1. AMF Status
    AMF_REPLICAS=$(kubectl get deployment open5gs-amf -n open5gs -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    if [ "$AMF_REPLICAS" -gt 0 ]; then
        echo -e "AMF Status: \033[0;32mHealthy\033[0m ($AMF_REPLICAS/1 Ready)"
    else
        echo -e "AMF Status: \033[0;31mFailed/Unavailable\033[0m"
    fi

    # 2. UPF Status
    UPF1_REPLICAS=$(kubectl get deployment open5gs-upf1 -n open5gs -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    UPF2_REPLICAS=$(kubectl get deployment open5gs-upf2 -n open5gs -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    if [ "$UPF1_REPLICAS" -gt 0 ] && [ "$UPF2_REPLICAS" -gt 0 ]; then
        echo -e "UPF Status: \033[0;32mHealthy\033[0m (UPF1=$UPF1_REPLICAS, UPF2=$UPF2_REPLICAS)"
    else
        echo -e "UPF Status: \033[0;31mFailed/Unavailable\033[0m (UPF1=$UPF1_REPLICAS, UPF2=$UPF2_REPLICAS)"
    fi

    # 3. Network Delay
    GNB_POD=$(kubectl get pods -n open5gs -l app=ueransim,component=gnb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$GNB_POD" ]; then
        HAS_NETEM=$(kubectl exec -n open5gs "$GNB_POD" -c gnb -- tc qdisc show dev n3 2>/dev/null | grep netem || true)
        if [ -n "$HAS_NETEM" ]; then
            echo -e "Network Delay (gNB N3): \033[0;31mActive\033[0m ($HAS_NETEM)"
        else
            echo -e "Network Delay (gNB N3): \033[0;32mClean (No Delay/Loss)\033[0m"
        fi
    else
        echo -e "Network Delay (gNB N3): \033[1;33mUnknown (gNB Pod Not Found)\033[0m"
    fi

    # 4. N4 Block
    UPF1_POD=$(kubectl get pods -n open5gs -l app=open5gs,name=upf1,nf=upf -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ -n "$UPF1_POD" ]; then
        HAS_DROP=$(kubectl exec -n open5gs "$UPF1_POD" -c upf -- iptables -L INPUT -n 2>/dev/null | grep -E "dpt:8805.*DROP|DROP.*dpt:8805" || true)
        if [ -n "$HAS_DROP" ]; then
            echo -e "N4 PFCP Port 8805: \033[0;31mBlocked\033[0m"
        else
            echo -e "N4 PFCP Port 8805: \033[0;32mOpen\033[0m"
        fi
    else
        echo -e "N4 PFCP Port 8805: \033[1;33mUnknown (UPF1 Pod Not Found)\033[0m"
    fi

    # 5. NRF Status
    NRF_REPLICAS=$(kubectl get deployment open5gs-nrf -n open5gs -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    if [ "$NRF_REPLICAS" -gt 0 ]; then
        echo -e "NRF Status: \033[0;32mHealthy\033[0m ($NRF_REPLICAS/1 Ready)"
    else
        echo -e "NRF Status: \033[0;31mFailed/Unavailable\033[0m"
    fi
}

while true; do
    show_status
    echo -e "\n\033[0;34m=== Chaos Engineering Orchestrator ===\033[0m"
    echo "1) Inject AMF Pod Delete Failure"
    echo "2) Restore AMF Deployment"
    echo "3) Inject UPF Scale Down (Replicas=0) Failure"
    echo "4) Restore UPF Deployments"
    echo "5) Inject Network Chaos (200ms delay, 20% loss) on gNB N3 interface"
    echo "6) Restore Network Chaos on gNB"
    echo "7) Inject N4 (PFCP Port 8805) Drop Rule on UPF1"
    echo "8) Restore N4 (PFCP Port 8805) on UPF1"
    echo "9) Inject NRF Pod Delete Failure"
    echo "10) Restore NRF Deployment"
    echo "11) Restore ALL (Heal whole network)"
    echo "12) Exit"
    read -rp "Enter choice [1-12]: " CHOICE

    case $CHOICE in
        1) "$DIR/amf/inject.sh" ;;
        2) "$DIR/amf/restore.sh" ;;
        3) "$DIR/upf/inject.sh" ;;
        4) "$DIR/upf/restore.sh" ;;
        5) "$DIR/network/inject.sh" ;;
        6) "$DIR/network/restore.sh" ;;
        7) "$DIR/n4/inject.sh" ;;
        8) "$DIR/n4/restore.sh" ;;
        9) "$DIR/nrf/inject.sh" ;;
        10) "$DIR/nrf/restore.sh" ;;
        11)
            echo "Healing entire network..."
            "$DIR/amf/restore.sh" || true
            "$DIR/upf/restore.sh" || true
            "$DIR/network/restore.sh" || true
            "$DIR/n4/restore.sh" || true
            "$DIR/nrf/restore.sh" || true
            echo -e "\033[0;32mAll network components restored to healthy baseline.\033[0m"
            ;;
        12) exit 0 ;;
        *) echo -e "\033[0;31mInvalid choice!\033[0m" ;;
    esac
done
