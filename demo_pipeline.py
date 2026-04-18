#!/usr/bin/env python3
"""Demo script: Run the full LEC Phase 0 Bronze pipeline.

This demonstrates the end-to-end workflow:
1. Discovery (AACT demo mode)
2. Validation (4 MVP validators)
3. TruthCert generation
4. MetaEngine bridge
5. LEC object assembly
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lec.discovery.aact import AACTDiscovery
from lec.discovery.cochrane import Cochrane501Ranker
from lec.validators import run_all_validators
from lec.verification.truthcert import TruthCertGenerator
from lec.metaengine.bridge import MetaEngineBridge, run_simple_meta_analysis
from lec.assembly import LECBuilder
from lec.core import load_json, write_json


def main():
    """Run the full pipeline demo."""
    project_dir = Path(__file__).parent
    outputs_dir = project_dir / "outputs"
    data_dir = project_dir / "data"

    topic = "colchicine_mi"
    print(f"=== LEC Phase 0 Bronze Pipeline Demo ===")
    print(f"Topic: {topic}\n")

    # Step 1: Discovery (AACT)
    print("Step 1a: Running AACT discovery...")
    discovery = AACTDiscovery()  # Demo mode (no DB connection)
    sql_path = project_dir / "sql" / "colchicine_mi_candidates.sql"
    ctgov_output = discovery.run(topic, sql_path, outputs_dir / "ctgov")
    print(f"  -> AACT Candidates: {ctgov_output}")
    
    # Step 1b: Discovery (Europe PMC)
    print("Step 1b: Running Europe PMC discovery (Demo)...")
    from lec.discovery.europe_pmc import EuropePMCIndex
    epmc = EuropePMCIndex(outputs_dir / "epmc", demo_mode=True)
    epmc_output = epmc.run(topic, "colchicine myocardial infarction")
    print(f"  -> Europe PMC Candidates: {epmc_output}")
    
    # Step 1c: Linking
    print("Step 1c: Linking candidates...")
    from lec.linking.linker import Linker
    linker = Linker(outputs_dir / "linking")
    
    # Reload jsons to pass to linker
    ctgov_data = load_json(ctgov_output)
    epmc_data = load_json(epmc_output)
    
    linked_output = linker.link(ctgov_data, epmc_data, topic)
    print(f"  -> Linked Results: {linked_output}")

    # Step 2: Cochrane501 ranking
    print("\nStep 2: Running Cochrane501 ranking...")
    config_path = project_dir / "configs" / "discovery.yaml"
    ranker = Cochrane501Ranker(config_path)
    # Using AACT output for ranking as per original design, but could use linked
    discovery_output = ranker.rank(topic, ctgov_output, outputs_dir / "discovery")
    print(f"  -> Ranked discovery: {discovery_output}")

    # Step 3: Load sample extraction and validate
    print("\nStep 3: Running MVP validators...")
    extraction_path = data_dir / "sample_extraction.json"
    extraction_data = load_json(extraction_path)

    validation_report = run_all_validators(extraction_data)
    validation_path = outputs_dir / "validation" / "validation_report.json"
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(validation_path, validation_report)

    print(f"  -> Validators run: {validation_report['validators_run']}")
    print(f"  -> Summary: {validation_report['summary']}")

    # Step 4: Generate TruthCert
    print("\nStep 4: Generating TruthCert...")
    truthcert_gen = TruthCertGenerator(outputs_dir / "verification")
    truthcert_result = truthcert_gen.verify(extraction_path)
    print(f"  -> Decision: {truthcert_result['decision']}")
    print(f"  -> Certificate: {truthcert_result['certificate_path']}")

    # Step 5: MetaEngine bridge
    print("\nStep 5: Running MetaEngine bridge...")
    me_bridge = MetaEngineBridge(outputs_dir / "metaengine")
    me_input = me_bridge.prepare_input(extraction_data, topic)
    print(f"  -> MetaEngine input: {me_input['path']}")

    # Run simple meta-analysis (demo)
    me_input_data = load_json(Path(me_input["path"]))
    me_results = run_simple_meta_analysis(me_input_data["studies"])
    me_output_path = outputs_dir / "metaengine" / f"metaengine_output_{topic}.json"
    write_json(me_output_path, me_results)
    print(f"  -> MetaEngine output: {me_output_path}")
    print(f"  -> Pooled estimate: {me_results.get('pooled', {})}")
    print(f"  -> Heterogeneity I2: {me_results.get('heterogeneity', {}).get('i2')}%")

    # Step 6: Assemble LEC object
    print("\nStep 6: Assembling LEC object...")
    builder = LECBuilder(topic)
    builder.set_question(
        title="Colchicine for Secondary Prevention After Myocardial Infarction",
        population="Adults with recent myocardial infarction",
        intervention="Colchicine 0.5mg daily",
        comparator="Placebo",
        outcome="Major adverse cardiovascular events (MACE)",
        timeframe="Median 2 years follow-up",
        keywords=["colchicine", "STEMI", "NSTEMI", "cardiovascular", "anti-inflammatory"]
    )
    builder.add_discovery(discovery_output)
    builder.add_extraction(extraction_path)
    builder.add_metaengine(
        input_path=Path(me_input["path"]),
        output_path=me_output_path
    )
    builder.add_truthcert(
        Path(truthcert_result["certificate_path"]),
        Path(truthcert_result["audit_path"])
    )
    builder.set_analysis_results(me_results)

    lec_path = outputs_dir / "lec_objects" / f"{topic}.json"
    schema_path = project_dir / "schema" / "lec.schema.json"

    try:
        lec_output = builder.build(lec_path, schema_path)
        print(f"  -> LEC object: {lec_output}")
    except ValueError as e:
        print(f"  -> LEC validation warning: {e}")
        # Build without schema validation for demo
        lec_output = builder.build(lec_path)
        print(f"  -> LEC object (unvalidated): {lec_output}")

    # Step 7: Zenodo Pack
    print("\nStep 7: Creating Zenodo Package...")
    from lec.publishing.zenodo import ZenodoPacker
    packer = ZenodoPacker(outputs_dir / "packages")
    zip_path = packer.pack(lec_output)
    print(f"  -> Zenodo Package: {zip_path}")

    # Summary
    print("\n=== Pipeline Complete ===")
    print(f"Outputs written to: {outputs_dir}")
    print("\nArtifacts generated:")
    print(f"  - Discovery (AACT): {ctgov_output}")
    print(f"  - Discovery (EPMC): {epmc_output}")
    print(f"  - Linked: {linked_output}")
    print(f"  - Ranked: {discovery_output}")
    print(f"  - Validation: {validation_path}")
    print(f"  - TruthCert: {truthcert_result['certificate_path']}")
    print(f"  - MetaEngine: {me_output_path}")
    print(f"  - LEC Object: {lec_output}")
    print(f"  - Zenodo Zip: {zip_path}")

if __name__ == "__main__":
    main()
