// Star Trek Graph — sample Cypher queries (Layer 1)

// 1. Top 10 characters by total dialogue lines across all episodes
MATCH (c:Character)<-[:SPOKEN_BY]-(l:Line)
RETURN c.canonical_name AS character, count(l) AS lines
ORDER BY lines DESC LIMIT 10;

// 2. Per-episode line counts for top characters
MATCH (c:Character)-[r:APPEARS_IN]->(e:Episode)
RETURN e.id AS episode, e.title AS title,
       c.canonical_name AS character, r.line_count AS lines
ORDER BY episode, lines DESC;

// 3. Characters who appear together in the same scene
MATCH (a:Character)<-[:SPOKEN_BY]-(:Line)-[:IN_SCENE]->(s:Scene)<-[:IN_SCENE]-(:Line)-[:SPOKEN_BY]->(b:Character)
WHERE a.canonical_name < b.canonical_name
RETURN a.canonical_name AS a, b.canonical_name AS b, count(DISTINCT s) AS shared_scenes
ORDER BY shared_scenes DESC LIMIT 20;

// 4. Episodes featuring the Enterprise
MATCH (e:Episode)-[:FEATURES_SHIP]->(s:Ship {name: "Enterprise"})
RETURN e.id, e.title, e.stardate;

// 5. Picard's 10 longest speeches
MATCH (l:Line)-[:SPOKEN_BY]->(c:Character {canonical_name: "PICARD"})
RETURN l.episode_id AS ep, l.line_num AS n, size(l.text) AS chars, l.text AS text
ORDER BY chars DESC LIMIT 10;

// 6. Character co-occurrence network (build SPEAKS_WITH-like view)
MATCH (a:Character)<-[:SPOKEN_BY]-(la:Line)-[:IN_SCENE]->(s:Scene)<-[:IN_SCENE]-(lb:Line)-[:SPOKEN_BY]->(b:Character)
WHERE a.canonical_name < b.canonical_name
WITH a, b, count(*) AS exchanges
WHERE exchanges >= 5
RETURN a.canonical_name, b.canonical_name, exchanges
ORDER BY exchanges DESC LIMIT 25;

// 7. Most common scene locations
MATCH (s:Scene)-[:SET_AT]->(l:Location)
RETURN l.name AS location, count(s) AS scene_count
ORDER BY scene_count DESC LIMIT 15;

// 8. Acts / scene distribution per episode
MATCH (s:Scene)-[:IN_EPISODE]->(e:Episode)
RETURN e.id AS ep, e.title AS title, s.act AS act, count(s) AS scenes
ORDER BY ep, act;

// 9. Characters appearing in multiple episodes
MATCH (c:Character)-[:APPEARS_IN]->(e:Episode)
WITH c, count(DISTINCT e) AS eps
WHERE eps > 1
RETURN c.canonical_name, eps ORDER BY eps DESC;

// 10. Dialogue density by episode (lines / scenes)
MATCH (e:Episode)
OPTIONAL MATCH (s:Scene)-[:IN_EPISODE]->(e)
WITH e, count(DISTINCT s) AS scenes
OPTIONAL MATCH (l:Line) WHERE l.episode_id = e.id
RETURN e.id AS id, e.title AS title, scenes, count(l) AS lines,
       CASE WHEN scenes = 0 THEN 0 ELSE toFloat(count(l)) / scenes END AS lines_per_scene
ORDER BY id;
