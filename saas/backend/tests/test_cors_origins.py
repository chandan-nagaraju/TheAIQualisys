from app.cors_origins import KNOWN_SPA_ORIGINS, expand_cors_origins


def test_known_spa_origins_include_www_and_apex():
    expanded = expand_cors_origins(list(KNOWN_SPA_ORIGINS))
    assert "https://www.theaiqualisys.com" in expanded
    assert "https://theaiqualisys.com" in expanded


def test_expand_adds_www_from_apex_only():
    out = expand_cors_origins(["https://theaiqualisys.com"])
    assert out[0] == "https://theaiqualisys.com"
    assert "https://www.theaiqualisys.com" in out
