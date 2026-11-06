from app.config import Settings
from app.rag.discover import OFFICIAL_DOMAINS, discover


def test_official_discovery_uses_fixed_non_personal_topic_and_domain_filters(monkeypatch):
    captured = {}

    class FakeResponse:
        def model_dump(self, mode):
            assert mode == "json"
            return {
                "output": [
                    {
                        "action": {
                            "sources": [
                                {
                                    "url": "https://consumeraffairs.gov.in/example.pdf",
                                    "title": "Official rule",
                                },
                                {"url": "https://example.com/blog", "title": "Blog"},
                            ]
                        }
                    }
                ]
            }

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeOpenAI:
        def __init__(self, **_kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr("app.rag.discover.OpenAI", FakeOpenAI)
    settings = Settings(openai_api_key="labelled-test-key", openai_web_search_model="test-model")
    results = discover(settings, "consumer_procedure")
    assert results == [
        {"url": "https://consumeraffairs.gov.in/example.pdf", "title": "Official rule"}
    ]
    tool = captured["tools"][0]
    assert tool["type"] == "web_search"
    assert set(tool["filters"]["allowed_domains"]) == set(OFFICIAL_DOMAINS)
    assert captured["input"].startswith("Discover primary official Indian sources")
    assert "private" not in captured["input"].casefold()
