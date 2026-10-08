# AI Content Generation Pipeline
# Generates reading passages and comprehension questions using OpenAI

from openai import OpenAI
import json
import os
from typing import List, Dict, Optional
from readability import analyze_readability
import re
import time
import random as _random
from collections import Counter as _Counter


def _find_correct_index(options, correct):
    """Index of the correct option, matched by text: exact first, then
    ignoring case/extra whitespace. None if it can't be found."""
    if correct is None:
        return None
    for i, opt in enumerate(options):
        if opt == correct:
            return i
    norm = lambda s: ' '.join(str(s).lower().split())
    target = norm(correct)
    for i, opt in enumerate(options):
        if norm(opt) == target:
            return i
    return None


def randomize_question_set(questions):
    """
    Comprehension-question presentation fix (client item #3):

    1. The questions come back in the order of the story, and the model tends
       to put the correct answer first (its own JSON example does). This
       shuffles the question ORDER so it doesn't follow the story, and
    2. spreads the correct answers evenly across the option positions so it
       isn't always "A": each multiple-choice question's correct option is
       moved to whichever position has been used least so far in this set
       (random tie-break), and the remaining options are shuffled into the
       other slots.

    correct_answer is matched by TEXT (that's how both the dashboard and the
    stored data grade answers), so grading is unaffected. A question whose
    correct_answer can't be located among its options is left untouched
    rather than risk corrupting it. Fill-in-the-blank questions have no
    options and are only reordered. Returns a NEW list; inputs aren't mutated.
    """
    if not questions:
        return questions
    usage = _Counter()
    result = []
    for q in questions:
        q = dict(q)
        opts = q.get('options')
        if (isinstance(opts, list) and len(opts) >= 2
                and q.get('type') not in ('fill_in_blank', 'fill-in-blank', 'fill_blank')):
            idx = _find_correct_index(opts, q.get('correct_answer'))
            if idx is not None:
                n = len(opts)
                least = min(usage[p] for p in range(n))
                target = _random.choice([p for p in range(n) if usage[p] == least])
                usage[target] += 1
                others = [o for i, o in enumerate(opts) if i != idx]
                _random.shuffle(others)
                q['options'] = others[:target] + [opts[idx]] + others[target:]
                q['correct_answer'] = opts[idx]  # canonical option text
        result.append(q)
    _random.shuffle(result)
    return result


