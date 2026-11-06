"""One destination policy for public discovery and downloads."""

from urllib.parse import urlparse

OFFICIAL_DOMAINS = (
    "consumeraffairs.gov.in",
    "consumerhelpline.gov.in",
    "indiacode.nic.in",
    "egazette.gov.in",
    "sci.gov.in",
    "scr.sci.gov.in",
    "nalsa.gov.in",
    "e-jagriti.gov.in",
)
ALLOWED_HOSTS = (
    set(OFFICIAL_DOMAINS) | {f"www.{host}" for host in OFFICIAL_DOMAINS} | {"api.sci.gov.in"}
)
POLICY_VERSION = "official-consumer-v2"


def allowed_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (
            len(url) <= 2048
            and parsed.scheme == "https"
            and parsed.hostname in ALLOWED_HOSTS
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False
