# 🤖 AI TUTOR AVATAR SYSTEM - COMPLETE IMPLEMENTATION GUIDE

## 📋 Overview

Add an animated AI tutor that:
- ✅ Greets students by name with voice
- ✅ Provides instructions with encouraging tone
- ✅ Celebrates successes
- ✅ Motivates when struggling
- ✅ Speaks using text-to-speech
- ✅ Shows text captions
- ✅ Animated avatar with expressions

---

## 🎯 STEP 1: Add Backend AI Tutor Endpoint

Add this to your `app.py`:

```python
# ============================================
# AI TUTOR ENDPOINTS
# ============================================

@app.post("/api/tutor/message")
async def get_tutor_message(request: Request):
    """Generate personalized AI tutor message"""
    try:
        data = await request.json()
        token = data.get('token')
        context = data.get('context')  # 'greeting', 'instruction', 'success', 'struggle', 'encouragement'
        student_name = data.get('student_name', 'there')
        score = data.get('score')
        lesson_number = data.get('lesson_number')
        
        # Verify token
        user_data = verify_token(token)
        
        # Generate personalized message based on context
        messages = generate_tutor_message(context, student_name, score, lesson_number)
        
        return {
            "success": True,
            "message": messages['text'],
            "emotion": messages['emotion']  # happy, encouraging, celebrating, thoughtful
        }
        
    except Exception as e:
        print(f"Error generating tutor message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def generate_tutor_message(context, student_name, score=None, lesson_number=None):
    """Generate personalized tutor messages"""
    
    first_name = student_name.split()[0] if student_name else "there"
    
    if context == 'greeting':
        messages = [
            f"Hello {first_name}! I'm so excited to learn with you today! 🌟",
            f"Welcome back, {first_name}! Ready to explore something amazing? 📚",
            f"Hi {first_name}! Great to see you! Let's make today's lesson awesome! ✨",
            f"Hey {first_name}! I'm here to help you succeed. Let's get started! 🎯"
        ]
        emotion = 'happy'
        
    elif context == 'instruction':
        messages = [
            f"Alright {first_name}, read this passage carefully. Take your time and enjoy the story! Then we'll test your understanding.",
            f"Here's your reading for today, {first_name}. Focus on the main ideas and interesting details. You've got this!",
            f"Let's dive into this passage together, {first_name}! Read at your own pace, and I'll be here when you're ready for questions.",
            f"Time to read, {first_name}! Remember, it's not a race. Understanding is what matters most!"
        ]
        emotion = 'encouraging'
        
    elif context == 'success':
        if score and score >= 80:
            messages = [
                f"Outstanding work, {first_name}! You scored {score}%! You're really mastering this! 🌟",
                f"Wow {first_name}! {score}% is fantastic! You understood that passage perfectly! 🎉",
                f"Incredible, {first_name}! {score}%! Your hard work is really paying off! Keep it up! ✨",
                f"Amazing job, {first_name}! {score}%! I'm so proud of your progress! 🏆"
            ]
            emotion = 'celebrating'
        else:
            messages = [
                f"Good effort, {first_name}! You scored {score}%. Every lesson makes you stronger!",
                f"Nice work, {first_name}! {score}% shows you're learning. Keep practicing!",
                f"You're doing great, {first_name}! {score}% is progress. Each lesson builds your skills!",
                f"Well done, {first_name}! {score}% means you're on the right track. Keep going!"
            ]
            emotion = 'encouraging'
            
    elif context == 'struggle':
        messages = [
            f"Hey {first_name}, I know this one was challenging. That's okay! Challenges help us grow. Want to try another passage?",
            f"{first_name}, even the best readers find some passages tricky. The important thing is you're trying! Let's keep practicing.",
            f"Don't worry, {first_name}! Learning has ups and downs. You're doing better than you think. Keep going!",
            f"{first_name}, remember: every expert was once a beginner. You're building important skills. I believe in you!"
        ]
        emotion = 'encouraging'
        
    elif context == 'encouragement':
        messages = [
            f"You're making real progress, {first_name}! Every word you read makes you a better reader!",
            f"Keep up the fantastic work, {first_name}! You're building skills that will help you forever!",
            f"{first_name}, I can see how much you're improving! You should be proud of yourself!",
            f"You're doing amazing, {first_name}! Each lesson brings you closer to your goals!"
        ]
        emotion = 'happy'
        
    elif context == 'milestone':
        if lesson_number and lesson_number % 10 == 0:
            messages = [
                f"🎉 WOW {first_name}! You've completed {lesson_number} lessons! That's incredible dedication!",
                f"🏆 Amazing milestone, {first_name}! {lesson_number} lessons shows real commitment to learning!",
                f"🌟 {first_name}, {lesson_number} lessons completed! You're unstoppable! Keep this momentum going!"
            ]
        else:
            messages = [
                f"Great progress, {first_name}! Lesson {lesson_number} done! You're on a roll!",
                f"Another lesson complete, {first_name}! That's lesson {lesson_number}! Keep it up!",
                f"Excellent, {first_name}! Lesson {lesson_number} is behind you! Onward and upward!"
            ]
        emotion = 'celebrating'
    
    else:
        messages = [f"Great to have you here, {first_name}! Let's learn together!"]
        emotion = 'happy'
    
    import random
    return {
        'text': random.choice(messages),
        'emotion': emotion
    }
```

