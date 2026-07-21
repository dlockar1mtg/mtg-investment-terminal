from models.projections import scenario_cagrs

def test_bull_above_base():
    row = {"projection_confidence": 80}
    bear, base, bull, base_cap, bull_cap = scenario_cagrs(0.20, row)
    assert bear < base < bull
    assert base <= base_cap
    assert bull <= bull_cap
