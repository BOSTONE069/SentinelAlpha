from app.services.fixtures import demo_bars
from app.services.indicators import compute_indicators


def test_indicator_pipeline_produces_finite_features():
    result = compute_indicators(demo_bars("AAPL"))

    assert result.sma20 > result.sma50
    assert 0 <= result.rsi14 <= 100
    assert result.atr14 > 0
    assert result.resistance >= result.support


def test_indicator_pipeline_requires_enough_context():
    try:
        compute_indicators(demo_bars("AAPL", count=20))
    except ValueError as error:
        assert "50 bars" in str(error)
    else:
        raise AssertionError("short market context should fail closed")
