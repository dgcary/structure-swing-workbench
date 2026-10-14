from app.account.models import SourceKind


def test_source_priority():
    assert SourceKind.CONFIRMED_FILL.priority > SourceKind.SNAPSHOT.priority