---

## 🎯 STEP 2: Add Avatar HTML to reading.html

Add this right after the `<body>` tag in reading.html:

```html
<!-- AI Tutor Avatar -->
<div id="aiTutor" class="ai-tutor hidden">
    <div class="tutor-avatar">
        <div class="avatar-face" id="avatarFace">
            <!-- Animated face -->
            <div class="eyes">
                <div class="eye left"></div>
                <div class="eye right"></div>
            </div>
            <div class="mouth" id="avatarMouth"></div>
        </div>
    </div>
    <div class="tutor-speech-bubble">
        <div class="speech-text" id="tutorMessage"></div>
        <button class="speech-continue" id="continueBtntutor" onclick="hideTutor()">
            Got it! ✓
        </button>
    </div>
    <button class="tutor-close" onclick="hideTutor()">✕</button>
    <button class="tutor-mute" id="muteButton" onclick="toggleMute()">
        <span id="muteIcon">🔊</span>
    </button>
</div>
```

---

## 🎯 STEP 3: Add Avatar CSS

Add this to your `<style>` section in reading.html:

```css
/* ============================================
   AI TUTOR AVATAR STYLES
   ============================================ */

.ai-tutor {
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    z-index: 1000;
    display: flex;
    align-items: flex-end;
    gap: 1rem;
    animation: slideInUp 0.5s ease;
}

.ai-tutor.hidden {
    display: none;
}

@keyframes slideInUp {
    from {
        transform: translateY(100px);
        opacity: 0;
    }
    to {
        transform: translateY(0);
        opacity: 1;
    }
}

/* Avatar Face */
.tutor-avatar {
    width: 120px;
    height: 120px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
    border: 4px solid white;
    animation: bounce 2s infinite;
}

@keyframes bounce {
    0%, 20%, 50%, 80%, 100% {
        transform: translateY(0);
    }
    40% {
        transform: translateY(-10px);
    }
    60% {
        transform: translateY(-5px);
    }
}

.avatar-face {
    width: 80%;
    height: 80%;
    position: relative;
}

/* Eyes */
.eyes {
    display: flex;
    justify-content: space-around;
    margin-top: 20px;
    gap: 15px;
}

.eye {
    width: 16px;
    height: 16px;
    background: white;
    border-radius: 50%;
    position: relative;
    animation: blink 4s infinite;
}

.eye::after {
    content: '';
    position: absolute;
    width: 8px;
    height: 8px;
    background: #2C3E50;
    border-radius: 50%;
    top: 4px;
    left: 4px;
    animation: lookAround 3s infinite;
}

@keyframes blink {
    0%, 90%, 100% {
        height: 16px;
    }
    95% {
        height: 2px;
    }
}

@keyframes lookAround {
    0%, 100% {
        left: 4px;
    }
    25% {
        left: 6px;
    }
    75% {
        left: 2px;
    }
}

/* Mouth */
.mouth {
    width: 30px;
    height: 15px;
    border: 3px solid white;
    border-top: none;
    border-radius: 0 0 30px 30px;
    margin: 15px auto 0;
    animation: talk 0.5s infinite;
}

.mouth.happy {
    animation: smile 0.5s ease;
    border-radius: 0 0 30px 30px;
}

.mouth.celebrating {
    border-radius: 30px 30px 0 0;
    border-top: 3px solid white;
    border-bottom: none;
    animation: laugh 0.3s infinite;
}

@keyframes talk {
    0%, 100% {
        height: 15px;
    }
    50% {
        height: 20px;
    }
}

@keyframes smile {
    to {
        width: 35px;
        height: 18px;
    }
}

@keyframes laugh {
    0%, 100% {
        transform: scaleX(1);
    }
    50% {
        transform: scaleX(1.2);
    }
}

/* Speech Bubble */
.tutor-speech-bubble {
    background: white;
    padding: 1.5rem;
    border-radius: 16px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
    max-width: 350px;
    position: relative;
    animation: fadeIn 0.3s ease;
}

.tutor-speech-bubble::before {
    content: '';
    position: absolute;
    bottom: 20px;
    right: -15px;
    width: 0;
    height: 0;
    border-left: 15px solid white;
    border-top: 10px solid transparent;
    border-bottom: 10px solid transparent;
}

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: scale(0.8);
    }
    to {
        opacity: 1;
        transform: scale(1);
    }
}

.speech-text {
    font-size: 1.1rem;
    line-height: 1.6;
    color: var(--text-primary);
    margin-bottom: 1rem;
    font-weight: 500;
}

.speech-continue {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    width: 100%;
    transition: all 0.3s;
}

.speech-continue:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

/* Control Buttons */
.tutor-close,
.tutor-mute {
    position: absolute;
    top: -10px;
    background: white;
    border: 2px solid #E0E0E0;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 1rem;
    transition: all 0.3s;
}

.tutor-close {
    right: -10px;
    color: #E74C3C;
}

.tutor-mute {
    left: -10px;
}

.tutor-close:hover {
    background: #E74C3C;
    color: white;
    transform: rotate(90deg);
}

.tutor-mute:hover {
    background: var(--navy-primary);
    color: white;
    transform: scale(1.1);
}

/* Mobile Responsive */
@media (max-width: 768px) {
    .ai-tutor {
        bottom: 1rem;
        right: 1rem;
        left: 1rem;
        flex-direction: column;
        align-items: center;
    }
    
    .tutor-avatar {
        width: 100px;
        height: 100px;
    }
    
    .tutor-speech-bubble {
        max-width: 100%;
    }
    
    .tutor-speech-bubble::before {
        bottom: -15px;
        right: 50%;
        transform: translateX(50%);
        border-left: 10px solid transparent;
        border-right: 10px solid transparent;
        border-top: 15px solid white;
        border-bottom: none;
    }
}
```

