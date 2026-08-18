"""Deterministic seed derivation.

One integer must reproduce an entire run. Every random draw anywhere downstream
gets its seed from :func:`derive`, so a bench run is fully described by
``master_seed`` plus the code that names the purposes — see
docs/ARCHITECTURE.md section 7.

Why a hash and not ``master_seed + index``:

* Consecutive integers are a poor way to seed independent streams. Mersenne
  Twister initialisation from nearby integers is fine in practice, but the
  property is not guaranteed by any library we depend on, and other consumers of
  these values (``random.Random``, GerryChain's RNG, numpy) make no promise at
  all about nearby seeds.
* Purposes must not collide. ``derive(s, "chain", 3)`` and
  ``derive(s, "scenario", 3)`` have to be unrelated streams, and additive schemes
  make that a bookkeeping problem instead of a property of the function.

blake2b gives both for free, and is stable across processes, platforms and
Python versions — unlike the builtin ``hash()``, which is salted per process.

The output is 63 bits, non-negative, so it is safe to hand to any library that
wants a plain ``int`` seed and unsafe-at-64-bits nowhere.
"""

from __future__ import annotations

import hashlib

DOMAIN = b"districting-bench/generate/seeds/v1"
BITS = 63


def _framed(*fields: bytes) -> bytes:
    """Length-prefixed concatenation, so no field can impersonate another.

    A plain separator join is ambiguous the moment a purpose string contains the
    separator. Framing each field with its length makes the encoding injective,
    which is what "deterministic and collision-free" actually requires.
    """
    out = bytearray()
    for field in fields:
        out += len(field).to_bytes(8, "big")
        out += field
    return bytes(out)


def derive(master_seed: int, purpose: str, index: int) -> int:
    """Return the seed for ``(master_seed, purpose, index)``.

    Args:
        master_seed: the one integer a whole run is reproducible from.
        purpose: a stable label for the stream, e.g. ``"chain"``. Changing a
            purpose string changes every seed under it, so treat these as part of
            the run's identity, not as free-text comments.
        index: position within the stream.

    Returns:
        A non-negative 63-bit integer.
    """
    if isinstance(master_seed, bool) or not isinstance(master_seed, int):
        raise TypeError(f"master_seed must be an int, got {type(master_seed).__name__}")
    if not isinstance(purpose, str):
        raise TypeError(f"purpose must be a str, got {type(purpose).__name__}")
    if isinstance(index, bool) or not isinstance(index, int):
        raise TypeError(f"index must be an int, got {type(index).__name__}")

    payload = _framed(
        DOMAIN,
        str(master_seed).encode("ascii"),
        purpose.encode("utf-8"),
        str(index).encode("ascii"),
    )
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big") >> (64 - BITS)


def stream(master_seed: int, purpose: str, count: int) -> list[int]:
    """``[derive(master_seed, purpose, i) for i in range(count)]``."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"count must be a non-negative int, got {count!r}")
    return [derive(master_seed, purpose, i) for i in range(count)]
