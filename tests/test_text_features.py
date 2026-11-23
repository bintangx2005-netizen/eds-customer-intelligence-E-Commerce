import pytest

from etl.text_features import NO_COMMENT, analyze


@pytest.mark.parametrize(
    "text, sentiment, topics",
    [
        ("Ótimo produto, chegou antes do prazo, recomendo", "positif", {"pengiriman"}),
        ("Produto não chegou no prazo, entrega muito demorada", "negatif", {"pengiriman"}),
        ("Produto diferente do anúncio, embalagem amassada", "negatif", {"tidak_sesuai", "kemasan"}),
        ("Vendedor não responde.\nEntrega atrasou e veio quebrado", "negatif",
         {"layanan", "pengiriman", "kualitas"}),
        ("não recomendo", "negatif", set()),
        ("Recomendo muito", "positif", set()),
        ("ok", "netral", set()),
    ],
)
def test_portuguese_examples(text, sentiment, topics):
    result = analyze(text)
    assert result.sentiment == sentiment
    assert result.topics == topics


@pytest.mark.parametrize("text", [None, "", "   ", "!!!"])
def test_empty_or_blank_comment_is_tanpa_komentar(text):
    result = analyze(text)
    assert result.sentiment == NO_COMMENT and result.topics == frozenset()
