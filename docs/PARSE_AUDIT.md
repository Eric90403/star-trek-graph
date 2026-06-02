# Parse Quality Audit

**Corpus:** 176 episodes

## Title hygiene

**2 episodes with title problems:**

| ID | Title (excerpt) | Issues |
|----|-----------------|--------|
| 132 | `Loud as a Whisper  \n                           #40272-132  \n    ` | TOO LONG (714 chars), CONTAINS NEWLINE, CONTAINS HEADER JUNK |
| 235 | `#40276-235  \n                                \n                  ` | TOO LONG (712 chars), CONTAINS NEWLINE, CONTAINS HEADER JUNK |

## Dialogue line count distribution

- Min: 239
- p10: 341
- p50: 398
- p90: 456
- Max: 809
- Mean: 401

**Episodes with thin parses (<300 lines):**

| ID | Title | Lines |
|----|-------|-------|
| 111 | Q | 239 |
| 234 | A Fistful of Datas | 277 |
| 241 | Tapestry | 291 |

## Scene count distribution

- Min: 22
- p10: 32
- p50: 48
- Max: 114


## Suspicious speaker names

No obvious parser-noise speakers ✅

## Parser warnings

| Warning | Episodes |
|---------|----------|
| No CAST block detected; relying on cue extraction | 1 |

