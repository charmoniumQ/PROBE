https://www.sciencedirect.com/science/article/pii/S2215016122002746

Population: computational experiments
Intervention: system-level provenance capture
Comparison: performance overhead, no-missing-edges, few-extra-edges, granularity, ease-of-use, system requirements, storage cost
  Performance overhead := CPU overhead, wall time overhead, max RSS overhead
Outcome: efficient provenance

Databases: Scopus, Web Of Science, EI Compendix, IEEE Digital Library, ACM Digital Library

Constraints:
  - Language: English

Quality assessment:
  - Does lit evaluate or mention a system-level provenance capturing tool?

Data extraction:
  - Provenance tool name
  - Provenance tool characteristics (level, capture method, granularity, perf time overhead)

Search string: System-level AND provenance


Emphasis theirs
> However, for this approach to work, **all** applications in the system need to be built against, or dynamically linked to, provenance-aware libraries, replacing existing libraries.
-- CamFlow paper
This is as easy as setting LD_LIBRARY_PATH, for Rust, C++, and C binaries.

Difference between provenance in comptuational science and in security:
- Computational science can assume that no actor is intentionally malicious. If we set LD_PRELOAD, most programs won't override that. If they do, they can be modified to append instead of replace the LD_PRELOAD variable.

Interposition agents: transparently interposing user code at the system interface
https://dl.acm.org/doi/pdf/10.1145/168619.168626
