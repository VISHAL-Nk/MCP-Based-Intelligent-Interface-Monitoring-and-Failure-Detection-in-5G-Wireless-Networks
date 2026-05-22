#!/usr/bin/env bash

# WMN 5G Core Packet Capture Automation Script

set -e

NAMESPACE="open5gs"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== 5G Core Packet Capture Utility ===${NC}"

# Dynamic Pod Discovery
get_pod_name() {
    local label=$1
    local name=$(kubectl get pods -n "$NAMESPACE" -l "$label" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -z "$name" ]; then
        echo -e "${RED}Error: Could not find pod with label $label in namespace $NAMESPACE${NC}" >&2
        exit 1
    fi
    echo "$name"
}

# Menu for Capture Targets
echo -e "\nSelect traffic type to capture:"
echo "1) N1/N2 (NAS & SCTP Signaling) - Port 38412"
echo "2) N3 (GTP-U Data Plane) - Port 2152"
echo "3) N4 (PFCP Control/User Plane Association) - Port 8805"
echo "4) SBI (HTTP/2 Service-Based Interfaces) - Ports 80, 7777, 8080"
echo "5) Host/Bridge Level (Raw captures using netshoot)"
read -rp "Enter choice [1-5]: " TARGET_CHOICE

case $TARGET_CHOICE in
    1)
        POD_NAME=$(get_pod_name "app=open5gs,nf=amf")
        CONTAINER_NAME="amf"
        INTERFACE="any"
        FILTER="sctp or port 38412"
        DESC="N1_N2_SCTP_NAS_on_AMF"
        ;;
    2)
        POD_NAME=$(get_pod_name "app=open5gs,name=upf1,nf=upf")
        CONTAINER_NAME="upf"
        INTERFACE="n3"
        FILTER="udp port 2152"
        DESC="N3_GTPU_on_UPF1"
        ;;
    3)
        POD_NAME=$(get_pod_name "app=open5gs,name=upf1,nf=upf")
        CONTAINER_NAME="upf"
        INTERFACE="n4"
        FILTER="udp port 8805"
        DESC="N4_PFCP_on_UPF1"
        ;;
    4)
        POD_NAME=$(get_pod_name "app=open5gs,nf=amf")
        CONTAINER_NAME="amf"
        INTERFACE="eth0"
        FILTER="tcp port 80 or tcp port 7777 or tcp port 8080"
        DESC="SBI_HTTP2_on_AMF"
        ;;
    5)
        POD_NAME="netshoot"
        CONTAINER_NAME="netshoot"
        INTERFACE="any"
        FILTER=""
        DESC="Host_Bridge_Level_netshoot"
        
        # Verify netshoot pod is running
        if ! kubectl get pod netshoot -n "$NAMESPACE" &>/dev/null; then
            echo -e "${YELLOW}Warning: netshoot pod is not running. Deploying it now...${NC}"
            kubectl apply -f "$(dirname "$0")/netshoot-pod.yaml"
            echo "Waiting for netshoot pod to be ready..."
            kubectl wait --for=condition=Ready pod/netshoot -n "$NAMESPACE" --timeout=60s
        fi
        ;;
    *)
        echo -e "${RED}Invalid choice!${NC}"
        exit 1
        ;;
esac

echo -e "\nTarget identified: ${GREEN}$POD_NAME ($CONTAINER_NAME) on interface $INTERFACE${NC}"

# Menu for Output Modes
echo -e "\nSelect output mode:"
echo "1) Stream in real-time to local Wireshark GUI (Requires local X11 session)"
echo "2) Save capture to local PCAP file"
read -rp "Enter choice [1-2]: " OUTPUT_CHOICE

case $OUTPUT_CHOICE in
    1)
        if ! command -v wireshark &> /dev/null; then
            echo -e "${RED}Error: wireshark is not installed or not in PATH on this host!${NC}"
            exit 1
        fi
        echo -e "${GREEN}Streaming live traffic to Wireshark. Press Ctrl+C in terminal to stop capture.${NC}"
        kubectl exec -i "$POD_NAME" -n "$NAMESPACE" -c "$CONTAINER_NAME" -- tcpdump -i "$INTERFACE" $FILTER -U -w - | wireshark -k -i -
        ;;
    2)
        CAPTURE_DIR="$(dirname "$0")/captures"
        mkdir -p "$CAPTURE_DIR"
        FILE_NAME="${CAPTURE_DIR}/capture_${DESC}_$(date +%Y%m%d_%H%M%S).pcap"
        echo -e "${GREEN}Saving capture to file: $FILE_NAME${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop capture...${NC}"
        # Capture SIGINT to cleanly stop and notify
        trap 'echo -e "\n${GREEN}Capture stopped. Saved to $FILE_NAME${NC}"; exit 0' SIGINT
        kubectl exec -i "$POD_NAME" -n "$NAMESPACE" -c "$CONTAINER_NAME" -- tcpdump -i "$INTERFACE" $FILTER -U -w - > "$FILE_NAME"
        ;;
    *)
        echo -e "${RED}Invalid choice!${NC}"
        exit 1
        ;;
esac
