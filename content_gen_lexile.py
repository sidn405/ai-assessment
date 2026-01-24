async def generate_lesson_with_lexile(topic, lexile_level):
    """Generate lesson content at specific Lexile level"""
    
    lexile_guidance = {
        (0, 300): "Use very simple sentences (5-8 words). Basic vocabulary. Present tense. Concrete concepts.",
        (300, 600): "Use simple sentences (8-12 words). Common vocabulary. Mix of tenses. Some abstract concepts.",
        (600, 900): "Use varied sentence structures (10-15 words). Grade-level vocabulary. Complex sentences OK.",
        (900, 1100): "Use complex sentences. Advanced vocabulary. Multiple clauses. Abstract reasoning.",
        (1100, 1300): "Use sophisticated language. Academic vocabulary. Nuanced concepts.",
        (1300, 1600): "Use college-level language. Technical vocabulary. Complex analysis."
    }
    
    # Find appropriate guidance
    guidance = "Use age-appropriate language."
    for (min_lex, max_lex), guide in lexile_guidance.items():
        if min_lex <= lexile_level < max_lex:
            guidance = guide
            break
    
    prompt = f"""
    Create a reading comprehension lesson about {topic} at Lexile level {lexile_level}L.
    
    Writing Guidelines: {guidance}
    
    Target Lexile: {lexile_level}L (±50L acceptable)
    
    Provide:
    1. A passage (150-250 words) at the specified Lexile level
    2. 3 comprehension questions (literal, inferential, evaluative)
    3. 4 vocabulary words with definitions
    
    Format as JSON.
    """
    
    # Call your AI API with this prompt
    # ... (your existing lesson generation code)