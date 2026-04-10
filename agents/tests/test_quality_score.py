import pytest
from datetime import datetime, timezone, timedelta


def make_repo(stars=50, forks=5, days_old=10, pushed_days_ago=3,
              description="An AI coding tool", topics=["llm"], license_name="MIT"):
    now = datetime.now(timezone.utc)
    return {
        "stargazers_count": stars,
        "forks_count": forks,
        "created_at": (now - timedelta(days=days_old)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pushed_at": (now - timedelta(days=pushed_days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "description": description,
        "topics": topics,
        "license": {"name": license_name} if license_name else None,
    }


def test_high_velocity_repo_scores_above_threshold():
    from sources import _quality_score
    repo = make_repo(stars=100, forks=15, days_old=5)
    assert _quality_score(repo) >= 0.4


def test_stale_no_description_repo_scores_below_threshold():
    from sources import _quality_score
    repo = make_repo(stars=5, forks=0, days_old=300, pushed_days_ago=200,
                     description="", topics=[], license_name=None)
    assert _quality_score(repo) < 0.4


def test_score_is_between_0_and_1():
    from sources import _quality_score
    repo = make_repo(stars=10000, forks=5000, days_old=1)
    assert 0.0 <= _quality_score(repo) <= 1.0


def test_score_increases_with_more_signals():
    from sources import _quality_score
    bare = make_repo(stars=20, forks=0, days_old=30, pushed_days_ago=20,
                     description="", topics=[], license_name=None)
    rich = make_repo(stars=20, forks=5, days_old=30, pushed_days_ago=5,
                     description="AI tool", topics=["llm"], license_name="MIT")
    assert _quality_score(rich) > _quality_score(bare)
