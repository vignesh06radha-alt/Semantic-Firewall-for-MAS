import argparse
import asyncio

from fastapi import FastAPI
from rich.console import Console

from protocols.a2a_schema import A2AMessage, A2AMetadata
from protocols.agent_cards import generate_agent_card
from firewall.sidecar_proxy import sidecar
from graph.workflow import lab_swarm_graph
from langchain_core.messages import HumanMessage
from evaluation.benchmark_runner import run_evaluation_suite

console = Console()
app = FastAPI(title="Semantic Firewall Protected Node")


async def execute_agent_pipeline(inoculated_text: str, cancel_token: asyncio.Event):
    """Primary agent executor. Periodically verifies cancel_token before tool actuation."""
    await asyncio.sleep(0.05)  # Pre-allocation / workspace loading simulation

    if cancel_token.is_set():
        raise asyncio.CancelledError("Execution halted by Kill Switch.")

    final_state = await lab_swarm_graph.ainvoke({
        "messages": [HumanMessage(content=inoculated_text)],
        "iteration_count": 0,
        "status": "continue",
    })
    return {"status": "success", "final_state": final_state}


@app.post("/a2a/ingress")
async def a2a_ingress_endpoint(message: A2AMessage):
    """Network entrypoint enforcing the zero-trust sidecar boundary."""
    success, response = await sidecar.intercept_and_race(
        envelope=message,
        agent_executor=execute_agent_pipeline
    )
    return response  # success=A2A result dict, failure=A2AError -- FastAPI serializes either


@app.get("/.well-known/agent-card.json")
async def agent_card_endpoint():
    return generate_agent_card(
        name="SemanticFirewallNode",
        description="MAS node protected by an out-of-band Inline Semantic Firewall.",
        endpoint="/a2a/ingress",
        methods=[{"name": "submit", "description": "Submit an A2A JSON-RPC task to the lab swarm."}],
    )


async def run_single_query():
    """--mode single: one interactive A2A query through the sidecar gateway."""
    console.print("[bold cyan]Inline Semantic Firewall -- interactive single query[/bold cyan]")
    content = input("Enter content to submit to the swarm: ").strip()
    if not content:
        console.print("[yellow]No input provided, aborting.[/yellow]")
        return

    msg = A2AMessage(
        sender="cli_user", recipient="atlas", method="submit",
        params={"content": content},
        metadata=A2AMetadata(originating_agent="cli_user"),
    )
    success, response = await sidecar.intercept_and_race(msg, execute_agent_pipeline)
    if success:
        console.print("[bold green]ALLOWED[/bold green]")
        console.print(response)
    else:
        console.print("[bold red]BLOCKED[/bold red]")
        console.print(response)


def main():
    parser = argparse.ArgumentParser(description="Inline Semantic Firewall for Multi-Agent Systems")
    parser.add_argument(
        "--mode", choices=["single", "benchmark", "serve"], default="serve",
        help="single: one interactive A2A query through the sidecar. "
             "benchmark: run the comparative evaluation sweep. "
             "serve: start the FastAPI ingress node (default)."
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if args.mode == "benchmark":
        asyncio.run(run_evaluation_suite())
    elif args.mode == "single":
        asyncio.run(run_single_query())
    else:
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
