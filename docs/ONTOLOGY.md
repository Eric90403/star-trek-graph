# Star Trek Graph — Ontology Reference

## Layer 1 — Canonical Facts

### Node Labels

| Label | Key Properties |
|-------|----------------|
| `Episode` | id, series, season, episode_num, title, stardate_start, stardate_end, airdate, writer, director, canon_tier |
| `Scene` | id, episode_id, act, scene_num, location_ref, time_of_day |
| `Line` | id, scene_id, line_num, speaker_ref, text, parenthetical |
| `Character` | canonical_name, aliases, species_ref, primary_affiliation |
| `CharacterState` | character_ref, stardate, rank, posting_ship_ref, notes |
| `Ship` | name, registry, class, affiliation_ref, status |
| `Location` | name, type (planet/station/region/ship_interior), region_ref |
| `Species` | name, homeworld_ref, notable_traits |
| `Organization` | name, type (govt/military/criminal/religious) |
| `Quote` | text, speaker_ref, episode_ref, scene_ref, embedding_id |
| `Universe` | name (Prime, Mirror, Kelvin, AU-community) |

### Edge Types

```
(Character)-[:APPEARS_IN {scene_count, line_count}]->(Episode)
(Line)-[:SPOKEN_BY]->(Character)
(Line)-[:IN_SCENE]->(Scene)
(Scene)-[:IN_EPISODE]->(Episode)
(Scene)-[:SET_AT]->(Location)
(Character)-[:SERVES_ABOARD {start_stardate, end_stardate, rank}]->(Ship)
(Character)-[:MEMBER_OF]->(Organization)
(Character)-[:IS_SPECIES]->(Species)
(Character)-[:SPEAKS_WITH {episode_id, line_count}]->(Character)
(Episode)-[:FEATURES_SHIP]->(Ship)
(Episode)-[:IN_UNIVERSE]->(Universe)
(CharacterState)-[:STATE_OF]->(Character)
```

## Layer 2 — Behavioral Models (Phase 3)

```
(Character)-[:HAS_BEHAVIORAL_CARD]->(BehavioralCard {
  core_identity, driving_question,
  speech_patterns[], decision_heuristics[],
  hard_limits[], voice_corpus_query
})
```

## Layer 3 — Narrative Grammar (Phase 4)

```
(Trope {name, mechanism, stakes, freshness_score})
(BeatTemplate {series, structure_json})
(Theme {name, description})

(Episode)-[:USES_TROPE]->(Trope)
(Episode)-[:HAS_THEME]->(Theme)
(Character)-[:HAS_TENSION_WITH {type, current_tension, last_addressed_episode}]->(Character)
```

## Layer 4 — Worldbuilding Rules (Phase 4)

```
(Rule {
  id, type (physics|political|species|tech),
  scope_series[], scope_era,
  statement_nl, established_in_episode_ref
})
```

## Layer 5 — Authorial Intent (Phase 4)

```
(Series {
  name, era_start, era_end,
  tonal_profile: {optimism, moral_ambiguity, serialization, philosophical_density}
})
```

## Canon Tiers

| Tier | Meaning |
|------|---------|
| 1 | Aired canon (films + TV) |
| 2 | Producer-acknowledged supplementary |
| 3 | Licensed tie-in (novels, comics) |
| 4 | Community-validated generated content |
| 5 | Explicitly non-canon / AU |

## Phase 1 Subset

For the spike, we implement only Layer 1 with these nodes:
**Episode, Scene, Line, Character, Ship, Location** and these edges:
**APPEARS_IN, SPOKEN_BY, IN_SCENE, IN_EPISODE, SET_AT, FEATURES_SHIP**.

That's enough to validate the parser and prove the schema before investing
in enrichment.
