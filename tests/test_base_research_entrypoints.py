from pathlib import Path

from scripts.server.evaluate_and_infer import model_cells

ROOT = Path(__file__).resolve().parents[1]


def test_model_cells_preserve_small_default_identities() -> None:
    assert model_cells("small") == (
        ("small-zero-shot", "small", "zero_shot"),
        ("small-official-ft", "small", "official_style"),
        ("small-strict-pit", "small", "strict_pit"),
    )


def test_model_cells_define_exact_base_three_cell_candidate() -> None:
    assert model_cells("base") == (
        ("base-zero-shot", "base", "zero_shot"),
        ("base-official-ft", "base", "official_style"),
        ("base-strict-pit", "base", "strict_pit"),
    )


def test_base_is_pre_registered_in_both_training_protocols() -> None:
    small_official = (ROOT / "configs/models/official.yaml").read_text()
    small_strict = (ROOT / "configs/models/strict_pit.yaml").read_text()
    base_official = (ROOT / "configs/models/base_official.yaml").read_text()
    base_strict = (ROOT / "configs/models/base_strict_pit.yaml").read_text()
    assert "NeoQuasar/Kronos-base" not in small_official
    assert "models: [small]" in small_strict
    assert "NeoQuasar/Kronos-base" in base_official
    assert "models: [base]" in base_strict


def test_base_finalizer_is_immutable_catalog_only_and_never_promotes_current() -> None:
    script = (ROOT / "scripts/server/finalize_base_candidate.sh").read_text()
    assert '[[ ! -e "$target" ]]' in script
    assert "build_research_catalog.py" in script
    assert "publish_release.py" not in script
    assert "releases/current" not in script


def test_base_evaluation_resume_preserves_existing_matrix_and_never_promotes() -> None:
    script = (ROOT / "scripts/server/resume_base_evaluation.sh").read_text()
    assert '[[ -f "$MATRIX" ]]' in script
    assert "compile_training_matrix.py" not in script
    assert '[[ ! -e "$target" ]]' in script
    assert '[[ ! -e "$CATALOG" ]]' in script
    assert "--model-size base" in script
    assert "build_research_catalog.py" in script
    assert "publish_release.py" not in script
    assert "releases/current" not in script
