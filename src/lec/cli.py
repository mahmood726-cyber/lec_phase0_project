"""LEC Command Line Interface."""

import json
import sys
from pathlib import Path

import click

from lec import __version__
from lec.core import generate_run_id, load_json, write_json, ManifestWriter, utc_now_iso


@click.group()
@click.version_option(version=__version__)
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
@click.pass_context
def main(ctx, verbose):
    """LEC - Living Evidence Composite Pipeline (Phase 0 Bronze)"""
    ctx.ensure_object(dict)
    ctx.obj["outputs_dir"] = Path("outputs")
    
    if verbose:
        import logging
        logging.getLogger("lec").setLevel(logging.DEBUG)
        click.echo("Verbose logging enabled")


@main.command()
@click.option("--topic", required=True, help="Topic identifier (e.g., colchicine_mi)")
@click.option("--config", type=click.Path(exists=True), help="Config YAML file")
@click.option("--source", type=click.Path(exists=True), help="Source document for extraction")
@click.option("--skip-discovery", is_flag=True, help="Skip discovery step")
@click.pass_context
def run(ctx, topic, config, source, skip_discovery):
    """Run full LEC pipeline for a topic."""
    from lec.core import sanitize_filename
    
    safe_topic = sanitize_filename(topic)
    run_id = generate_run_id()
    click.echo(f"Starting LEC run: {run_id}")
    click.echo(f"Topic: {topic} (safe: {safe_topic})")

    # Use run-specific output directory
    base_outputs_dir = ctx.obj["outputs_dir"]
    outputs_dir = base_outputs_dir / run_id
    outputs_dir.mkdir(parents=True, exist_ok=True)
    
    # Save runtime configuration for reproducibility
    runtime_config = {
        "run_id": run_id,
        "topic": topic,
        "config_file": str(config) if config else None,
        "source_file": str(source) if source else None,
        "skip_discovery": skip_discovery,
        "timestamp": utc_now_iso(),
        "cli_version": __version__,
        "python_version": sys.version
    }
    write_json(outputs_dir / "run_config.json", runtime_config)
    
    data_dir = Path("data")
    
    # 1. Discovery
    discovery_output = None
    if not skip_discovery:
        from lec.discovery.aact import AACTDiscovery
        from lec.discovery.cochrane import Cochrane501Ranker
        
        click.echo("Step 1: Discovery...")
        discovery = AACTDiscovery()
        sql_path = Path("sql") / f"{safe_topic}_candidates.sql"
        if not sql_path.exists():
             sql_path = Path("sql") / "colchicine_mi_candidates.sql" # Fallback
             
        ctgov_output = discovery.run(safe_topic, sql_path, outputs_dir / "ctgov")
        
        # Check if we found anything
        ctgov_data = load_json(ctgov_output)
        candidate_count = ctgov_data.get("candidate_count", 0)
        if candidate_count == 0:
            click.echo("  -> No candidates found in AACT. Aborting pipeline.")
            return

        ranker = Cochrane501Ranker(Path(config) if config else None)
        discovery_output = ranker.rank(safe_topic, ctgov_output, outputs_dir / "discovery")
        click.echo(f"  -> Discovery artifacts: {discovery_output}")

    # 2. Extraction
    extraction_path = data_dir / "sample_extraction.json"
    if source:
        from lec.extraction.runner import run_extraction
        click.echo(f"Step 2: Extraction from {source}...")
        # For simplicity, we'll assume extraction output path
        extract_results = run_extraction(Path(source), ["rules", "llm"], outputs_dir / "extraction")
        # We'll use one of the outputs for next steps
        extraction_path = outputs_dir / "extraction" / f"extraction_rules_v1_{Path(source).stem}.json"

    # 3. Validation
    click.echo("Step 3: Validation...")
    from lec.validators import run_all_validators
    extraction_data = load_json(extraction_path)
    validation_report = run_all_validators(extraction_data)
    validation_path = outputs_dir / "validation" / f"report_{safe_topic}.json"
    write_json(validation_path, validation_report)
    click.echo(f"  -> Validation Status: {validation_report['summary']['passed']}/{validation_report['summary']['total']} passed")

    # 4. TruthCert
    click.echo("Step 4: TruthCert...")
    from lec.verification.truthcert import TruthCertGenerator
    truthcert_gen = TruthCertGenerator(outputs_dir / "verification")
    truthcert_result = truthcert_gen.verify(extraction_path)
    click.echo(f"  -> Decision: {truthcert_result['decision']}")

    # 5. MetaEngine
    click.echo("Step 5: MetaEngine Bridge & Advanced Stats...")
    from lec.metaengine.bridge import MetaEngineBridge, run_simple_meta_analysis
    from lec.metaengine.statistics import multivariate_sensitivity_analysis
    
    me_bridge = MetaEngineBridge(outputs_dir / "metaengine")
    me_input = me_bridge.prepare_input(extraction_data, safe_topic)
    
    # Run demo analysis
    me_input_data = load_json(Path(me_input["path"]))
    click.echo(f"  -> Running analysis on {len(me_input_data['studies'])} studies")
    
    me_results = run_simple_meta_analysis(me_input_data["studies"])
    me_output_path = outputs_dir / "metaengine" / f"metaengine_output_{safe_topic}.json"
    write_json(me_output_path, me_results)
    
    # Optional Sensitivity Analysis
    has_multiple_outcomes = any(len(s.get("outcomes", [])) > 1 for s in extraction_data.get("studies", []))
    if has_multiple_outcomes:
        click.echo("  -> Multiple outcomes detected; running multivariate sensitivity analysis...")
        # We'll just run it for the first study that has multiple for demo
        for study in extraction_data.get("studies", []):
            if len(study.get("outcomes", [])) > 1:
                # Prepare outcomes
                outcomes = []
                for o in study.get("outcomes", []):
                    e = o.get("effect", {})
                    if e.get("estimate"):
                        outcomes.append({"estimate": e["estimate"], "se": 0.1}) # Mock SE
                
                sens = multivariate_sensitivity_analysis(outcomes)
                click.echo(f"     [Sensitivity] Study {study.get('study_id')} rho=0.9 SE: {sens['sensitivity_results'][-1]['se']:.4f}")
                break

    # 6. Assembly
    click.echo("Step 6: LEC Object Assembly & Reporting...")
    from lec.assembly import LECBuilder
    from lec.reporting.summary_findings import SummaryFindingsGenerator
    
    builder = LECBuilder(safe_topic)
    if discovery_output:
        builder.add_discovery(discovery_output)
    builder.add_extraction(extraction_path)
    builder.add_metaengine(Path(me_input["path"]), me_output_path)
    builder.add_truthcert(Path(truthcert_result["certificate_path"]), Path(truthcert_result["audit_path"]))
    builder.set_analysis_results(me_results)
    
    lec_path = outputs_dir / "lec_objects" / f"{safe_topic}.json"
    builder.build(lec_path)
    click.echo(f"  -> LEC object built: {lec_path}")
    
    # Generate Summary Findings & PRISMA
    lec_data = load_json(lec_path)
    reporter = SummaryFindingsGenerator(lec_data)
    
    prisma_table = reporter.generate_prisma()
    sof_markdown = reporter.generate().to_markdown()
    
    report_path = outputs_dir / f"REPORT_{safe_topic}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# LEC Run Report: {topic}\n\n")
        f.write(prisma_table)
        f.write("\n\n")
        f.write(sof_markdown)
    
    click.echo(f"  -> Final Report generated: {report_path}")

    click.echo(f"\nRun complete: {run_id}")


