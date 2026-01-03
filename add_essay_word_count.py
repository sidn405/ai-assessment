import psycopg2

DATABASE_URL = ""

def add_word_count_requirement():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Add column for essay word count requirement
    cursor.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS essay_word_count_requirement INTEGER DEFAULT 50
    """)
    
    # Set initial values based on current reading level
    cursor.execute("""
        UPDATE users 
        SET essay_word_count_requirement = CASE 
            WHEN reading_level = 'beginner' THEN 50
            WHEN reading_level = 'intermediate' THEN 150
            WHEN reading_level = 'advanced' THEN 250
            ELSE 50
        END
        WHERE essay_word_count_requirement IS NULL OR essay_word_count_requirement = 50
    """)
    
    conn.commit()
    conn.close()
    print("✓ Added essay_word_count_requirement column")

if __name__ == "__main__":
    add_word_count_requirement()