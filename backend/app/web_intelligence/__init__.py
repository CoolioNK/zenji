"""Web Intelligence Engine (Phase 3).

Eigenständige Recherche-Schicht: Suchmaschinen-Abstraktion, Research
Planner, Browser Engine (mit SSRF-Schutz), Content-Extraktion, Source
Management/-Analyse, Citation Engine und Research Cache. Der ZENJI Core
nutzt ausschließlich die Research Engine als Schnittstelle – niemals
direkt eine Suchmaschinen- oder Browser-Bibliothek.

Sicherheitsgrundsatz: Webinhalte sind **untrusted data**. Sie werden als
reines Informationsmaterial in Datenblöcken übergeben, niemals als
Anweisungen behandelt und können Persönlichkeit, Regeln oder Identität
nicht verändern (siehe ``app.web_intelligence.ssrf`` und
``docs/WEB_SECURITY.md``).
"""