@main.command()
@click.option("--extraction", type=click.Path(exists=True), required=True,
              help="Extraction JSON file(s) to verify")
@click.option("--output-dir", type=click.Path(), default="outputs/verification",
              help="Output directory for certificates")
@click.pass_context
def verify(ctx, extraction, output_dir):
    """Run verification pipeline and generate TruthCert."""
    from lec.verification.truthcert import TruthCertGenerator

    click.echo(f"Verifying extraction: {extraction}")

    extraction_path = Path(extraction)
    output_path = Path(output_dir)

    generator = TruthCertGenerator(output_path)
    result = generator.verify(extraction_path)

    click.echo(f"Decision: {result['decision']}")
    click.echo(f"Certificate: {result['certificate_path']}")
    click.echo(f"Audit log: {result['audit_path']}")


@main.command()
@click.option("--topic", required=True, help="Topic identifier")
@click.option("--discovery", type=click.Path(exists=True), help="Discovery JSON")
@click.option("--extraction", type=click.Path(exists=True), help="Extraction JSON")
@click.option("--metaengine", type=click.Path(exists=True), help="MetaEngine output JSON")
@click.option("--truthcert", type=click.Path(exists=True), help="TruthCert JSON")
@click.option("--output-dir", type=click.Path(), default="outputs/lec_objects",
              help="Output directory")
