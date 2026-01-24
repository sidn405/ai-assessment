-- Add Lexile level columns to lessons table
ALTER TABLE lessons ADD COLUMN lexile_level INTEGER;
ALTER TABLE lessons ADD COLUMN lexile_range_min INTEGER;
ALTER TABLE lessons ADD COLUMN lexile_range_max INTEGER;

-- Add Lexile level to user profile
ALTER TABLE users ADD COLUMN lexile_level INTEGER DEFAULT 500;
ALTER TABLE users ADD COLUMN target_lexile INTEGER;

-- Update existing lessons with Lexile levels based on current reading_level
UPDATE lessons SET 
    lexile_level = CASE 
        WHEN reading_level = 'beginner' THEN 200
        WHEN reading_level = 'elementary' THEN 450
        WHEN reading_level = 'intermediate' THEN 750
        WHEN reading_level = 'middle_school' THEN 1000
        WHEN reading_level = 'high_school' THEN 1200
        WHEN reading_level = 'advanced' THEN 1400
        ELSE 500
    END,
    lexile_range_min = CASE 
        WHEN reading_level = 'beginner' THEN 0
        WHEN reading_level = 'elementary' THEN 300
        WHEN reading_level = 'intermediate' THEN 600
        WHEN reading_level = 'middle_school' THEN 900
        WHEN reading_level = 'high_school' THEN 1100
        WHEN reading_level = 'advanced' THEN 1300
        ELSE 400
    END,
    lexile_range_max = CASE 
        WHEN reading_level = 'beginner' THEN 300
        WHEN reading_level = 'elementary' THEN 600
        WHEN reading_level = 'intermediate' THEN 900
        WHEN reading_level = 'middle_school' THEN 1100
        WHEN reading_level = 'high_school' THEN 1300
        WHEN reading_level = 'advanced' THEN 1600
        ELSE 600
    END;