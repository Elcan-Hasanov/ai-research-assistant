DO $$
BEGIN
  EXECUTE format(
    'ALTER DATABASE %I SET hnsw.ef_search = 100',
    current_database()
  );
END $$;