@click.pass_context
def build(ctx, topic, discovery, extraction, metaengine, truthcert, output_dir):
    """Build LEC object from verified components."""
    from lec.assembly import LECBuilder

    click.echo(f"Building LEC object for topic: {topic}")

    builder = LECBuilder(topic)
    if discovery:
        builder.add_discovery(Path(discovery))
    if extraction:
        builder.add_extraction(Path(extraction))
    if metaengine:
        builder.add_metaengine(Path(metaengine))
    if truthcert:
        builder.add_truthcert(Path(truthcert))

    output_path = Path(output_dir) / f"{topic}.json"
    lec_path = builder.build(output_path)
    click.echo(f"LEC object written to: {lec_path}")


@main.group()
def discovery():
    """Trial discovery commands."""
    pass


@discovery.command("aact")
@click.option("--topic", required=True, help="Topic identifier")
@click.option("--sql", type=click.Path(exists=True), help="SQL query file")
@click.option("--connection", envvar="AACT_CONNECTION", help="AACT connection string")
@click.option("--output-dir", type=click.Path(), default="outputs/ctgov",
              help="Output directory")
def discovery_aact(topic, sql, connection, output_dir):
    """Run AACT-based discovery for CT.gov trials."""
    from lec.discovery.aact import AACTDiscovery

    click.echo(f"Running AACT discovery for topic: {topic}")

    if sql:
        sql_path = Path(sql)
    else:
        sql_path = Path("sql") / f"{topic}_candidates.sql"

    discovery = AACTDiscovery(connection)
    output_path = discovery.run(topic, sql_path, Path(output_dir))
    click.echo(f"Candidates written to: {output_path}")


@discovery.command("cochrane")
@click.option("--topic", required=True, help="Topic identifier")
@click.option("--candidates", type=click.Path(exists=True), required=True,
              help="AACT candidates parquet file")
@click.option("--config", type=click.Path(exists=True), default="configs/discovery.yaml",
              help="Discovery config YAML")
@click.option("--output-dir", type=click.Path(), default="outputs/discovery",
              help="Output directory")
def discovery_cochrane(topic, candidates, config, output_dir):
    """Run Cochrane501 precision ranking on candidates."""
    from lec.discovery.cochrane import Cochrane501Ranker

    click.echo(f"Running Cochrane501 ranking for topic: {topic}")

    ranker = Cochrane501Ranker(Path(config))
    output_path = ranker.rank(topic, Path(candidates), Path(output_dir))
    click.echo(f"Ranked discovery written to: {output_path}")


