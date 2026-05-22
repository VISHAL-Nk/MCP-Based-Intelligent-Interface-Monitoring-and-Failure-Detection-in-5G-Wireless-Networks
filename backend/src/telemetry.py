import os
import json
import requests
from typing import List, Dict, Any

PROMETHEUS_URL = "http://10.102.203.128:9090"
LOG_FILE_PATH = "/var/log/open5gs-monitoring/open5gs-parsed.log"
CAPTURES_DIR = "/home/vboxuser/Documents/WMN/k8s/monitoring/packet-capture/captures"

class TelemetryIngestor:
    def __init__(self, prom_url: str = PROMETHEUS_URL, log_path: str = LOG_FILE_PATH, captures_dir: str = CAPTURES_DIR):
        self.prom_url = prom_url
        self.log_path = log_path
        self.captures_dir = captures_dir

    def get_metrics(self) -> Dict[str, Any]:
        """Queries Prometheus for deployment readiness states."""
        metrics = {
            "amf_ready": 1,
            "upf1_ready": 1,
            "upf2_ready": 1,
            "nrf_ready": 1,
            "raw": {}
        }
        
        try:
            # Query for ready replicas of deployments in open5gs namespace
            query = 'kube_deployment_status_replicas_ready{namespace="open5gs"}'
            response = requests.get(f"{self.prom_url}/api/v1/query", params={"query": query}, timeout=3)
            if response.status_code == 200:
                data = response.json()
                results = data.get("data", {}).get("result", [])
                
                # Default all to 0 first if we find them in metrics, to show status correctly
                deployments_found = set()
                for item in results:
                    dep = item.get("metric", {}).get("deployment")
                    val = int(item.get("value", [0, "0"])[1])
                    deployments_found.add(dep)
                    
                    if dep == "open5gs-amf":
                        metrics["amf_ready"] = val
                    elif dep == "open5gs-upf1":
                        metrics["upf1_ready"] = val
                    elif dep == "open5gs-upf2":
                        metrics["upf2_ready"] = val
                    elif dep == "open5gs-nrf":
                        metrics["nrf_ready"] = val
                
                # Check for deployments that are scaled to 0 (so they might not return from replicas_ready query)
                spec_query = 'kube_deployment_spec_replicas{namespace="open5gs"}'
                spec_resp = requests.get(f"{self.prom_url}/api/v1/query", params={"query": spec_query}, timeout=3)
                if spec_resp.status_code == 200:
                    spec_data = spec_resp.json()
                    spec_results = spec_data.get("data", {}).get("result", [])
                    for item in spec_results:
                        dep = item.get("metric", {}).get("deployment")
                        val = int(item.get("value", [0, "0"])[1])
                        metrics["raw"][f"{dep}_spec_replicas"] = val
                        
                        # If spec is 0, then ready replicas is indeed 0
                        if val == 0:
                            if dep == "open5gs-amf":
                                metrics["amf_ready"] = 0
                            elif dep == "open5gs-upf1":
                                metrics["upf1_ready"] = 0
                            elif dep == "open5gs-upf2":
                                metrics["upf2_ready"] = 0
                            elif dep == "open5gs-nrf":
                                metrics["nrf_ready"] = 0
        except Exception as e:
            # Fallback/Log error but keep running
            metrics["error"] = str(e)
            
        return metrics

    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Reads the last N lines from Fluent Bit parsed log file."""
        logs = []
        if not os.path.exists(self.log_path):
            return logs
            
        try:
            with open(self.log_path, 'r') as f:
                # Efficiently read last N lines
                lines = f.readlines()
                last_lines = lines[-limit:] if len(lines) > limit else lines
                
                for line in last_lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        parsed_log = json.loads(line)
                        logs.append(parsed_log)
                    except json.JSONDecodeError:
                        # Fallback for plain text lines if any
                        logs.append({"raw_message": line})
        except Exception as e:
            logs.append({"error": str(e)})
            
        return logs

    def get_packet_captures(self) -> List[Dict[str, Any]]:
        """Scans captures directory for metadata on active/saved packet captures."""
        captures = []
        if not os.path.exists(self.captures_dir):
            return captures
            
        try:
            for file in os.listdir(self.captures_dir):
                if file.endswith(".pcap"):
                    full_path = os.path.join(self.captures_dir, file)
                    stat = os.stat(full_path)
                    captures.append({
                        "filename": file,
                        "size_bytes": stat.st_size,
                        "modified_timestamp": stat.st_mtime
                    })
            # Sort by modified time descending
            captures.sort(key=lambda x: x["modified_timestamp"], reverse=True)
        except Exception as e:
            captures.append({"error": str(e)})
            
        return captures