---

## 🎯 STEP 4: Add JavaScript Functions

Add this JavaScript to reading.html (in `<script>` section):

```javascript
// ============================================
// AI TUTOR SYSTEM
// ============================================

let isMuted = false;
let speechSynthesis = window.speechSynthesis;

// Show tutor with message
async function showTutor(context, additionalData = {}) {
    const token = localStorage.getItem('token');
    const studentName = localStorage.getItem('studentName') || 'there';
    
    try {
        const response = await fetch('/api/tutor/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: token,
                context: context,
                student_name: studentName,
                ...additionalData
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            displayTutorMessage(data.message, data.emotion);
        }
    } catch (error) {
        console.error('Error getting tutor message:', error);
        // Fallback message
        displayTutorMessage("Let's do great work together!", 'happy');
    }
}

function displayTutorMessage(message, emotion = 'happy') {
    const tutor = document.getElementById('aiTutor');
    const messageEl = document.getElementById('tutorMessage');
    const mouthEl = document.getElementById('avatarMouth');
    
    // Show tutor
    tutor.classList.remove('hidden');
    
    // Set message
    messageEl.textContent = message;
    
    // Set mouth emotion
    mouthEl.className = 'mouth ' + emotion;
    
    // Speak message
    if (!isMuted) {
        speak(message);
    }
}

function speak(text) {
    // Cancel any ongoing speech
    speechSynthesis.cancel();
    
    // Create utterance
    const utterance = new SpeechSynthesisUtterance(text);
    
    // Configure voice
    utterance.rate = 0.9;  // Slightly slower for clarity
    utterance.pitch = 1.1;  // Slightly higher for friendly tone
    utterance.volume = 1.0;
    
    // Try to use a pleasant voice
    const voices = speechSynthesis.getVoices();
    const preferredVoice = voices.find(voice => 
        voice.name.includes('Google') || 
        voice.name.includes('Female') ||
        voice.name.includes('Samantha')
    );
    
    if (preferredVoice) {
        utterance.voice = preferredVoice;
    }
    
    // Speak
    speechSynthesis.speak(utterance);
}

function hideTutor() {
    const tutor = document.getElementById('aiTutor');
    tutor.classList.add('hidden');
    
    // Stop speech
    speechSynthesis.cancel();
}

function toggleMute() {
    isMuted = !isMuted;
    const muteIcon = document.getElementById('muteIcon');
    muteIcon.textContent = isMuted ? '🔇' : '🔊';
    
    if (isMuted) {
        speechSynthesis.cancel();
    }
}

// ============================================
// INTEGRATION POINTS IN LESSON FLOW
// ============================================

// Call these at appropriate times:

// 1. When lesson loads
window.addEventListener('load', function() {
    // Load voices
    if (speechSynthesis.onvoiceschanged !== undefined) {
        speechSynthesis.onvoiceschanged = () => {};
    }
    
    // Greet student after 1 second
    setTimeout(() => {
        showTutor('greeting');
    }, 1000);
    
    // Show instructions after greeting (after 6 seconds)
    setTimeout(() => {
        showTutor('instruction');
    }, 6000);
});

// 2. When student submits answers - UPDATE YOUR submitAnswers FUNCTION:
async function submitAnswers() {
    // ... your existing code to calculate score ...
    
    const score = calculateScore();  // Your score calculation
    const lessonNumber = getCurrentLessonNumber();  // Your lesson number
    
    // Show tutor feedback based on score
    if (score >= 80) {
        showTutor('success', { score: score, lesson_number: lessonNumber });
    } else if (score < 60) {
        showTutor('struggle', { score: score });
    } else {
        showTutor('success', { score: score });
    }
    
    // Check for milestones
    if (lessonNumber % 10 === 0) {
        setTimeout(() => {
            showTutor('milestone', { lesson_number: lessonNumber });
        }, 3000);
    }
}

// 3. Random encouragement during reading (optional)
function startEncouragementTimer() {
    // Show encouragement every 2 minutes while reading
    setInterval(() => {
        if (!document.getElementById('aiTutor').classList.contains('hidden')) {
            return;  // Don't interrupt if tutor is already showing
        }
        
        const random = Math.random();
        if (random > 0.7) {  // 30% chance every 2 minutes
            showTutor('encouragement');
        }
    }, 120000);  // 2 minutes
}

// Start encouragement timer
startEncouragementTimer();
```

