# AI Content Generation Pipeline
# Generates reading passages and comprehension questions using OpenAI

import openai
import json
from typing import List, Dict, Optional
from readability import analyze_readability

class ContentGenerator:
    """
    Generates educational reading content using AI with proper difficulty levels,
    topics, and comprehension questions.
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        openai.api_key = api_key
    
    def generate_passage(
        self,
        topic: str,
        difficulty_level: str,
        target_words: int = 200,
        user_interests: List[str] = None
    ) -> Dict:
        """
        Generate a reading passage with specified parameters.
        
        Args:
            topic: Main topic/subject
            difficulty_level: 'beginner', 'intermediate', 'advanced'
            target_words: Target word count
            user_interests: List of user interest tags
        
        Returns:
            Dictionary with passage data
        """
        
        # Map difficulty to grade level guidance
        grade_guidance = {
            "beginner": "3rd-5th grade reading level. Use simple sentences and common words.",
            "intermediate": "6th-8th grade reading level. Use varied sentence structure and moderate vocabulary.",
            "advanced": "9th-12th grade reading level. Use complex sentences and advanced vocabulary."
        }
        
        interests_context = ""
        if user_interests:
            interests_context = f"\nStudent interests include: {', '.join(user_interests)}. Try to connect the content to these interests when relevant."
        
        prompt = f"""Create an educational reading passage about {topic}.

Requirements:
- {grade_guidance.get(difficulty_level, grade_guidance['intermediate'])}
- Approximately {target_words} words
- Engaging and informative
- Include specific facts and details
- Appropriate for students learning to improve reading skills{interests_context}

The passage should be interesting and educational, teaching something meaningful about the topic.

Format your response as JSON:
{{
    "title": "Engaging Title",
    "content": "The full passage text...",
    "key_concepts": ["concept1", "concept2", "concept3"],
    "vocabulary_words": [
        {{"word": "word1", "definition": "simple definition"}},
        {{"word": "word2", "definition": "simple definition"}}
    ]
}}"""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert educational content creator specializing in literacy development."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=1500
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            passage_data = json.loads(content)
            
            # Analyze readability
            readability = analyze_readability(passage_data['content'])
            
            # Add metadata
            passage_data.update({
                "source": "AI",
                "topic_tags": self._extract_topics(topic, user_interests),
                "word_count": readability['word_count'],
                "readability_score": readability['flesch_kincaid_grade'],
                "flesch_ease": readability['flesch_reading_ease'],
                "difficulty_level": difficulty_level,
                "estimated_minutes": readability['estimated_minutes'],
                "actual_difficulty": readability['difficulty_level'],  # Actual vs requested
                "grade_band": readability['grade_band']
            })
            
            return passage_data
            
        except Exception as e:
            print(f"Error generating passage: {e}")
            # Return a fallback passage
            return self._get_fallback_passage(topic, difficulty_level)
    
    def generate_comprehension_questions(
        self,
        passage_text: str,
        passage_title: str,
        num_questions: int = 5
    ) -> List[Dict]:
        """
        Generate comprehension questions for a passage.
        
        Includes mix of:
        - Main idea questions
        - Detail questions
        - Inference questions
        - Vocabulary questions
        """
        
        prompt = f"""Create {num_questions} comprehension questions for this reading passage:

Title: {passage_title}

Passage:
{passage_text}

Create a mix of question types:
1. Main idea (what is the passage mainly about?)
2. Details (specific facts from the passage)
3. Inference (what can we conclude?)
4. Vocabulary in context (if applicable)

Format as JSON array:
[
    {{
        "question": "Question text here?",
        "type": "main_idea",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": "Option A",
        "explanation": "Why this answer is correct",
        "difficulty": 1
    }}
]

