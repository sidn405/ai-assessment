# AI Content Generation Pipeline
# Generates reading passages and comprehension questions using OpenAI

from openai import OpenAI
import json
import os
from typing import List, Dict, Optional
from readability import analyze_readability
import re

class ContentGenerator:
    def __init__(self, api_key=None):
        """Initialize with OpenAI API key"""
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        # NEW API - Create client
        self.client = OpenAI(api_key=self.api_key)
        
    def _get_cultural_context_guidance(self, age, grade_band):
        """
        Provides age-appropriate cultural context guidance
        """
        contexts = {
            'elementary': {
                'settings': ['playground', 'classroom', 'community center', 'library', 'park', 'corner store'],
                'characters': ['students', 'teachers', 'parents', 'grandparents', 'librarians', 'coaches'],
                'themes': ['friendship', 'learning', 'helping others', 'trying new things', 'community'],
                'avoid': ['Keep it simple and positive', 'No complex social issues', 'Focus on everyday experiences']
            },
            'middle': {
                'settings': ['school', 'community center', 'basketball court', 'tech lab', 'after-school program', 'local business'],
                'characters': ['students', 'mentors', 'coaches', 'small business owners', 'community leaders', 'older siblings'],
                'themes': ['discovering talents', 'overcoming challenges', 'leadership', 'innovation', 'community service'],
                'avoid': ['Avoid trauma', 'No criminal justice references', 'Focus on growth and potential']
            },
            'high': {
                'settings': ['high school', 'internships', 'community college', 'local businesses', 'volunteer programs', 'STEM programs'],
                'characters': ['students', 'mentors', 'entrepreneurs', 'professionals', 'college students', 'counselors'],
                'themes': ['career exploration', 'college prep', 'leadership', 'social justice', 'entrepreneurship', 'identity'],
                'avoid': ['Respectful of complex realities', 'Focus on agency and empowerment', 'No deficit narratives']
            },
            'adult': {
                'settings': ['workplace', 'community organizations', 'professional settings', 'entrepreneurship', 'continuing education'],
                'characters': ['professionals', 'entrepreneurs', 'community leaders', 'working parents', 'returning students'],
                'themes': ['career advancement', 'community building', 'economic mobility', 'lifelong learning', 'giving back'],
                'avoid': ['Acknowledge challenges without dwelling', 'Focus on resilience and success', 'Asset-based approach']
            }
        }
        
        # Map grade to category
        if grade_band in ['pre-k', 'kindergarten', '1st', '2nd', '3rd', '4th', '5th', 'elementary']:
            category = 'elementary'
        elif grade_band in ['6th', '7th', '8th', 'middle']:
            category = 'middle'
        elif grade_band in ['9th', '10th', '11th', '12th', 'high']:
            category = 'high'
        else:
            category = 'adult'
        
        return contexts.get(category, contexts['elementary'])
    
    
        
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
    
    def generate_passage(self, topic, difficulty_level, word_count_min, word_count_max, user_interests, age=None, grade_band=None):
        """Generate educational passage using GPT-4 with dynamic word count"""
        
        # Calculate target from range
        import random
        target_words = (word_count_min + word_count_max) // 2
        
        # Build enhanced prompt
        prompt = f"""
        Generate an engaging reading passage for a student:
        
        Student Profile:
        - Age: {age} years old
        - Grade Level: {grade_band}
        - Reading Difficulty: {difficulty_level}
        - Interests: {', '.join(user_interests) if user_interests else 'general topics'}
        - Topic: {topic}
        
        Requirements:
        - Word count: approximately {target_words} words
        - Use age-appropriate vocabulary for a {age}-year-old in {grade_band}
        - Make it engaging and relatable to their interests
        - Include vivid details and clear structure
        - Difficulty level: {difficulty_level}
        
        The passage should be educational but fun, matching their grade level expectations.
        """
        
        # Add after line 69
        cultural_context = self._get_cultural_context_guidance(age, grade_band)
        
        # Include in prompt
        prompt += f"""
        
        CULTURAL CONTEXT FOR THIS AGE/GRADE:
        Settings to use: {', '.join(cultural_context['settings'])}
        Characters to include: {', '.join(cultural_context['characters'])}
        Appropriate themes: {', '.join(cultural_context['themes'])}
        What to avoid: {', '.join(cultural_context['avoid'])}
        """
        
        # ========== UPDATED PROMPT WITH SINGLE INTEREST FOCUS ==========
        prompt = f"""Write a SHORT STORY (narrative) about {topic} featuring African American characters.

        Student Profile:
        - Age: {age} years old
        - Grade Level: {grade_band}
        - Reading Difficulty: {difficulty_level}
        - PRIMARY INTEREST/TOPIC: {topic}
        
        IMPORTANT - TOPIC FOCUS:
        - Focus ONLY on {topic}
        - Do NOT combine with other interests or topics
        - Provide variety by exploring different aspects/subtopics within {topic}
        - Make it fresh and engaging - avoid repetitive storylines
        
        CULTURAL CONTEXT:
        - Set in an urban community (city neighborhood, public spaces)
        - Feature authentic Black characters with realistic names
        - Show positive community interactions and support
        - Include cultural elements (music, food, celebrations, traditions)
        - Demonstrate resilience and success
        
        CHARACTER NAME RULES — CRITICAL:
        - NEVER use the name "Jamal" — it has been overused in recent stories
        - Choose a DIFFERENT name each time from this diverse list:
          Marcus, Aaliyah, Devon, Zoe, Jordan, Imani, Malik, Destiny, 
          Andre, Jasmine, Elijah, Simone, Isaiah, Nia, Jaylen, Amara,
          Darius, Keisha, Trey, Brianna, Cameron, Layla, Xavier, Jade
        - Vary the name with every passage — do not reuse the same name twice in a row
        
        SETTING RULES — CRITICAL:
        - Do NOT default to "community center" — this setting has been overused
        - Rotate settings: school classroom, backyard, library, park, kitchen/home,
          art class, basketball court, music studio, garden, friend's house, bookstore,
          science fair, sports field, after-school program, grandma's house, corner store
        - Pick a setting that fits naturally with the topic: {topic}
        
        HARD WORD COUNT RULE:
        - The "content" field MUST be EXACTLY {target_words} words.
        - Count words by splitting on spaces.
        - Before you respond, self-check the word count and adjust until it is exactly {target_words}.
        
        STORY STRUCTURE:
        - Character: African American protagonist facing a relatable challenge
        - Setting: Urban neighborhood, school, community center, park, library, etc.
        - Plot: Beginning → problem/challenge → resolution through creativity/effort/community
        - Include at least one line of dialogue
        - Show positive outcome and growth
        - NO criminal justice, violence, or trauma content
        - Focus on strengths, not struggles with poverty
        
        TOPIC FOCUS: {topic}
        - Stay focused on this topic only
        - Make it educational but engaging
        - Connect to their real-world experiences
        - Show how the topic matters in their community
        
        AGE-APPROPRIATE VOCABULARY:
        - Use {difficulty_level} level vocabulary
        - Include challenging academic words they can learn
        - Define any cultural references they might not know
        
        Return your response as a JSON object:
        {{
            "title": "Engaging title about {topic}",
            "content": "The full story (EXACTLY {target_words} words)",
            "key_concepts": ["concept1", "concept2", "concept3"],
            "vocabulary_words": [
                {{"word": "challenging_word1", "definition": "simple, clear definition"}},
                {{"word": "challenging_word2", "definition": "simple, clear definition"}},
                ... (minimum 5-10 words based on difficulty level)
            ]
        }}
        
        REMINDER: This story should feel real and relatable to an African American student from an urban community. Focus on positive experiences, community strength, and educational growth."""
        
        try:
            # NEW API SYNTAX
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert educational content creator specializing in culturally relevant, trauma-informed content for African American students from underserved communities.
                        
                        CRITICAL CULTURAL GUIDELINES:
                        1. **Authentic Representation**: 
                           - Use diverse Black characters with authentic names and experiences
                           - Include positive role models from the community (teachers, coaches, entrepreneurs, artists)
                           - Show families with different structures (single parents, grandparents, extended family)
                           - Represent urban/neighborhood settings authentically and positively
                        
                        2. **TRAUMA-INFORMED - AVOID**:
                           - Police encounters or criminal justice system references
                           - Violence, gangs, or crime as plot elements
                           - Poverty as a defining characteristic (it's context, not identity)
                           - Deficit narratives or stereotypes
                           - Drug-related content
                        
                        3. **EMPOWERING THEMES**:
                           - Community strength and mutual support
                           - Overcoming challenges through creativity and resilience
                           - Cultural pride and heritage
                           - Educational and career success
                           - Arts, music, sports as pathways
                           - Entrepreneurship and innovation
                           - STEM and creative fields
                        
                        4. **RELATABLE CONTEXTS**:
                           - Urban neighborhoods, public transportation, corner stores
                           - Community centers, parks, libraries, churches
                           - Barbershops, hair salons, family gatherings
                           - Basketball courts, community gardens
                           - Local heroes and mentors
                           - Music (hip-hop, R&B), art, fashion, sports culture
                        
                        5. **VOCABULARY EXTRACTION**:
                           Extract ALL challenging words from your passage. A good passage should have AT LEAST 5-10 vocabulary words.
                           
                           Examples by level:
                           - Elementary: "ecosystem", "gravity", "nutrient", "habitat", "diverse"
                           - Intermediate: "phenomenon", "inevitable", "perspective", "substantial", "comprehensive"  
                           - High School: "culmination", "juxtaposition", "paradigm", "synthesis", "nuance"
                           - Adult: "epistemology", "hegemony", "empirical", "ubiquitous", "pragmatic"
                        
                        STORY REQUIREMENTS:
                        - Focus on ONE topic at a time
                        - Include a character, setting, and plot (beginning → problem → resolution)
                        - Make it engaging and age-appropriate
                        - Show positive outcomes through effort, creativity, or community support
                        - Include at least one line of dialogue
                        - NO articles, definitions, or lectures - tell a STORY"""
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.35,
                max_tokens=2500,
                timeout=60
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            passage_data = json.loads(content)
            
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

    def generate_story_image(self, title, content, topic, grade_band):
        """
        Generate a single child-friendly illustration for a story.
        Only call this for younger grade bands (see is_young_learner) - image
        generation costs real money per call, so we don't want it firing for
        every passage at every grade level.

        Returns a data URL (data:image/png;base64,...) on success, or None on
        any failure (callers should treat a missing image as non-fatal - the
        story still needs to render without it).

        NOTE: dall-e-3 was retired from the OpenAI API on May 12, 2026.
        This uses gpt-image-1-mini (the cost-effective GPT Image model) instead.
        Bump to "gpt-image-1" or "gpt-image-2" below if quality needs to go up -
        gpt-image-2 in particular allows custom resolutions instead of the
        fixed 1024x1024 / 1024x1536 / 1536x1024 options.

        IMPORTANT: unlike dall-e-3, GPT Image models ALWAYS return base64 image
        data (no .url field, no response_format param) - and your OpenAI org
        needs to complete Organization Verification before this model will work
        at all. See: https://platform.openai.com/settings/organization/general
        """
        try:
            # Keep the prompt short and visual. Explicitly avoid asking for any
            # text/words in the image since image models render text poorly and
            # it's not needed here - the story text is already on the page.
            snippet = (content or '')[:300]
            image_prompt = (
                f"A warm, friendly children's storybook illustration. "
                f"Story title: '{title}'. Topic: {topic}. "
                f"Scene inspired by: {snippet} "
                f"Style: simple flat-color storybook art, bright and cheerful, "
                f"no text or letters anywhere in the image, single clear scene, "
                f"safe and appropriate for young children."
            )

            response = self.client.images.generate(
                model="gpt-image-1-mini",
                prompt=image_prompt,
                size="1024x1024",
                quality="low",
                n=1
            )

            b64_data = response.data[0].b64_json
            if not b64_data:
                return None

            # GPT Image models only return base64 - build a data URL so the
            # frontend <img> tag works exactly like it would with a real URL,
            # and so we follow the same storage pattern already used for
            # profile photos elsewhere in app.py (data URL stored as TEXT).
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
        
        # Pick one vocab word for a dedicated vocabulary question.
        # We generate num_questions - 1 comprehension questions from the AI
        # then append the vocab question at the end so it's always present.
        vocab_question = None
        comprehension_count = num_questions

        if vocabulary_words and len(vocabulary_words) > 0:
            import random
            # Pick a word — prefer words with clean single-word definitions
            candidates = [v for v in vocabulary_words if v.get('word') and v.get('definition')]
            if candidates:
                vocab_entry = random.choice(candidates)
                vocab_word = vocab_entry['word'].strip()
                correct_def = vocab_entry['definition'].strip()

                # Build 3 distractor definitions from other vocab words in the list
                other_defs = [
                    v['definition'].strip() for v in candidates
                    if v['word'] != vocab_word and v.get('definition')
                ]
                random.shuffle(other_defs)
                distractors = other_defs[:3]

                # Pad with generic distractors if not enough vocab words
                generic = [
                    "A type of weather condition",
                    "Something you eat for breakfast",
                    "A place where people swim",
                    "A very loud sound",
                    "Moving very slowly",
                ]
                while len(distractors) < 3:
                    distractors.append(generic[len(distractors)])

                options = [correct_def] + distractors
                random.shuffle(options)

                vocab_question = {
                    "question": f'What does the word "{vocab_word}" mean in the story?',
                    "type": "multiple_choice",
                    "options": options,
                    "correct_answer": correct_def,
                    "explanation": f'"{vocab_word}" means: {correct_def}',
                    "difficulty": 1,
                    "is_vocabulary": True
                }
                # Generate one fewer from AI so total stays at num_questions
                comprehension_count = num_questions - 1

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
    - Provide "accept_answers" array with variations (lowercase)
    - Keep answers SHORT (1-3 words max)
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

                # Append vocabulary question as the last question
                if vocab_question:
                    validated.append(vocab_question)

                question_types = "mixed" if allow_fill_blank else "MC only"
                vocab_note = " + 1 vocab" if vocab_question else ""
                print(f"✓ Generated {len(validated)} questions ({question_types}{vocab_note})")
                return validated
                
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

            # Always append vocab question if available, even in fallback
            if vocab_question:
                fallback.append(vocab_question)

            return fallback[:num_questions]
        """
        Generate comprehension questions with optional fill-in-blank
        
        Args:
            passage_text: The passage content
            passage_title: Title of the passage  
            num_questions: Number of questions (default 4)
            allow_fill_blank: If True, mix MC and fill-in-blank. If False, MC only.
        """
        
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
    - Provide "accept_answers" array with variations (lowercase)
    - Keep answers SHORT (1-3 words max)
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
    
    {type_instruction.format(num_questions=num_questions)}
    
    Return as JSON array:
    {json_example}
    
    IMPORTANT:
    - Vary difficulty (easier questions first)
    - Cover different aspects of the passage
    - Make questions age-appropriate
    - Test different comprehension skills
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
                for q in questions[:num_questions]:
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
                        # Ensure accept_answers exists
                        if 'accept_answers' not in q:
                            base = q['correct_answer'].lower().strip()
                            q['accept_answers'] = [base, f"the {base}", f"a {base}"]
                        # Remove options field if present
                        q.pop('options', None)
                    else:
                        # Multiple choice - ensure options exist
                        if 'options' not in q or len(q['options']) < 4:
                            q['options'] = [
                                q.get('correct_answer', 'Option A'),
                                "Option B",
                                "Option C", 
                                "Option D"
                            ]
                    
                    validated.append(q)
                
                question_types = "mixed" if allow_fill_blank else "MC only"
                print(f"✓ Generated {len(validated)} questions ({question_types})")
                return validated
                
            else:
                raise ValueError("Could not find JSON in response")
                
        except Exception as e:
            print(f"Error generating questions: {e}")
            import traceback
            traceback.print_exc()
            
            # Fallback questions based on allow_fill_blank
            if allow_fill_blank:
                # Mix of MC and fill-in-blank
                return [
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
                    },
                    {
                        "question": "The main character wanted to __________.",
                        "type": "fill_in_blank",
                        "correct_answer": "achieve a goal",
                        "accept_answers": ["achieve a goal", "reach a goal", "accomplish something", "succeed"],
                        "explanation": "The passage shows the character working toward something.",
                        "difficulty": 2
                    }
                ]

            # Always append vocab question if available, even in fallback
            if vocab_question:
                fallback.append(vocab_question)

            return fallback[:num_questions]

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