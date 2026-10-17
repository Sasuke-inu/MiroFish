"""R06: legal chunk_size/overlap combinations must terminate and keep the text.

RED was a start sequence 0 -> -39 -> -19 -> 1 -> ... (watchdog timeout on the
real function); every case here must finish, move forward and cover the input.
"""
import pytest

from app.services.text_processor import TextProcessor
from app.utils.file_parser import split_text_into_chunks


def walk_source(text, chunks, chunk_size):
    """Ground truth walk; text must use unique characters so find() is exact."""
    indexes, last_end = [], 0
    for chunk in chunks:
        assert chunk.strip() == chunk and chunk
        index = text.find(chunk, max(0, last_end - chunk_size))
        assert index != -1, 'chunk content missing from the source text'
        assert index <= last_end, 'a region of the source text was skipped'
        indexes.append(index)
        last_end = index + len(chunk)
    assert indexes[0] == 0
    assert all(b > a for a, b in zip(indexes, indexes[1:])), indexes  # strictly increasing
    assert last_end == len(text)
    return indexes


def unique_text(length=600, dot_at=40):
    """Every character occurs once, so chunk positions can be mapped exactly."""
    text = ''.join(chr(0x4E00 + i) for i in range(length))
    return text[:dot_at] + '\u3002' + text[dot_at:]


PATHOLOGICAL = [
    ('x' * 40 + '\u3002' + 'y' * 200, 100, 80),
    ('x' * 40 + '\u3002' + 'y' * 460, 500, 450),
]


@pytest.mark.parametrize('text,chunk_size,overlap', PATHOLOGICAL)
def test_pathological_settings_terminate_and_keep_both_ends(text, chunk_size, overlap):
    chunks = split_text_into_chunks(text, chunk_size, overlap)
    assert text.startswith(chunks[0])
    assert text.endswith(chunks[-1])
    assert len(chunks) <= len(text) // (chunk_size - overlap) + 2  # bounded, not a cycle


@pytest.mark.parametrize('chunk_size,overlap', [(100, 80), (500, 450), (100, 0), (100, 99)])
def test_unique_text_has_strictly_increasing_covered_windows(chunk_size, overlap):
    text = unique_text()
    chunks = split_text_into_chunks(text, chunk_size, overlap)
    assert len(chunks) <= len(text) + 1
    walk_source(text, chunks, chunk_size)


def test_zero_overlap_keeps_every_character_once():
    for text in ('a' * 1234, '\u4e2d\u6587' * 600, 'x' * 40 + '\u3002' + 'y' * 200):
        chunks = split_text_into_chunks(text, 100, 0)
        assert ''.join(chunks) == text


def test_overlap_at_the_upper_bound_terminates():
    text = 'z' * 300
    chunks = split_text_into_chunks(text, 100, 99)
    assert len(chunks) <= len(text) + 1
    assert text.startswith(chunks[0]) and text.endswith(chunks[-1])


def test_text_without_sentence_boundaries_is_fully_covered():
    text = 'a' * 1000
    chunks = split_text_into_chunks(text, 100, 0)
    assert chunks == [text[i:i + 100] for i in range(0, 1000, 100)]


def test_legal_sentence_boundary_still_shrinks_the_chunk():
    text = 'a' * 50 + '\u3002' + 'b' * 950
    chunks = split_text_into_chunks(text, 100, 10)
    assert chunks[0] == 'a' * 50 + '\u3002'


def test_multibyte_text_is_covered():
    text = '\u5c0f\u6a59\u5728\u5496\u5561\u5e97\u5de5\u4f5c\u3002' * 200
    chunks = split_text_into_chunks(text, 120, 0)
    assert ''.join(chunks) == text
    chunks = split_text_into_chunks(text, 120, 110)
    assert text.startswith(chunks[0]) and text.endswith(chunks[-1])


def test_short_and_blank_text():
    assert split_text_into_chunks('short', 100, 50) == ['short']
    assert split_text_into_chunks('', 100, 50) == []
    assert split_text_into_chunks('   \n  ', 100, 50) == []


@pytest.mark.parametrize('chunk_size,overlap', [
    (0, 0), (-5, 0), (True, 0), (3.5, 0), (100, -1), (100, 100), (100, 120), (100, 2.5),
])
def test_invalid_settings_are_rejected_at_the_function_level(chunk_size, overlap):
    with pytest.raises(ValueError):
        split_text_into_chunks('a' * 500, chunk_size, overlap)


def test_text_processor_delegates_to_the_single_fixed_implementation():
    text = 'x' * 40 + '\u3002' + 'y' * 200
    assert TextProcessor.split_text(text, 100, 80) == split_text_into_chunks(text, 100, 80)
    assert ''.join(TextProcessor.split_text('abc' * 100, 100, 0)) == 'abc' * 100