@discovery.command("epmc")
@click.option("--topic", required=True, help="Topic identifier")
@click.option("--query", required=True, help="Search query")
@click.option("--limit", default=50, help="Max articles to process")
@click.option("--output-dir", type=click.Path(), default="outputs/epmc",
              help="Output directory")
def discovery_epmc(topic, query, limit, output_dir):
    """Run Europe PMC Open Access discovery."""
    from lec.discovery.europe_pmc import EuropePMCIndex

    click.echo(f"Searching Europe PMC for topic: {topic}")
    
    index = EuropePMCIndex(Path(output_dir))
    output_path = index.run(topic, query, limit)
    
    click.echo(f"Results written to: {output_path}")


@main.command()
@click.option("--topic", required=True, help="Topic identifier")
@click.option("--source-a", type=click.Path(exists=True), required=True,
              help="Primary candidate list (JSON)")
@click.option("--source-b", type=click.Path(exists=True), required=True,
              help="Secondary candidate list (JSON)")
@click.option("--output-dir", type=click.Path(), default="outputs/linking",
              help="Output directory")
def link(topic, source_a, source_b, output_dir):
    """Link candidates from two sources."""
    from lec.linking.linker import Linker
    from lec.core import load_json

    click.echo(f"Linking candidates for topic: {topic}")

    # Load sources
    data_a = load_json(Path(source_a))
    data_b = load_json(Path(source_b))

    linker = Linker(Path(output_dir))
    output_path = linker.link(data_a, data_b, topic)
    
    click.echo(f"Linked results written to: {output_path}")


@main.command()
@click.option("--lec-object", type=click.Path(exists=True), required=True,
              help="LEC object JSON to pack")
@click.option("--topic", help="Topic identifier (used for package name)")
@click.option("--methods", type=click.Path(exists=True), 
              help="Custom METHODS.md to include")
@click.option("--output-dir", type=click.Path(), default="outputs/packages",
              help="Output directory")
def pack(lec_object, topic, methods, output_dir):
    """Create Zenodo-ready package from LEC object."""
    from lec.publishing.zenodo import ZenodoPacker

    click.echo(f"Packing LEC object: {lec_object}")
    
    packer = ZenodoPacker(Path(output_dir))
    methods_path = Path(methods) if methods else None
    
    zip_path = packer.pack(Path(lec_object), methods_path, topic=topic)
    click.echo(f"Package created: {zip_path}")


@main.command()
@click.option("--input", "input_file", type=click.Path(exists=True), required=True,
              help="Extraction JSON to validate")
@click.option("--output-dir", type=click.Path(), default="outputs/validation",
              help="Output directory")
def validate(input_file, output_dir):
    """Run all 4 MVP validators on extraction."""
    from lec.validators import run_all_validators

    click.echo(f"Validating: {input_file}")

    input_path = Path(input_file)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    extraction_data = load_json(input_path)
    report = run_all_validators(extraction_data)

    report_path = output_path / "validation_report.json"
    write_json(report_path, report)

    click.echo(f"Validation report: {report_path}")
    click.echo(f"Passed: {report['summary']['passed']}/{report['summary']['total']}")


@main.command()
@click.option("--source", type=click.Path(exists=True), required=True,
              help="Source document (PDF/JSON)")
@click.option("--output-dir", type=click.Path(), default="outputs/extraction",
              help="Output directory")
@click.option("--agents", default="rules,llm", help="Comma-separated agent types")
def extract(source, output_dir, agents):
    """Run dual-agent extraction on source document."""
    from lec.extraction.runner import run_extraction

    click.echo(f"Extracting from: {source}")
    click.echo(f"Agents: {agents}")

    agent_list = [a.strip() for a in agents.split(",")]
    output_path = Path(output_dir)

    results = run_extraction(Path(source), agent_list, output_path)
    click.echo(f"Extractions written to: {output_path}")
    click.echo(f"Disagreements: {results.get('disagreement_count', 0)}")


if __name__ == "__main__":
    main()
