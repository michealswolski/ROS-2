import pytest

ament_flake8 = pytest.importorskip('ament_flake8.main')


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    rc, errors = ament_flake8.main_with_errors(argv=[])
    assert rc == 0, f'Found {len(errors)} code style errors / warnings:\n' + '\n'.join(errors)
