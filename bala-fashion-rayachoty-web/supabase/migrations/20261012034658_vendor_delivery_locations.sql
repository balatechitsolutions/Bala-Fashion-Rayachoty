-- Rayachoty road-distance delivery requires a map pin for each vendor.
ALTER TABLE public.vendors
  ADD COLUMN IF NOT EXISTS latitude double precision,
  ADD COLUMN IF NOT EXISTS longitude double precision;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'vendors_latitude_valid') THEN
    ALTER TABLE public.vendors
      ADD CONSTRAINT vendors_latitude_valid
      CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'vendors_longitude_valid') THEN
    ALTER TABLE public.vendors
      ADD CONSTRAINT vendors_longitude_valid
      CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'vendors_coordinates_paired') THEN
    ALTER TABLE public.vendors
      ADD CONSTRAINT vendors_coordinates_paired
      CHECK ((latitude IS NULL) = (longitude IS NULL));
  END IF;
END $$;