---

## 🚀 DEPLOYMENT

### Step 1: Update Backend
```bash
# Add the tutor endpoints to app.py
git add app.py
git commit -m "Add AI tutor message generation endpoint"
```

### Step 2: Update Frontend
```bash
# Add HTML, CSS, and JavaScript to reading.html
git add reading.html
git commit -m "Add AI tutor avatar with voice and animations"
```

### Step 3: Deploy
```bash
git push origin main
```

---

## ✅ EXPECTED BEHAVIOR

### **When Lesson Loads:**
1. Avatar slides up from bottom right
2. "Hello [Name]! I'm so excited to learn with you today! 🌟"
3. Voice speaks the greeting
4. After 5 seconds: "Alright [Name], read this passage carefully..."

### **When Student Completes (80%+):**
1. Avatar appears with celebration
2. "Outstanding work, [Name]! You scored 90%! 🌟"
3. Mouth animates to celebrating expression
4. Voice speaks encouragement

### **When Student Struggles (<60%):**
1. Avatar appears with encouraging expression
2. "Hey [Name], I know this one was challenging. That's okay!"
3. Supportive, gentle tone
4. Voice speaks motivation

### **Milestone (Every 10 Lessons):**
1. Special celebration animation
2. "🎉 WOW [Name]! You've completed 10 lessons!"
3. Extra enthusiastic voice

---

## 🎨 CUSTOMIZATION

### Change Avatar Color:
```css
.tutor-avatar {
    background: linear-gradient(135deg, #FF6B6B 0%, #FFE66D 100%);
}
```

### Change Voice Settings:
```javascript
utterance.rate = 1.0;  // Speed (0.1 to 10)
utterance.pitch = 1.2;  // Pitch (0 to 2)
```

### Add More Messages:
Edit the `generate_tutor_message()` function in app.py to add more variety.

---

## 📱 MOBILE SUPPORT

- Avatar repositions to bottom center
- Speech bubble appears above avatar
- Touch-friendly buttons
- Smaller avatar size (100px instead of 120px)

---

## 🎯 TESTING

1. **Greeting:** Reload page → Should greet by name with voice
2. **Instructions:** Wait 6 seconds → Should give instructions
3. **Success:** Get 80%+ → Should celebrate
4. **Struggle:** Get <60% → Should encourage
5. **Mute:** Click 🔊 → Should mute voice
6. **Close:** Click ✕ → Should hide avatar

---

## 🌟 FEATURES

✅ Personalized greetings
✅ Context-aware messages
✅ Text-to-speech with pleasant voice
✅ Animated avatar with emotions
✅ Speech bubble with text captions
✅ Mute/unmute control
✅ Close button
✅ Responsive design
✅ Smooth animations
✅ Celebration for milestones
✅ Encouragement for struggling students
✅ Instructions at right time

Your students will love learning with their AI tutor! 🎉