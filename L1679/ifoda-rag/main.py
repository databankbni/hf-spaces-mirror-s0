"""
IFODA RAG System — Main entry point.
Usage:
    python main.py ingest    — Build the knowledge base
    python main.py query     — Interactive query mode
    python main.py eval      — Run accuracy evaluation
    python main.py server    — Start API server
    python main.py test      — Run test queries
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_ingest():
    """Build the vector database from IFODA documents."""
    from ingest import IFODAIngestor
    ingestor = IFODAIngestor()
    ingestor.run_full_ingestion()


def cmd_query():
    """Interactive query mode."""
    from query import interactive_cli
    interactive_cli()


def cmd_eval():
    """Run accuracy evaluation."""
    from evaluate import RAGEvaluator
    evaluator = RAGEvaluator()
    evaluator.run_full_eval()


def cmd_server():
    """Start API server."""
    from server import main as server_main
    server_main()


def cmd_test():
    """Run a few test queries without interactive mode."""
    from query import IFODAQueryEngine

    engine = IFODAQueryEngine(use_llm=False)

    test_queries = [
        "Какой инсектицид использовать против тли на хлопчатнике?",
        "Дозировка Далатэ для пшеницы",
        "What fungicide against powdery mildew on wheat?",
        "Удобрение для томатов в закрытом грунте",
        "Норма расхода SMARTFERT для хлопчатника",
    ]

    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"🔍 {q}")
        print(f"{'='*60}")
        result = engine.query(q)
        print(f"Confidence: {result.confidence}")
        print(f"Products: {', '.join(result.products_found[:5]) if result.products_found else 'none'}")
        print(f"Answer preview: {result.answer[:300]}...")
        if result.citations:
            print(f"Sources: {len(result.citations)}")


def print_usage():
    print("IFODA RAG System v1.0")
    print("Usage:")
    print("  python main.py ingest    — Build the knowledge base")
    print("  python main.py query     — Interactive query mode")
    print("  python main.py eval      — Run accuracy evaluation")
    print("  python main.py server    — Start API server (http://localhost:8000)")
    print("  python main.py test      — Run test queries")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    cmd = sys.argv[1].lower()

    commands = {
        "ingest": cmd_ingest,
        "query": cmd_query,
        "eval": cmd_eval,
        "server": cmd_server,
        "test": cmd_test,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print_usage()
        sys.exit(1)
