from models.projections import scenario_cagrs

def test_bull_above_base():
    row = {"projection_confidence": 80}
    bear, base, bull = scenario_cagrs(0.20, row)
    assert bear < base < bull
