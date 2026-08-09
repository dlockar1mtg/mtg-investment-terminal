from scripts.audit_precollector_scope_governance import main


def test_precollector_scope_governance_and_mtg_standard_conformance(capsys):
    main()
    output = capsys.readouterr().out
    assert "PASS_PRECOLLECTOR_SCOPE_GOVERNANCE" in output
    assert "PASS_MTG_STANDARD_CONFORMANCE" in output
    assert "PASS_GITHUB_FIRST_WORKFLOW_CONTROL" in output
    assert "NEXT_STAGE_AUTHORIZED=CANDIDATE_UNIVERSE_INVENTORY_ONLY" in output
