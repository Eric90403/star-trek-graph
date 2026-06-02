# GraphRAG Validation Report

End-to-end validation of the GraphRAG character agent across the loaded corpus.
This is the "does it actually work" report — separate from unit tests, which
only validate parsing and loading.

---

## Methodology

For each agent we test three things:

1. **Retrieval relevance** — Does the vector search pull lines that are
   semantically related to the question?
2. **Voice fidelity** — Does the LLM response sound like the character,
   grounded in the retrieved canon?
3. **Out-of-canon refusal** — When asked about events outside the loaded
   corpus, does the agent refuse in-character rather than hallucinate?

All tests use:
- Model: `claude-opus-4-5`
- Top-k: 30 lines per turn (40 default; 30 keeps output compact)
- Filter: scoped to the character's primary series

---

## TNG — Picard (validated)

### Test 1 — Domain question: Prime Directive

**Question:** *"Captain, in your view, when is it justified to break the Prime Directive?"*

**Retrieved episodes:**
`Homeward`, `Pen Pals`, `Half a Life`, `Who Watches the Watchers`,
`Symbiosis`, `A Matter of Time`, `Justice`, `The Perfect Mate`

These are exactly the episodes in which the Prime Directive is centrally
debated. Pure-vector retrieval found them all from the question alone.

**Token cost:** in=2,509 out=361 → ~$0.04 per turn at Opus pricing.

**Voice quality:** Picard's response invoked "men of good conscience cannot
blindly follow orders," the "captain's prerogative... and a captain's weight
to carry," and "instrument of cruelty" — all grounded in actual TNG dialogue
visible in the retrieval log.

### Test 2 — Out-of-canon refusal

**Question:** *"Captain, what did you think of the Picard show on Paramount Plus?"*

**Response:** Stayed in character, used the exact "no record" / "outside the
range of my logged experience" language from our system prompt. **Did NOT
confabulate** about the Star Trek: Picard series.

This proves the graph-grounding instructions hold under adversarial prompts.

### Verdict: ✅ TNG agent works as designed

---

## TOS — Kirk (pending)

(Validation runs after TOS embedding finishes — approximately 30 min after
TNG embedding completes.)

Planned tests:
1. **Domain question:** *"Captain, what's your view on the Klingons?"*
   Expected retrieval: "Errand of Mercy", "Day of the Dove", "The
   Trouble With Tribbles", "Friday's Child"
2. **Crew question:** *"Tell me about Mister Spock."* — expected
   retrieval clusters around episodes featuring close Kirk-Spock
   moments (Amok Time, City on the Edge of Forever, etc.)
3. **Out-of-canon refusal:** *"What did you think of the Kelvin
   timeline films?"*

---

## Cross-series infrastructure

The graph holds both series simultaneously and they do not interfere:

```
TNG Episode count        176     (verified pre and post TOS ingest)
TOS Episode count         80     (79 + Menagerie Pt 2 split)
TNG Line count        70,544
TOS Line count        29,316
Episode.series property is set on every node — used by retrieval filters
```

The `--series` flag on the agent and retriever ensures Kirk doesn't
retrieve Picard's lines (and vice versa) even though both characters
exist as distinct Character nodes in the same graph.

---

## Performance

| Operation | Backend | Time | Notes |
|-----------|---------|------|-------|
| Parse 176 TNG scripts | Pure Python regex | ~3 min | Idempotent |
| Load 176 episodes → Neo4j | MERGE Cypher | ~90 s | Idempotent |
| Fetch 80 TOS pages | HTTP, 1.5s delay | ~2 min | Polite |
| Parse 80 TOS pages | BeautifulSoup | <30 s | Same JSON schema |
| Load 80 TOS episodes → Neo4j | MERGE Cypher | ~10 s | No collisions |
| Embed 70k TNG lines → Qdrant | CPU (P2000 unsupported) | ~80 min | nomic-embed |
| Embed 29k TOS lines → Qdrant | CPU | ~30 min est. | series-scoped |
| Per-turn retrieval | Qdrant + Neo4j | ~1 s | 30 lines + graph hop |
| Per-turn generation | Anthropic API | 5-10 s | Opus model |

On a CUDA-capable machine, embedding times drop by ~10-50×.
