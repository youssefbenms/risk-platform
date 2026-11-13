from src.collect.news_rss import extract_text, parse_rss

SAMPLE = """<?xml version="1.0"?><rss version="2.0"><channel><title>ECB</title>
<item><title> Press release A</title><link>https://www.ecb.europa.eu//press/pr/a.en.html</link>
<pubDate>Fri, 20 Mar 2026 15:00:00 +0100</pubDate></item>
<item><title>Sans lien</title></item>
</channel></rss>"""


def test_parse_rss():
    arts = parse_rss(SAMPLE)
    assert len(arts) == 1
    assert arts[0]["title"] == "Press release A"
    assert arts[0]["link"] == "https://www.ecb.europa.eu/press/pr/a.en.html"
    assert arts[0]["published_at"].hour == 14  # converti en UTC


def test_extract_text():
    html = "<html><body><nav>menu</nav><main><h1>Titre</h1><p>Texte  utile</p></main><script>x</script></body></html>"
    assert extract_text(html) == "Titre Texte utile"
