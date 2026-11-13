"""Shared fixtures: card snapshots shaped like the ones the browser module captures.

The advertisers and copy are invented. The layout (line order, zero-width filler,
redirect links, video timer) mirrors real Ad Library cards.
"""
import pytest

REDIRECT = "https://l.facebook.com/l.php?u={}&h=AT0abc"


def make_card(library_id="1001", started="Started running on Jan 5, 2026", status="Active",
              advertiser="Northwind Desks", handle="northwinddesks",
              body=("Still working hunched over a laptop?", "Raise your desk in 3 seconds.",
                    "Rated 4.8/5 by 12,000 customers.", "\U0001F449 Order today with free shipping"),
              preview=("NORTHWIND.EXAMPLE", "Sit-stand desk, oak top", "Free 30-day returns", "Shop Now"),
              landing="https%3A%2F%2Fwww.northwind.example%2Fdesk%3Futm_source%3Dfb",
              extra_header=("This ad has multiple versions", "EU transparency"),
              details="See ad details", video=False):
    header = ["​", status, f"Library ID: {library_id}", started, "Platforms", "​",
              *extra_header, "Open Dropdown", "​", details]
    lines = [*header, advertiser, "Sponsored", *body]
    if video:
        lines.append("0:00 / 0:37")
    links = [{"href": f"https://www.facebook.com/{handle}/", "text": advertiser}]
    if preview:
        lines.extend(preview)
        links.append({"href": REDIRECT.format(landing), "text": "\n".join(preview)})
    return {
        "text": "\n".join(lines),
        "links": links,
        "images": ["https://scontent.example/avatar.jpg", "https://scontent.example/creative.jpg"],
        "videos": ["https://scontent.example/poster.jpg"] if video else [],
    }


@pytest.fixture
def card():
    return make_card()


@pytest.fixture
def cards():
    return [
        make_card(),
        make_card(library_id="1002", started="Started running on Mar 20, 2026",
                  advertiser="Caffè Aurora", handle="caffeaurora",
                  body=("Stanco del solito caffè?", "Scopri la miscela tostata a mano.",
                        "Soddisfatti o rimborsati."),
                  preview=("AURORA.EXAMPLE", "Miscela Aurora 1 kg", "Learn more"),
                  landing="https%3A%2F%2Faurora.example%2F",
                  extra_header=("2 ads use this creative and text",),
                  details="See summary details", video=True),
        make_card(library_id="1003", started="Started running on Feb 1, 2026"),  # same copy as 1001
    ]
