from pathlib import Path

from utils.naming import (
    base_stem_from_filename,
    canonical_jsonl_filename,
    canonical_dataset_stem,
    dataset_id_from_path,
    normalize_language_tag,
    part_number_from_filename,
    source_stem_from_audio_filename,
)


def test_canonical_dataset_stem_includes_part():
    stem = canonical_dataset_stem(
        "valmiki_ramayanam",
        title="sampoorna_ramayanam",
        author="chaganti",
        language="te",
        kind="audio",
        part=1,
    )

    assert stem == "valmiki_ramayanam_sampoorna_ramayanam_chaganti_te_audio_part01"


def test_canonical_jsonl_filename_ends_with_jsonl():
    filename = canonical_jsonl_filename(
        "valmiki_ramayanam",
        title="sampoorna_ramayanam",
        author="chaganti",
        language="te",
        kind="transcript",
        part=1,
    )

    assert filename == "valmiki_ramayanam_sampoorna_ramayanam_chaganti_te_transcript_part01.jsonl"


def test_dataset_id_from_canonical_path_uses_stem():
    path = Path("knowledge/processed/valmiki_ramayanam_chaganti_te_audio_part01.jsonl")
    assert dataset_id_from_path(path) == "valmiki_ramayanam_chaganti_te_audio_part01"


def test_normalize_language_tag_shortens_common_labels():
    assert normalize_language_tag("Telugu") == "te"
    assert normalize_language_tag("hi-IN") == "hi"


def test_base_stem_from_filename_strips_kind_suffix():
    assert base_stem_from_filename("valmiki_ramayanam_chaganti_te_audio_part01.mp3") == "valmiki_ramayanam_chaganti_te"
    assert base_stem_from_filename("valmiki_ramayanam_chaganti_te_transcript_part01.jsonl") == "valmiki_ramayanam_chaganti_te"


def test_source_stem_from_audio_filename_strips_language_and_kind():
    assert source_stem_from_audio_filename("valmiki_ramayanam_chaganti_te_audio_part01.mp3", language="te") == "valmiki_ramayanam_chaganti"
    assert source_stem_from_audio_filename("lecture_audio_part01.wav", language="hi-IN") == "lecture"


def test_part_number_from_filename_reads_chunk_index():
    assert part_number_from_filename("valmiki_ramayanam_chaganti_te_audio_part0007.mp3") == 7
    assert part_number_from_filename("lecture.mp3") == 1
