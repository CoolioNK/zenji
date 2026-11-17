-- ============================================================================
-- ZENJI – Row-Level-Security für Supabase
-- ============================================================================
-- Die Tabellen selbst werden vom Backend beim ersten Start automatisch erzeugt
-- (SQLAlchemy ``create_all``).  Dieses Skript aktiviert zusätzlich die
-- Row-Level-Security, damit jeder Account ausschließlich seine eigenen Daten
-- sieht.  Es ist idempotent und kann mehrfach ausgeführt werden.
--
-- Aufruf: Supabase Dashboard → SQL Editor → Skript einfügen → Run.
-- (Das Backend führt dieselben Policies beim Start selbst aus; dieses Skript
-- ist für manuelle Setups / Nachvollziehbarkeit gedacht.)
-- ============================================================================

GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;

-- conversations, messages, settings, personalities, policies, memories,
-- research_sessions, search_queries, search_results, sources,
-- source_snapshots, citations, research_cache
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'conversations', 'messages', 'settings', 'personalities', 'policies',
    'memories', 'research_sessions', 'search_queries', 'search_results',
    'sources', 'source_snapshots', 'citations', 'research_cache'
  ]
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_own', t);
    EXECUTE format(
      'CREATE POLICY %I ON public.%I FOR ALL TO authenticated '
      'USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())',
      t || '_own', t
    );
  END LOOP;
END $$;

-- accounts
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "profiles_own" ON public.profiles;
CREATE POLICY "profiles_own" ON public.profiles
  FOR ALL TO authenticated
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid());

-- technische Migrations-Tabelle: für normale Nutzer sperren
ALTER TABLE public.schema_version ENABLE ROW LEVEL SECURITY;