Make sure correct answers are randomly distributed (not all A or B).
Difficulty scale: 1=easy, 2=medium, 3=hard"""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at creating reading comprehension assessments."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            questions = json.loads(content)
            return questions
            
        except Exception as e:
            print(f"Error generating questions: {e}")
            return self._get_fallback_questions(passage_title)
    
    def generate_discussion_prompt(self, passage_text: str, user_question: str = None) -> str:
        """
        Generate engaging discussion prompts or respond to user questions about a passage.
        """
        
        if user_question:
            prompt = f"""A student just read this passage:

{passage_text[:500]}...

They asked: "{user_question}"

Provide a helpful, encouraging response that:
1. Answers their question clearly
2. Connects back to the passage
3. Encourages deeper thinking
4. Uses positive, supportive language

Keep response under 150 words."""
        else:
            prompt = f"""A student just finished reading this passage:

{passage_text[:500]}...

Generate 3 engaging discussion questions that encourage them to think deeper about what they read.
Questions should be open-ended and appropriate for learning readers.

Format as JSON array: ["Question 1?", "Question 2?", "Question 3?"]"""
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Faster for discussion
                messages=[
                    {"role": "system", "content": "You are an encouraging literacy tutor."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=300
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"Error generating discussion: {e}")
            return "That's a great question! What do you think the author wanted us to learn from this passage?"
    
    def provide_writing_feedback(
        self,
        prompt: str,
        user_response: str,
        passage_context: str = None
    ) -> Dict:
        """
        Provide constructive feedback on student writing.
        Always encouraging, never shaming.
        """
        
        context_text = f"\n\nThis response is about a passage they read:\n{passage_context[:300]}..." if passage_context else ""
        
        feedback_prompt = f"""A student responded to this writing prompt:

Prompt: {prompt}

Student's response:
{user_response}
{context_text}

Provide encouraging, constructive feedback that:
1. Highlights what they did well (be specific!)
2. Gently suggests 1-2 improvements
3. Uses positive, growth-oriented language (never "wrong" or "bad")
4. Ends with encouragement

Also suggest a revised version that shows the improvements.

Format as JSON:
{{
    "positive_feedback": "What they did well...",
    "suggestions": ["Suggestion 1", "Suggestion 2"],
    "revised_example": "Improved version of their response...",
    "encouragement": "Final encouraging statement",
    "score": 75
}}

Score is 0-100 based on: clarity, completeness, and connection to prompt."""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a supportive writing tutor who believes every student can improve."
                    },
                    {"role": "user", "content": feedback_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            return json.loads(content)
            
        except Exception as e:
            print(f"Error generating writing feedback: {e}")
            return {
                "positive_feedback": "Great job getting your ideas down!",
                "suggestions": ["Try adding more details to support your main point."],
                "revised_example": user_response,
                "encouragement": "You're making progress - keep writing!",
                "score": 70
            }
    
    def _extract_topics(self, main_topic: str, interests: List[str] = None) -> List[str]:
        """Extract topic tags for categorization."""
        topics = [main_topic.lower()]
        if interests:
            topics.extend([i.lower() for i in interests])
        return list(set(topics))  # Remove duplicates
    
    def _get_fallback_passage(self, topic: str, difficulty: str) -> Dict:
        """Fallback passage if AI generation fails."""
        return {
            "title": f"Introduction to {topic}",
            "content": f"This is a beginner passage about {topic}. [AI generation unavailable - please try again or contact administrator]",
            "key_concepts": [topic],
            "vocabulary_words": [],
            "source": "AI",
            "topic_tags": [topic.lower()],
            "word_count": 50,
            "difficulty_level": difficulty
        }
    
    def _get_fallback_questions(self, title: str) -> List[Dict]:
        """Fallback questions if AI generation fails."""
        return [
            {
                "question": f"What is the main topic of '{title}'?",
                "type": "main_idea",
                "options": ["The topic mentioned", "Something else", "Another topic", "Different subject"],
                "correct_answer": "The topic mentioned",
                "explanation": "The passage focuses on this topic.",
                "difficulty": 1
            }
        ]

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