class ContentGenerator:
    def __init__(self, api_key=None):
        """Initialize with OpenAI API key"""
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        # NEW API - Create client
        self.client = OpenAI(api_key=self.api_key)
        
    def _get_cultural_context_guidance(self, age, grade_band, cultural_identity=None):
        """
        Provides culturally-responsive context guidance based on the student's
        cultural identity. Defaults to inclusive/diverse if not specified.
        """
        # ── Culture-specific character name pools ──────────────────────────
        # Item (new): tagged by gender so protagonist_gender selection (see
        # select_diversity_element() in app.py, field "protagonist_genders_used_recently")
        # can actually be honored — previously the AI was told "PREFER {gender}
        # protagonist" but handed a single mixed-gender list, so the instruction
        # was routinely ignored and stories skewed toward one gender.
        name_pools = {
            'black_african_american': {
                'male': ['Jamal', 'Marcus', 'Devon', 'Malik', 'Andre', 'Elijah', 'Isaiah',
                         'Jaylen', 'Darius', 'Trey', 'Kofi', 'DeShawn', 'Miles', 'Cameron', 'Jordan'],
                'female': ['Aaliyah', 'Imani', 'Destiny', 'Jasmine', 'Simone', 'Nia', 'Amara',
                           'Keisha', 'Brianna', 'Sanaa', 'Raven', 'Zara', 'Jade'],
            },
            'hispanic_latino': {
                'male': ['Mateo', 'Diego', 'Sebastián', 'Alejandro', 'Miguel', 'Carlos',
                         'Andrés', 'Emilio', 'Rafael', 'Javier', 'Luis', 'Rodrigo'],
                'female': ['Sofia', 'Isabella', 'Valentina', 'Camila', 'Lucia', 'Gabriela',
                           'Daniela', 'Valeria', 'Natalia', 'Mariana', 'Fernanda', 'Paola'],
            },
            'asian': {
                'male': ['Kenji', 'Jin', 'Raj', 'Arjun', 'Wei', 'Hiroshi', 'Kaito', 'Min-jun',
                         'Takeshi', 'Ravi', 'Sanjay', 'Haruto', 'Tenzin', 'Park', 'Chen'],
                'female': ['Mei', 'Priya', 'Aiko', 'Yuki', 'Sakura', 'Anya', 'Ananya', 'Sunita',
                           'Divya', 'Nadia', 'Yuna', 'Leila', 'Pooja', 'Amira'],
            },
            'native_american': {
                'male': ['Chayton', 'Takoda', 'Dakota', 'Cochise', 'Ahanu', 'Waya', 'Shilah', 'Elan'],
                'female': ['Aiyana', 'Kimi', 'Winona', 'Suni', 'Sequoia', 'Cheyenne', 'Tala',
                           'Nadie', 'Kaya', 'Lomasi'],
            },
            'pacific_islander': {
                'male': ['Kekai', 'Kai', 'Makoa', 'Keola', 'Koa', 'Ikaika', 'Alika'],
                'female': ['Kalani', 'Moana', 'Leilani', 'Hina', 'Nalani', 'Mahina', 'Pua',
                           'Mele', 'Noelani'],
            },
            'white': {
                'male': ['Liam', 'Noah', 'Ethan', 'Mason', 'Logan', 'Lucas', 'Aiden',
                         'Jackson', 'Owen', 'Sebastian'],
                'female': ['Emma', 'Olivia', 'Ava', 'Sophia', 'Isabella', 'Mia', 'Harper',
                           'Ella', 'Scarlett', 'Grace'],
            },
            'middle_eastern': {
                'male': ['Omar', 'Khalid', 'Yousef', 'Hassan', 'Tariq', 'Ahmad', 'Kareem', 'Ziad', 'Ali'],
                'female': ['Layla', 'Fatima', 'Amira', 'Nour', 'Sara', 'Rania', 'Yasmin', 'Hana', 'Samira'],
            },
        }

        # ── Culture-specific story context ─────────────────────────────────
        cultural_contexts = {
            'black_african_american': {
                'settings': ['urban neighborhood', 'community center', 'barbershop', 'church hall', 
                             'HBCU campus', 'local park', 'corner store', 'basketball court', 'school'],
                'themes': ['community pride', 'family bonds', 'resilience', 'excellence', 
                           'mentorship', 'cultural heritage', 'creativity', 'leadership'],
                'cultural_notes': 'Celebrate Black culture, excellence, and community. Use culturally authentic settings and experiences.'
            },
            'hispanic_latino': {
                'settings': ['family kitchen', 'mercado', 'quinceañera', 'school', 'community garden',
                             'neighborhood street', 'church', 'soccer field', 'abuela\'s house'],
                'themes': ['family (familia)', 'hard work', 'community (comunidad)', 'heritage', 
                           'bilingual pride', 'celebration', 'perseverance', 'dreams'],
                'cultural_notes': 'Celebrate Latino culture and family values. May naturally include Spanish words or phrases. Show strong family bonds and community connections.'
            },
            'asian': {
                'settings': ['family restaurant', 'school', 'temple', 'market', 'community center',
                             'martial arts studio', 'tech lab', 'garden', 'family home'],
                'themes': ['respect for elders', 'academic excellence', 'family honor', 'cultural tradition',
                           'innovation', 'balance', 'perseverance', 'community'],
                'cultural_notes': 'Celebrate Asian heritage authentically. Avoid stereotypes. Show diversity within Asian cultures. Balance tradition with modern life.'
            },
            'native_american': {
                'settings': ['reservation', 'forest', 'river', 'community gathering', 'school',
                             'elder\'s home', 'powwow', 'traditional grounds', 'natural landscape'],
                'themes': ['connection to nature', 'tribal heritage', 'oral tradition', 'respect for elders',
                           'stewardship', 'community', 'cultural preservation', 'identity'],
                'cultural_notes': 'Honor Native American cultures with deep respect. Celebrate connection to land, community, and tradition. Avoid stereotypes.'
            },
            'pacific_islander': {
                'settings': ['beach', 'community hall', 'school', 'fishing boat', 'family gathering',
                             'ocean', 'garden', 'village', 'cultural festival'],
                'themes': ['ocean connection', 'family (ohana)', 'navigation', 'cultural celebration',
                           'community strength', 'natural harmony', 'tradition', 'identity'],
                'cultural_notes': 'Celebrate Pacific Islander culture — Hawaiian, Samoan, Tongan, Filipino etc. Honor ohana (family) and connection to the ocean.'
            },
            'white': {
                'settings': ['school', 'suburb', 'farm', 'city neighborhood', 'sports field',
                             'library', 'park', 'family home', 'community center'],
                'themes': ['friendship', 'hard work', 'family', 'community', 'learning',
                           'sports', 'creativity', 'kindness', 'adventure'],
                'cultural_notes': 'Relatable everyday American experiences with diverse supporting characters.'
            },
            'middle_eastern': {
                'settings': ['family home', 'market (souk)', 'school', 'mosque', 'community center',
                             'garden', 'city', 'family business', 'cultural festival'],
                'themes': ['family honor', 'hospitality', 'faith', 'education', 'heritage',
                           'generosity', 'cultural pride', 'community bonds', 'achievement'],
                'cultural_notes': 'Celebrate Middle Eastern and North African cultures. Honor family, hospitality, and cultural heritage. Show modern and traditional balance.'
            },
        }

        # ── Grade-level context overlay ────────────────────────────────────
        grade_contexts = {
            'elementary': {
                'themes_add': ['friendship', 'learning', 'helping others', 'trying new things'],
                'avoid': ['Keep it simple and positive', 'No complex social issues']
            },
            'middle': {
                'themes_add': ['discovering talents', 'leadership', 'overcoming challenges'],
                'avoid': ['No trauma', 'Focus on growth']
            },
            'high': {
                'themes_add': ['career exploration', 'identity', 'college prep', 'entrepreneurship'],
                'avoid': ['Focus on empowerment', 'No deficit narratives']
            },
            'adult': {
                'themes_add': ['career advancement', 'community building', 'lifelong learning'],
                'avoid': ['Focus on resilience', 'Asset-based approach']
            }
        }

        if grade_band in ['pre-k', 'kindergarten', '1st', '2nd', '3rd', '4th', '5th', 'elementary']:
            grade_cat = 'elementary'
        elif grade_band in ['6th', '7th', '8th', 'middle']:
            grade_cat = 'middle'
        elif grade_band in ['9th', '10th', '11th', '12th', 'high']:
            grade_cat = 'high'
        else:
            grade_cat = 'adult'

        grade_ctx = grade_contexts.get(grade_cat, grade_contexts['elementary'])

        # Get culture-specific or default context
        culture = (cultural_identity or '').lower()
        cult_ctx = cultural_contexts.get(culture, {
            'settings': ['school', 'neighborhood', 'park', 'library', 'community center', 'home'],
            'themes': ['friendship', 'learning', 'community', 'growth', 'kindness'],
            'cultural_notes': 'Use diverse, inclusive characters representing multiple backgrounds.'
        })

        default_pool_by_gender = {
            # Default diverse pool when no identity specified. These are
            # deliberately unisex names, split into two lists purely so a
            # protagonist_gender pick still has a name pool to draw from.
            'male': ['Jordan', 'Quinn', 'Morgan', 'Taylor', 'Sage', 'Phoenix', 'Skylar'],
            'female': ['Avery', 'Riley', 'Alex', 'Cameron', 'River', 'Remy', 'Drew'],
        }
        pool_by_gender = name_pools.get(culture, default_pool_by_gender)

        return {
            'settings': cult_ctx['settings'],
            'themes': cult_ctx['themes'] + grade_ctx['themes_add'],
            'avoid': grade_ctx['avoid'],
            'cultural_notes': cult_ctx['cultural_notes'],
            'name_pool': pool_by_gender['male'] + pool_by_gender['female'],
            'name_pool_by_gender': pool_by_gender,
        }
    
    
        
    def _rewrite_passage_to_word_range(self, title, content, topic, difficulty_level, word_count_min, word_count_max, target_words):
        prompt = f"""
        Rewrite the passage below into a NEW VERSION.

        HARD WORD COUNT RULE:
        - The "content" field MUST be EXACTLY {target_words} words (content only).
        - Count words by splitting on spaces.
        - Before responding, self-check and adjust until exactly {target_words}.

        Hard rules:
        - Keep it a STORY (narrative), not an explanation/definition.
        - Keep the same topic focus: {topic}
        - Keep difficulty level: {difficulty_level}
        - No headings, no bullet points.

        Return ONLY valid JSON with:
        {{
        "title": "{title}",
        "content": "...",
        "key_concepts": ["...", "...", "..."],
        "vocabulary_words": [{{"word":"...","definition":"..."}}, ...]
        }}

        PASSAGE TO REWRITE:
{content}
"""
        resp = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You rewrite reading passages to match an exact word range while keeping a narrative story style."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
            max_tokens=2500,
            timeout=60
        )
        txt = resp.choices[0].message.content
        if "```json" in txt:
            txt = txt.split("```json")[1].split("```")[0].strip()
        elif "```" in txt:
            txt = txt.split("```")[1].split("```")[0].strip()
        return json.loads(txt)
    
    def generate_passage(self, topic, difficulty_level, word_count_min, word_count_max, user_interests,
                          age=None, grade_band=None, cultural_identity=None, student_name=None, used_names=None,
                          reading_track=1, genre=None, structure=None, perspective=None, interest_mode=None,
                          text_type=None, topic_area=None, word_count_band='standard',
                          protagonist_gender=None, supporting_role=None, used_supporting_names=None):
        """
        Generate educational passage using GPT-4 with dynamic word count.

        Item #8 (story generation variety) additions — all optional, default
        to Track 1 / current behavior so existing callers (e.g. the
        placement-test passage generator) work unchanged:
          reading_track: 1=Interest-Connected (default) | 2=Standards-Aligned | 3=Cold Reading
          genre/structure/perspective/interest_mode: pre-selected diversity picks
              (see select_diversity_element() in app.py) — when given, these
              replace the old random story_angle list with history-aware variety.
          text_type: narrative|informational|historical|biographical|argumentative|scientific|literary
          topic_area: the Track 2 standards topic (e.g. "life-science") — used
              INSTEAD of `topic`/interests when reading_track == 2.
          word_count_band: 'standard' (default) | 'extended' — extended nudges
              target_words toward word_count_max rather than the range midpoint.

        Bug fix (protagonist gender balance): protagonist_gender/supporting_role
        are now pre-selected by app.py's select_diversity_element() (rolling
        last-5 history, same mechanism as genre/structure) and passed in
        explicitly. This replaces the old name-based gender GUESS (a hardcoded,
        incomplete first-name list that silently defaulted to 'female' for any
        name it didn't recognize — including plenty of real male students —
        and then handed the AI a mixed-gender name list anyway, so the
        "PREFER {gender}" instruction was frequently ignored). That was the
        root cause of stories skewing away from male protagonists. When
        protagonist_gender isn't supplied (older callers, e.g. the
        placement-test path), we now pick 50/50 at random instead of
        guessing from the name, so we never systematically favor one gender.
        """

        import random
        target_words = word_count_max if word_count_band == 'extended' else (word_count_min + word_count_max) // 2
        if used_names is None:
            used_names = []

        gender_hint = protagonist_gender if protagonist_gender in ('male', 'female') else random.choice(['male', 'female'])

        # Get culturally-responsive context
        cultural_ctx = self._get_cultural_context_guidance(age, grade_band, cultural_identity)
        full_pool = cultural_ctx['name_pool']
        gendered_pool = cultural_ctx['name_pool_by_gender'].get(gender_hint, full_pool)

        # Filter out already-used names — student never sees the same name twice.
        # Draw from the GENDER-MATCHED pool first so the chosen name actually
        # agrees with gender_hint instead of the AI picking any name from a
        # mixed-gender list and silently overriding the "PREFER" instruction.
        available_names = [n for n in gendered_pool if n not in used_names]
        if not available_names:
            # Exhausted this gender's unused names for this student — reset
            # within that same gender rather than falling back to the whole
            # (mixed-gender) pool, so gender_hint is still honored.
            available_names = gendered_pool[:]

        random.shuffle(available_names)
        # Give AI the gender-matched available pool to choose from freely
        name_options = ', '.join(available_names)

        # Supporting-character role rotation (fixes "same 4 characters
        # repeated" — grandmother/coach/teacher — by giving the AI ONE
        # specific, history-aware role instead of a generic open choice it
        # kept resolving to the same handful of defaults).
        supporting_role_pool = [
            'older sibling', 'coach', 'teacher', 'grandmother', 'grandfather',
            'aunt or uncle', 'neighbor', 'best friend', 'classmate', 'librarian',
            'mentor from an after-school program', 'family friend', 'cousin',
            'youth group leader', 'shop or business owner in the community',
        ]
        supporting_role_pick = supporting_role if supporting_role in supporting_role_pool else random.choice(supporting_role_pool)

        # Bug fix ("Mr. Johnson" recurring under different roles): the role
        # now rotates, but nothing ever constrained or tracked the supporting
        # character's NAME, so the AI kept defaulting to the same familiar
        # name regardless of role. Give it a specific, history-aware name
        # pool the same way the protagonist gets one — drawn from the full
        # (both-gender) cultural name pool, minus the protagonist's own name
        # and minus names already used as a supporting character for this
        # student.
        if used_supporting_names is None:
            used_supporting_names = []
        supporting_name_candidates = [
            n for n in full_pool
            if n not in used_supporting_names and n not in available_names
        ]
        if not supporting_name_candidates:
            supporting_name_candidates = [n for n in full_pool if n not in available_names] or full_pool[:]
        random.shuffle(supporting_name_candidates)
        supporting_name_options = ', '.join(supporting_name_candidates[:10])

        # Pick a random story angle to prevent the AI defaulting to the same
        # scenario (e.g. "pizza party at school") for the same topic every time
        # Item #8: track/diversity-aware story angle. Falls back to the
        # original random list when called without a pre-selected
        # `structure` (e.g. the placement-test passage path), so that
        # caller keeps working unchanged.
        if structure:
            story_angle = structure.replace('-', ' ')
        else:
            story_angles = [
                "a surprising discovery",
                "a friendly competition",
                "helping someone in need",
                "learning something new for the first time",
                "a problem that needs creative solving",
                "an unexpected friendship",
                "a goal that takes practice to achieve",
                "a funny misunderstanding",
                "a challenge that builds confidence",
                "a day that doesn't go as planned — but turns out great",
                "working together as a team",
                "a special talent being discovered",
                "overcoming fear of trying something new",
                "a mystery to solve",
                "celebrating an achievement",
            ]
            story_angle = random.choice(story_angles)

        genre_instruction = f"- Genre: write this as a {genre.replace('-', ' ')} story." if genre else ""
        perspective_instruction = f"- Point of view: write in {perspective.replace('-', ' ')}." if perspective else ""
        interest_mode_instruction = ""
        if interest_mode and interest_mode != "ABSENT":
            mode_guidance = {
                "DIRECT": f"{topic} is the direct subject of the story.",
                "PERIPHERAL": f"{topic} appears in the background or as a minor detail, not the main focus.",
                "THEMATIC": f"the style or feel of {topic} shapes the story's tone, without {topic} being explicitly named as the plot.",
                "CULTURAL-HISTORICAL": f"explore the history, culture, or community around {topic} rather than a typical scene from it.",
                "ADJACENT": f"connect to something bordering {topic} — a related field, skill, or community — rather than {topic} itself.",
            }
            interest_mode_instruction = f"- Interest connection ({interest_mode}): {mode_guidance.get(interest_mode, '')}"

        text_type_val = text_type or "narrative"

        # Track-specific topic/subject framing (item #8's core fix: Track 2/3
        # break out of the "always one of the student's 10 interests" loop).
        if reading_track == 2 and topic_area:
            topic_focus_header = f"Write a {text_type_val.upper()} piece with {topic_area.replace('-', ' ')} as the primary subject."
            topic_line = f"- PRIMARY SUBJECT (standards-aligned, not an interest topic): {topic_area.replace('-', ' ')}"
            track_note = (
                f"        - This is Track 2 (Standards-Aligned): standards coverage is the primary driver, not student interest.\n"
                f"        - If a natural, unforced connection to {topic} exists, you may include ONE thread to it — never force it.\n"
                f"        - Apply strong narrative voice, concrete details, and a compelling opener even though the subject is {topic_area.replace('-', ' ')}."
            )
        elif reading_track == 3:
            topic_focus_header = f"Write a {text_type_val.upper()} piece for cold reading practice — assessment-style, with NO connection to any of the student's stated interests."
            topic_line = "- NO interest connection — this is Track 3 (Cold Reading)"
            track_note = (
                "        - Mirror standardized assessment passage tone and style.\n"
                "        - Prioritize argumentative or scientific writing for assessment readiness.\n"
                "        - Apply strong craft (voice, concrete detail, compelling opener) but with NO interest connection at all."
            )
        else:
            topic_focus_header = f"Write a {text_type_val.upper()} about {topic} featuring characters from the student's cultural background."
            topic_line = f"- PRIMARY INTEREST/TOPIC: {topic}"
            track_note = ""

        # ========== PASSAGE PROMPT ==========
        prompt = f"""{topic_focus_header}

        Student Profile:
        - Age: {age} years old
        - Grade Level: {grade_band}
        - Reading Difficulty: {difficulty_level}
        {topic_line}
        - Cultural Background: {cultural_identity or 'diverse/inclusive'}

{track_note}

        STORY ANGLE (make it fresh and different every time):
        - Story concept: {story_angle}
        - Apply this angle to the subject above — avoid repeating the same scenario
        {genre_instruction}
        {perspective_instruction}
        {interest_mode_instruction}
        
        CULTURAL AUTHENTICITY — IMPORTANT:
        - {cultural_ctx['cultural_notes']}
        - Authentic settings: {', '.join(cultural_ctx['settings'][:4])}
        - Resonant themes: {', '.join(cultural_ctx['themes'][:4])}
        - Guidelines: {' | '.join(cultural_ctx['avoid'])}
        
        CHARACTER DIVERSITY:
        - Protagonist gender: the protagonist MUST be {gender_hint} (this is a hard requirement, not a suggestion)
        - Choose ONE name from this list — every name in it is {gender_hint} and NEVER been used before for this student: {name_options}
        - DO NOT use any name not in the list above
        - Include exactly ONE significant supporting character, and make them a {supporting_role_pick}
        - Do not default to a generic "friend" if a more specific role is given above
        - Supporting character's name: choose ONE name from this list — NEVER used before for this student, and different from the protagonist's name: {supporting_name_options}
        - DO NOT name the supporting character "Mr. Johnson," "Ms. Lee," or any other name not in the list above — those defaults have been overused
        
        SETTING RULES:
        - Pick a setting that fits the topic: {topic}
        - Good options: school classroom, backyard, library, kitchen/home,
          art class, sports field, garden, friend's house, bookstore, grandma's house,
          after-school program, market, studio, neighborhood block
        - Avoid overused defaults like "community center"
        
        IMPORTANT - TOPIC FOCUS:
        {f"- The ONLY topic for this story is: {topic}" if reading_track == 1 else f"- The ONLY subject for this piece is: {topic_area.replace('-', ' ') if topic_area else 'the assigned subject'}"}
        - Do NOT introduce other topics not related to the subject above
        {f"- Stay 100% on topic — the student chose {topic} because it interests them" if reading_track == 1 else "- Stay fully on-subject"}
        
        HARD WORD COUNT RULE:
        - The "content" field MUST be EXACTLY {target_words} words.
        - Count words by splitting on spaces.
        - Self-check word count and adjust until exactly {target_words}.
        
        STORY STRUCTURE:
        - Character: Protagonist facing a relatable challenge or opportunity
        - Plot: Beginning → problem/challenge → resolution through creativity/effort/community
        - Include at least one line of dialogue
        - Show positive outcome and growth
        - NO criminal justice, violence, or trauma content
        - PARAGRAPH BREAKS: Separate the story into 3-4 paragraphs using blank lines (\\n\\n between each).
          Never return a single block of text — younger readers need visual breathing room.
        
        AGE-APPROPRIATE VOCABULARY:
        - Use {difficulty_level} level vocabulary
        - Include challenging academic words they can learn
        
        Return your response as a JSON object:
        {{
            "title": "Engaging title about {topic}",
            "protagonist_name": "The exact first name you chose for the protagonist",
            "supporting_character_name": "The exact first name you chose for the supporting character",
            "content": "The full story (EXACTLY {target_words} words)",
            "key_concepts": ["concept1", "concept2", "concept3"],
            "vocabulary_words": [
                {{"word": "challenging_word1", "definition": "simple, clear definition"}},
                {{"word": "challenging_word2", "definition": "simple, clear definition"}},
                ... (minimum 5-10 words based on difficulty level)
            ]
        }}
        
        REMINDER: This story should feel real and relatable to THIS student's actual cultural background and lived experience. Focus on positive experiences, community strength, and educational growth."""
        
        try:
            # NEW API SYNTAX
            # Was previously hardcoded to always describe "an African American
            # student from underserved communities" regardless of the actual
            # student's cultural_identity — cultural_ctx (built above, per
            # student) is now used here instead, matching what the user
            # prompt already does. Fixed alongside item #8 since this system
            # message needed rewriting for track-awareness anyway.
            system_message = f"""You are an expert educational content creator specializing in culturally relevant, trauma-informed content for K-12 students.

                        CRITICAL CULTURAL GUIDELINES:
                        1. **Authentic Representation**:
                           - {cultural_ctx['cultural_notes']}
                           - Include positive role models from the community (teachers, coaches, entrepreneurs, artists)
                           - Show families with different structures (single parents, grandparents, extended family)
                           - Represent settings authentically and positively: {', '.join(cultural_ctx['settings'][:4])}

                        2. **TRAUMA-INFORMED - AVOID**:
                           - Police encounters or criminal justice system references
                           - Violence, gangs, or crime as plot elements
                           - Poverty as a defining characteristic (it's context, not identity)
                           - Deficit narratives or stereotypes
                           - Drug-related content
                           - {' | '.join(cultural_ctx['avoid'])}

                        3. **EMPOWERING THEMES**:
                           - {', '.join(cultural_ctx['themes'][:6])}
                           - Overcoming challenges through creativity and resilience
                           - Educational and career success
                           - Arts, music, sports, and STEM as pathways
                           - Entrepreneurship and innovation

                        4. **VOCABULARY EXTRACTION**:
                           Extract ALL challenging words from your passage. A good passage should have AT LEAST 5-10 vocabulary words.
                           
                           Examples by level:
                           - Elementary: "ecosystem", "gravity", "nutrient", "habitat", "diverse"
                           - Intermediate: "phenomenon", "inevitable", "perspective", "substantial", "comprehensive"  
                           - High School: "culmination", "juxtaposition", "paradigm", "synthesis", "nuance"
                           - Adult: "epistemology", "hegemony", "empirical", "ubiquitous", "pragmatic"

                        STORY/PIECE REQUIREMENTS:
                        - Focus on ONE subject at a time
                        - For narrative text types: include a character, setting, and plot (beginning → problem → resolution) with at least one line of dialogue
                        - For informational/historical/biographical/argumentative/scientific text types: still use a strong, concrete, non-textbook voice with a compelling opener — never a flat lecture
                        - Make it engaging and age-appropriate
                        - Show positive outcomes through effort, creativity, or community support where the text type allows it
                        - NO articles, definitions, or lectures written in a flat textbook voice — bring the subject to life"""

            # Bug fix (silent fallback on long passages): max_tokens was a flat
            # 2500 regardless of target length. A 1055-1085 word Track 2/3
            # passage (word_count_band='extended' pushes toward word_count_max)
            # plus its JSON wrapper (title, key_concepts, 6-10 vocabulary words
            # with definitions) routinely exceeds that, so the model's JSON got
            # cut off mid-structure, json.loads() raised, and generate_passage()
            # silently returned the generic "[AI generation unavailable]"
            # placeholder passage instead — with no error surfaced to the
            # student or teacher. Scale the budget with word_count_max instead,
            # capped at gpt-4o's completion limit.
            dynamic_max_tokens = min(4096, max(2500, int(word_count_max * 2.2) + 1000))

            def _call_and_parse(max_tokens_budget, temperature=0.35, extra_instruction=""):
                resp = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": system_message
                        },
                        {"role": "user", "content": prompt + extra_instruction}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens_budget,
                    timeout=60
                )
                choice = resp.choices[0]
                raw = choice.message.content or ""

                if not raw.strip():
                    # Diagnostics for the empty-content case (distinct from a
                    # truncated-but-present response): a flat retry at a
                    # bigger token budget doesn't fix this, since a genuinely
                    # EMPTY response isn't a truncation problem. Surface
                    # finish_reason and any structured refusal so the real
                    # cause (content filter, API hiccup, etc.) is visible in
                    # the logs instead of just "JSONDecodeError".
                    refusal = getattr(choice.message, "refusal", None)
                    print(f"⚠️ Empty passage response — finish_reason={choice.finish_reason!r}, refusal={refusal!r}")

                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()

                return json.loads(raw)

            try:
                passage_data = _call_and_parse(dynamic_max_tokens)
            except json.JSONDecodeError as parse_err:
                # One retry before giving up. A truncated-but-nonempty
                # response is a token-budget problem, fixed by the larger
                # budget alone. A genuinely EMPTY response (the common case
                # in practice) isn't fixed by budget at all — identical
                # inputs tend to reproduce it — so the retry also nudges
                # temperature up and adds an explicit anti-empty-response
                # instruction to actually change the outcome instead of
                # repeating the same failed call.
                print(f"⚠️ Passage JSON parse failed ({parse_err}); retrying once with adjusted params...")
                passage_data = _call_and_parse(
                    4096,
                    temperature=0.6,
                    extra_instruction="\n\nCRITICAL: You MUST return a non-empty JSON object as specified above. Do not return an empty response."
                )
            
            # ========== VALIDATE & ENHANCE VOCABULARY ==========
            vocab_words = passage_data.get('vocabulary_words', [])
            vocab_count = len(vocab_words)
            
            print(f"📚 Initial vocabulary words: {vocab_count}")
            
            # Minimum vocabulary requirements by level
            # NOTE: difficulty_level is always 'beginner' | 'intermediate' | 'advanced'
            # (see calculate_difficulty() in app.py). The old keys here ('elementary',
            # 'high_school') never matched, so every passage silently fell back to 5.
            min_vocab = {
                'beginner': 5,
                'intermediate': 6,
                'advanced': 8
            }
            
            required_min = min_vocab.get(difficulty_level, 5)
            
            if vocab_count < required_min:
                print(f"⚠️ Only {vocab_count} words found. Need at least {required_min}. Extracting more...")
                passage_data['vocabulary_words'] = self._extract_additional_vocabulary(
                    passage_data['content'], 
                    vocab_words,
                    difficulty_level,
                    required_min
                )
                print(f"✅ Enhanced to {len(passage_data['vocabulary_words'])} vocabulary words")
            # ==================================================
            
            # Analyze readability
            from readability import analyze_readability

            # Analyze readability
            readability = analyze_readability(passage_data['content'])
            wc = readability['word_count']

            # If out of range, do up to 2 rewrite passes (MUCH faster than 6 new generations)
            if wc < word_count_min or wc > word_count_max:
                print(f"⚠️ Out of range on first draft: wc={wc}. Rewriting to fit...")

                for rewrite_attempt in range(1, 3):  # 2 rewrites max
                    passage_data = self._rewrite_passage_to_word_range(
                        title=passage_data.get("title", f"{topic}"),
                        content=passage_data["content"],
                        topic=topic,
                        difficulty_level=difficulty_level,
                        word_count_min=word_count_min,
                        word_count_max=word_count_max,
                        target_words=target_words
                    )
                    readability = analyze_readability(passage_data['content'])
                    wc = readability['word_count']
                    print(f"✍️ Rewrite attempt {rewrite_attempt}: wc={wc}")

                    if word_count_min <= wc <= word_count_max:
                        break

            # (Optional but recommended) Re-check vocab after rewrite because rewrite often returns fewer vocab words
            vocab_words = passage_data.get('vocabulary_words', [])
            vocab_count = len(vocab_words)
            required_min = min_vocab.get(difficulty_level, 5)

            if vocab_count < required_min:
                passage_data['vocabulary_words'] = self._extract_additional_vocabulary(
                    passage_data['content'],
                    vocab_words,
                    difficulty_level,
                    required_min
                )
            
            return passage_data
            
        except Exception as e:
            print(f"Error generating passage: {e}")
            import traceback
            traceback.print_exc()
            return self._get_fallback_passage(topic, difficulty_level)

    # Grade bands considered "younger students" for illustration purposes.
    # Matches the same elementary grouping used elsewhere (select_age_appropriate_topic,
    # calculate_difficulty) so this stays consistent if those buckets ever change.
    YOUNG_LEARNER_GRADE_BANDS = {
        'pre-k', 'kindergarten', '1st', '2nd', '3rd', '4th', '5th', 'elementary'
    }

    def is_young_learner(self, grade_band):
        """Return True if this grade band should get an illustration with its story."""
        return (grade_band or '').lower() in self.YOUNG_LEARNER_GRADE_BANDS

    def generate_story_image(self, title, content, topic, grade_band, cultural_identity=None):
        """
        Generate a story illustration styled to match the student's age/grade band.
        Style ranges from Pixar storybook (young kids) to graphic novel / editorial
        illustration (older teens/adults) so the art always feels age-appropriate.

        Bug fix: this previously took NO cultural_identity input at all, so the
        image prompt only ever described art STYLE (age-band) and a scene hint
        from the text — nothing told the image model who the characters should
        look like. Since the passage text often doesn't spell out physical
        appearance, the model defaulted to generic (frequently white-presenting)
        characters even for students whose story text and vocabulary were
        generated with e.g. black_african_american cultural context. Now the
        same cultural_identity used for the passage is passed straight through
        to the illustration prompt.
        """
        try:
            sentences = [s.strip() for s in (content or '').replace('\n', ' ').split('.') if s.strip()]
            scene_hint = '. '.join(sentences[:2]) if sentences else f"a story about {topic}"

            # ── Age-adaptive style map ──────────────────────────────────────
            # Maps grade band to an art style that fits the reader's age.
            gb = (grade_band or '').lower()

            if gb in ('pre-k', 'kindergarten', '1st', '2nd', '3rd'):
                # Ages 4-9: bright, rounded, very safe and playful
                style = (
                    "Warm Pixar-style children's storybook illustration. "
                    "Big expressive eyes, rounded soft shapes, pastel-bright colors, "
                    "simple cheerful backgrounds. Cozy, safe, and magical feeling. "
                    "Appropriate for ages 4-9."
                )
            elif gb in ('4th', '5th', '6th', 'elementary'):
                # Ages 9-12: slightly more detailed, still cartoon/animated feel
                style = (
                    "Colorful children's book illustration with a modern animated style, "
                    "similar to DreamWorks or Disney Channel. Expressive characters, "
                    "rich colors, dynamic poses, detailed backgrounds. "
                    "Appropriate for ages 9-12."
                )
            elif gb in ('7th', '8th', 'middle'):
                # Ages 12-14: graphic novel / YA illustrated style
                style = (
                    "Young Adult graphic novel illustration style. "
                    "Clean lines, bold colors, cinematic framing, "
                    "slightly more realistic proportions while staying illustration-based. "
                    "Dynamic and engaging, appropriate for ages 12-14."
                )
            elif gb in ('9th', '10th', '11th', '12th', 'high'):
                # Ages 14-18: editorial illustration / concept art style
                style = (
                    "Editorial illustration / digital concept art style. "
                    "Realistic proportions, sophisticated color palette, "
                    "mood lighting, painterly texture. Visually compelling "
                    "and age-appropriate for high school students ages 14-18."
                )
            else:
                # Adult: polished editorial / magazine illustration
                style = (
                    "Polished editorial magazine illustration. "
                    "Sophisticated color palette, realistic characters with expressive faces, "
                    "atmospheric depth and lighting. Professional and visually compelling "
                    "for adult readers."
                )

            # Character representation guidance, keyed to the student's actual
            # cultural_identity (mirrors _get_cultural_context_guidance's text
            # prompt) — so the illustration matches who the story is about
            # instead of defaulting to generic/white-presenting characters.
            representation_map = {
                'black_african_american': "The main characters shown should be Black/African American.",
                'hispanic_latino': "The main characters shown should be Hispanic/Latino.",
                'asian': "The main characters shown should be Asian.",
                'native_american': "The main characters shown should be Native American, depicted respectfully and without stereotype.",
                'pacific_islander': "The main characters shown should be Pacific Islander.",
                'white': "The main characters shown should be white.",
                'middle_eastern': "The main characters shown should be Middle Eastern.",
            }
            representation_instruction = representation_map.get((cultural_identity or '').lower(), "")

            image_prompt = (
                f"{style} "
                f"Scene: {scene_hint}. "
                f"{representation_instruction} "
                f"No text, letters, words, or numbers anywhere in the image."
            )

            # Item #5: this used to be a single attempt, so one rate-limit hit
            # (this OpenAI account allows 5 images/minute, and other image
            # jobs share that budget) meant the lesson went out with no
            # picture at all. Retry rate-limit errors with a wait, since the
            # limit window resets within a minute. Runs in a worker thread
            # (asyncio.to_thread / background thread), so sleeping is safe.
            response = None
            # Bumped from 2 to 4 retries: this account's 5-images/minute cap
            # is shared across every background thread generating images at
            # once (lessons, WordBank, missions, reserve pre-fill), so a
            # burst — e.g. reserve pre-generating several lessons back to
            # back — could still exhaust 2 retries and permanently save the
            # passage with image_url = NULL, with no later retry ever
            # happening. 4 retries with a longer max backoff gives a
            # burst substantially more time to clear the shared budget.
            max_retries = 4
            for attempt in range(max_retries + 1):
                try:
                    response = self.client.images.generate(
                        model="gpt-image-1",
                        prompt=image_prompt,
                        size="1536x1024",
                        quality="medium",
                        n=1
                    )
                    break
                except Exception as gen_err:
                    msg = str(gen_err).lower()
                    is_rate_limit = 'rate_limit' in msg or 'rate limit' in msg or '429' in msg
                    if is_rate_limit and attempt < max_retries:
                        wait_seconds = min(15 * (attempt + 1), 60)
                        print(f"⏳ Story image rate-limited — waiting {wait_seconds}s before retry {attempt + 1}/{max_retries}")
                        time.sleep(wait_seconds)
                        continue
                    raise

            b64_data = response.data[0].b64_json
            if not b64_data:
                return None

            return f"data:image/png;base64,{b64_data}"

        except Exception as e:
            print(f"⚠️ Story image generation failed (non-fatal, story will render without it): {e}")
            return None

    def _extract_additional_vocabulary(self, passage_text, existing_vocab, difficulty_level, min_required=5):
        """
        Use AI to extract more vocabulary words if initial extraction was insufficient
        
        Args:
            passage_text: The full passage content
            existing_vocab: List of already identified vocabulary dicts
            difficulty_level: Target difficulty (elementary, intermediate, etc.)
            min_required: Minimum number of total vocabulary words needed
        """
        existing_words = [v['word'].lower() for v in existing_vocab]
        words_needed = max(min_required - len(existing_vocab), 3)
        
        print(f"🔍 Extracting {words_needed} more vocabulary words...")
        
        prompt = f"""Analyze this passage and extract {words_needed} MORE challenging vocabulary words for a {difficulty_level} level reader.

    Passage:
    {passage_text}

    Already identified: {', '.join(existing_words) if existing_words else 'none'}

    Find {words_needed} MORE challenging words from this passage that students at {difficulty_level} level might not know.

    Focus on:
    - Academic vocabulary
    - Technical terms
    - Uncommon words
    - Subject-specific terminology
    - Advanced descriptive words

    Provide simple, age-appropriate definitions.

    Return ONLY a JSON array (no other text):
    [
        {{"word": "word1", "definition": "simple definition"}},
        {{"word": "word2", "definition": "simple definition"}},
        {{"word": "word3", "definition": "simple definition"}}
    ]"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": f"Extract challenging vocabulary for {difficulty_level} readers. Provide simple definitions."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000,
                timeout=30
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            additional_vocab = json.loads(content)
            
            # Combine with existing, avoid duplicates
            all_vocab = existing_vocab.copy()
            added_count = 0
            
            for new_word in additional_vocab:
                word_lower = new_word['word'].lower()
                if word_lower not in existing_words:
                    all_vocab.append(new_word)
                    existing_words.append(word_lower)
                    added_count += 1
            
            print(f"✅ Added {added_count} new vocabulary words")
            return all_vocab
            
        except Exception as e:
            print(f"❌ Error extracting additional vocabulary: {e}")
            import traceback
            traceback.print_exc()
            # Return existing vocabulary if extraction fails
            return existing_vocab

    def _get_fallback_passage(self, topic, difficulty):
        """Return a basic fallback passage if AI generation fails"""
        return {
            "title": f"Introduction to {topic}",
            "content": f"This is a {difficulty} passage about {topic}. [AI generation unavailable - please try again or contact administrator]",
            "source": "fallback",
            "topic_tags": [topic],
            "word_count": 50,
            "readability_score": 5.0,
            "flesch_ease": 70.0,
            "difficulty_level": difficulty,
            "estimated_minutes": 1,
            "key_concepts": [topic],
            "vocabulary_words": [
                {"word": "topic", "definition": "The main subject being discussed"},
                {"word": "passage", "definition": "A section of written text"},
                {"word": "educational", "definition": "Related to learning and teaching"}
            ],
            "vocabulary_count": 3
        }
        
            
    def _generate_vocab_distractors(self, chosen: list, passage_text: str) -> dict:
        """
        Asks the AI for 3 plausible-but-WRONG definitions per vocab word,
        matched in length/style/tone to a real dictionary-style definition,
        so a vocabulary question's wrong answers don't visibly belong to a
        completely different, unrelated word (see the call site's comment).
        Returns {} on any failure — callers fall back to the old method.
        """
        if not chosen:
            return {}
        try:
            words_block = "\n".join(
                f'- "{v["word"].strip()}" (correct definition: {v["definition"].strip()})'
                for v in chosen
            )
            prompt = f"""For each vocabulary word below, write 3 WRONG but PLAUSIBLE definitions —
the kind a student who doesn't know the word might mistakenly believe is correct.

Hard rules for each wrong definition:
- Must be FALSE for that word (not just a rephrasing of the correct definition)
- Must be the SAME length and style as a real simple dictionary definition (one short sentence, similar detail level to the correct one)
- Must NOT obviously belong to some other random word — it should sound like it *could* be this word's definition
- Do not mention the word itself or any obvious form of it

Words:
{words_block}

Return ONLY valid JSON in exactly this shape (no markdown fences):
{{"word_here": ["wrong definition 1", "wrong definition 2", "wrong definition 3"], ...}}"""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You write plausible-sounding wrong multiple-choice answers for vocabulary quizzes."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=500
            )
            content = response.choices[0].message.content.strip()
            import re, json as _json
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if not match:
                return {}
            result = _json.loads(match.group())
            # Normalize keys to match the exact word strings we asked about
            normalized = {}
            for v in chosen:
                w = v['word'].strip()
                if w in result and isinstance(result[w], list):
                    normalized[w] = [str(d).strip() for d in result[w] if str(d).strip()]
            return normalized
        except Exception as e:
            print(f"⚠️ Vocab distractor generation failed (falling back): {e}")
            return {}

    def generate_comprehension_questions(self, passage_text: str, passage_title: str, num_questions: int = 4, allow_fill_blank: bool = True, vocabulary_words: list = None):
        """
        Generate comprehension questions with optional fill-in-blank and
        always includes one vocabulary question when vocabulary_words are provided.
        
        Args:
            passage_text: The passage content
            passage_title: Title of the passage  
            num_questions: Number of questions (default 4)
            allow_fill_blank: If True, mix MC and fill-in-blank. If False, MC only.
            vocabulary_words: List of vocab dicts with 'word' and 'definition' keys.
                              When provided, one question will always be a vocab question.
        """
        
        # Pick up to 2 vocab words for dedicated vocabulary questions.
        # We generate num_questions - len(vocab_questions) comprehension
        # questions from the AI then append the vocab questions at the end
        # so they're always present (item #2: 5 total questions, 2 of them
        # vocabulary — was 4 total / 1 vocabulary).
        vocab_questions = []
        comprehension_count = num_questions

        if vocabulary_words and len(vocabulary_words) > 0:
            import random
            candidates = [v for v in vocabulary_words if v.get('word') and v.get('definition')]
            generic = [
                "A type of weather condition",
                "Something you eat for breakfast",
                "A place where people swim",
                "A very loud sound",
                "Moving very slowly",
            ]
            if candidates:
                # Pick up to 2 distinct words — prefer words with clean definitions
                pool = candidates[:]
                random.shuffle(pool)
                chosen = pool[:2]

                # Bug fix ("reading assessment answers easy to guess"): distractor
                # definitions used to be OTHER vocab words' real definitions
                # pulled from this same passage's list (e.g. asking what
                # "meticulous" means but offering the definition of "gigantic"
                # as a wrong answer). Those are instantly recognizable as
                # belonging to a totally different, unrelated word, so the
                # correct definition stood out by being the only one that
                # actually fit the question — guessable without even knowing
                # the word. Now we ask the AI for plausible-but-wrong
                # definitions of THIS SAME word, written in matching style/
                # length, so a guesser can't just spot the mismatched one.
                ai_distractors = self._generate_vocab_distractors(chosen, passage_text)

                for vocab_entry in chosen:
                    vocab_word = vocab_entry['word'].strip()
                    correct_def = vocab_entry['definition'].strip()

                    distractors = list(ai_distractors.get(vocab_word, []))[:3]

                    if len(distractors) < 3:
                        # Fallback: other vocab words' definitions (old
                        # behavior) — better than nothing if the AI call
                        # failed, but only used as a last resort now.
                        other_defs = [
                            v['definition'].strip() for v in candidates
                            if v['word'] != vocab_word and v.get('definition')
                        ]
                        random.shuffle(other_defs)
                        for d in other_defs:
                            if len(distractors) >= 3:
                                break
                            if d not in distractors:
                                distractors.append(d)

                    # Pad with generic distractors if still not enough
                    gi = 0
                    while len(distractors) < 3 and gi < len(generic):
                        if generic[gi] not in distractors:
                            distractors.append(generic[gi])
                        gi += 1

                    options = [correct_def] + distractors[:3]
                    random.shuffle(options)

                    vocab_questions.append({
                        "question": f'What does the word "{vocab_word}" mean in the story?',
                        "type": "multiple_choice",
                        "options": options,
                        "correct_answer": correct_def,
                        "explanation": f'"{vocab_word}" means: {correct_def}',
                        "difficulty": 1,
                        "is_vocabulary": True
                    })
                # Generate fewer from AI so total stays at num_questions
                comprehension_count = num_questions - len(vocab_questions)

        if allow_fill_blank:
            # Mix of question types for lessons
            type_instruction = """
    Generate EXACTLY {num_questions} comprehension questions with this distribution:
    - 2-3 multiple choice questions
    - 1-2 fill-in-the-blank questions
    
    QUESTION TYPES:
    1. MULTIPLE CHOICE: Standard 4-option questions
    2. FILL-IN-THE-BLANK: Questions where user types a word or short phrase
    
    REQUIREMENTS FOR FILL-IN-BLANK:
    - The blank must complete a sentence using words that appear VERBATIM in the passage above — do not paraphrase or summarize what goes in the blank
    - "correct_answer" MUST be copied exactly (word-for-word, same wording) from the passage text for that blank
    - "accept_answers" MUST include that exact verbatim phrase from the passage as one entry, plus close variations (lowercase) — e.g. with/without a leading article, singular/plural
    - Keep answers SHORT (1-4 words max)
    - Example: "accept_answers": ["library", "public library", "the library"]
    """
            json_example = """[
    {
        "question": "What is the main topic?",
        "type": "multiple_choice",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": "Option A",
        "explanation": "Why this is correct",
        "difficulty": 1
    },
    {
        "question": "The story takes place in a __________.",
        "type": "fill_in_blank",
        "correct_answer": "library",
        "accept_answers": ["library", "public library", "the library"],
        "explanation": "The passage mentions they met at the library",
        "difficulty": 2
    }
    ]"""
        else:

            # Only multiple choice for assessments
            type_instruction = """
    Generate EXACTLY {num_questions} MULTIPLE CHOICE questions.
    
    REQUIREMENTS:
    - ALL questions must be multiple choice with 4 options
    - NO fill-in-the-blank questions
    - Ensure only ONE correct answer per question
    """
            json_example = """[
    {
        "question": "What is the main topic?",
        "type": "multiple_choice",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": "Option A",
        "explanation": "Why this is correct",
        "difficulty": 1
    }
    ]"""
        
        prompt = f"""
    You are an expert educator creating comprehension questions for a reading passage.
    
    PASSAGE TITLE: {passage_title}
    
    PASSAGE:
    {passage_text}
    
    {type_instruction.format(num_questions=comprehension_count)}
    
    Return as JSON array:
    {json_example}
    
    IMPORTANT:
    - Vary difficulty (easier questions first)
    - Cover different aspects of the passage
    - Make questions age-appropriate
    - Test different comprehension skills
    - Do NOT include vocabulary definition questions — those are handled separately

    AVOID MAKING ANSWERS GUESSABLE WITHOUT READING THE PASSAGE:
    - All 4 options for a multiple-choice question must be SIMILAR in length and level of detail — never make the correct answer noticeably longer, more specific, or more "complete-sounding" than the wrong options
    - Every wrong option must be directly related to the passage's topic/characters/setting — never a generic, silly, or obviously-unrelated filler option (a reader should have to actually recall the passage to rule it out)
    - Never use "All of the above" or "None of the above"
    - Do not let the correct answer be the only option written in full sentences while others are sentence fragments, or vice versa
    """
    
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert educator creating engaging comprehension questions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Extract JSON from response
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                import json
                questions = json.loads(json_match.group())
                
                # Validate and normalize questions
                validated = []
                for q in questions[:comprehension_count]:
                    # If allow_fill_blank=False, force all to multiple choice
                    if not allow_fill_blank:
                        q['type'] = 'multiple_choice'
                        q.pop('accept_answers', None)
                    else:
                        # Normalize type names
                        if q.get('type') in ['fill_in_blank', 'fill-in-blank', 'fill_blank']:
                            q['type'] = 'fill_in_blank'
                        else:
                            q['type'] = 'multiple_choice'
                    
                    # Ensure required fields exist
                    if q['type'] == 'fill_in_blank':
                        if 'accept_answers' not in q:
                            base = q['correct_answer'].lower().strip()
                            q['accept_answers'] = [base, f"the {base}", f"a {base}"]
                        q.pop('options', None)
                    else:
                        if 'options' not in q or len(q['options']) < 4:
                            q['options'] = [
                                q.get('correct_answer', 'Option A'),
                                "Option B", "Option C", "Option D"
                            ]
                    
                    validated.append(q)

                # Append vocabulary questions as the last questions
                if vocab_questions:
                    validated.extend(vocab_questions)

                question_types = "mixed" if allow_fill_blank else "MC only"
                vocab_note = f" + {len(vocab_questions)} vocab" if vocab_questions else ""
                print(f"✓ Generated {len(validated)} questions ({question_types}{vocab_note})")
                # Item #3: random question order + correct answers spread across A-D
                return randomize_question_set(validated)
                
            else:
                raise ValueError("Could not find JSON in response")
                
        except Exception as e:
            print(f"Error generating questions: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback questions
            fallback = []
            if allow_fill_blank:
                fallback = [
                    {
                        "question": "What is the main idea of this passage?",
                        "type": "multiple_choice",
                        "options": ["A story about the topic", "A science experiment", "A history lesson", "A cooking recipe"],
                        "correct_answer": "A story about the topic",
                        "explanation": "The passage discusses this main theme.",
                        "difficulty": 1
                    },
                    {
                        "question": f"Fill in the blank: This passage is about __________.",
                        "type": "fill_in_blank",
                        "correct_answer": passage_title.lower() if passage_title else "the topic",
                        "accept_answers": [passage_title.lower() if passage_title else "the topic", "the story", "this topic"],
                        "explanation": "The passage focuses on this subject.",
                        "difficulty": 2
                    },
                    {
                        "question": "What challenge or situation is described?",
                        "type": "multiple_choice",
                        "options": ["A problem to solve", "A celebration", "A vacation", "A test"],
                        "correct_answer": "A problem to solve",
                        "explanation": "The passage describes a challenge.",
                        "difficulty": 2
                    }
                ]
            else:
                fallback = [
                    {
                        "question": "What is the main idea of this passage?",
                        "type": "multiple_choice",
                        "options": ["A story about the topic", "A science experiment", "A history lesson", "A cooking recipe"],
                        "correct_answer": "A story about the topic",
                        "explanation": "The passage discusses this main theme.",
                        "difficulty": 1
                    },
                    {
                        "question": "What challenge or situation is described?",
                        "type": "multiple_choice",
                        "options": ["A problem to solve", "A celebration", "A vacation", "A test"],
                        "correct_answer": "A problem to solve",
                        "explanation": "The passage describes a challenge.",
                        "difficulty": 2
                    },
                    {
                        "question": "What did the main character want to achieve?",
                        "type": "multiple_choice",
                        "options": ["To accomplish a goal", "To give up", "To run away", "To do nothing"],
                        "correct_answer": "To accomplish a goal",
                        "explanation": "The passage shows the character working toward something.",
                        "difficulty": 2
                    }
                ]

            # Always append vocab questions if available, even in fallback
            if vocab_questions:
                fallback.extend(vocab_questions)

            return randomize_question_set(fallback[:num_questions])

    def _extract_topics(self, main_topic, interests):
        """Extract relevant topic tags"""
        topics = [main_topic]
        topics.extend(interests[:3])
        return topics
    
    def _get_fallback_passage(self, topic, difficulty):
        """Return a basic fallback passage if AI generation fails"""
        return {
            "title": f"Introduction to {topic}",
            "content": f"This is a {difficulty} passage about {topic}. [AI generation unavailable - please try again or contact administrator]",
            "source": "fallback",
            "topic_tags": [topic],
            "word_count": 50,
            "readability_score": 5.0,
            "flesch_ease": 70.0,
            "difficulty_level": difficulty,
            "estimated_minutes": 1,
            "key_concepts": [topic],
            "vocabulary_words": []
        }

# Example usage
if __name__ == "__main__":
    # Test the content generator
    generator = ContentGenerator(api_key="your-key-here")
    
    passage = generator.generate_passage(
        topic="space exploration",
        difficulty_level="intermediate",
        target_words=250,
        user_interests=["science", "technology"]
    )
    
    print("Generated Passage:")
    print(f"Title: {passage['title']}")
    print(f"Word Count: {passage['word_count']}")
    print(f"Difficulty: {passage['difficulty_level']}")
    print(f"Readability Score: {passage['readability_score']}")