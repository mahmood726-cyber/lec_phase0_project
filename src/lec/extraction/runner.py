"""Extraction runner - orchestrates dual-agent extraction."""

from pathlib import Path

from lec.extraction.rules_agent import RulesExtractor
from lec.extraction.comparator import ExtractionComparator
from lec.core import write_json, utc_now_iso, get_logger

logger = get_logger("extraction.runner")


def run_extraction(source_path: Path, agents: list[str],
                   output_dir: Path) -> dict:
    """Run multi-agent extraction and comparison.

    Args:
        source_path: Path to source document
        agents: List of agent types to use (e.g., ["rules", "llm"])
        output_dir: Output directory for extraction results

    Returns:
        dict with extraction results and disagreement summary
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Starting extraction run for {source_path.name}")

    extractions = []
    agent_instances = []

    # Initialize agents
    for agent_type in agents:
        if agent_type == "rules":
            agent_instances.append(RulesExtractor())
        elif agent_type == "llm":
            # LLM agent would be implemented here
            # For Phase 0, we use a second rules profile
            agent = RulesExtractor()
            agent.agent_id = "rules_v2"  # Different profile
            agent_instances.append(agent)
        else:
            logger.error(f"Unknown agent type: {agent_type}")
            raise ValueError(f"Unknown agent type: {agent_type}")

    # Run each agent
    for agent in agent_instances:
        logger.info(f"Running agent: {agent.agent_id}")
        extraction = agent.extract(source_path)
        extractions.append(extraction)

        # Write individual extraction
        extraction_path = output_dir / f"extraction_{agent.agent_id}_{source_path.stem}.json"
        write_json(extraction_path, extraction)

    # Compare extractions if we have multiple
    disagreements = []
    if len(extractions) >= 2:
        logger.info("Running extraction comparison...")
        comparator = ExtractionComparator()
        comparison = comparator.compare(extractions[0], extractions[1])
        disagreements = comparison.get("disagreements", [])

        # Write comparison report
        comparison_path = output_dir / f"disagreements_{source_path.stem}.json"
        write_json(comparison_path, comparison)
        logger.info(f"Found {len(disagreements)} disagreements ({sum(1 for d in disagreements if d.get('severity') == 'critical')} critical)")

    # Create summary
    result = {
        "source": str(source_path),
        "run_at": utc_now_iso(),
        "agents_run": [a.agent_id for a in agent_instances],
        "extraction_count": len(extractions),
        "disagreement_count": len(disagreements),
        "critical_disagreements": sum(
            1 for d in disagreements if d.get("severity") == "critical"
        ),
        "output_dir": str(output_dir)
    }

    return result
