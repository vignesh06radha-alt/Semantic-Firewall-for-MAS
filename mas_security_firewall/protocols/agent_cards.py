def generate_agent_card(name: str, description: str, endpoint: str, methods: list[dict]) -> dict:
    return {
        "$schema": "https://a2a.dev/v1/agent-card.json",
        "name": name,
        "description": description,
        "url": endpoint,
        "version": "1.0.0",
        "capabilities": methods,
        "security": {
            "sidecar_ingress_inspection": True,
            "protocol_support": ["JSON-RPC-2.0"]
        }
    }
