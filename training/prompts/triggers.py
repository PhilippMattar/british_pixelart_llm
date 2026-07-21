"""Hand-written prompts for the bank (PLAN.md §6.2).

Everyday, conversational questions that open instruction sets under-represent — casual chat,
opinions, dialect-adjacent topics (weather, food, travel) that give the personas room to
perform. Mixed into the Dolly sample by build_bank.py. Kept generic (both personas answer the
same bank); the persona is style applied on top, not a different question.
"""

TRIGGERS: list[str] = [
    # everyday / casual
    "How's it going today?",
    "I'm having one of those days. Any words of wisdom?",
    "What's a good way to unwind after work?",
    "I keep procrastinating. How do I actually get started?",
    "Talk me into going for a walk.",
    "I can't sleep. What should I do?",
    "My phone battery dies by lunchtime. Any tips?",
    "How do I stop checking my emails on weekends?",
    "I'm bored on my lunch break. Entertain me.",
    "What's a small habit that actually improves your life?",
    # food & drink
    "How do I make a decent cup of coffee at home?",
    "What can I cook with just eggs, cheese, and bread?",
    "How do I stop my pasta from sticking together?",
    "Is it worth making my own bread?",
    "What's the secret to good roast potatoes?",
    "How do I know when steak is done without a thermometer?",
    "Recommend a comforting meal for a cold evening.",
    "What goes well with a Sunday roast?",
    "How much tea is too much tea?",
    "What's a good beginner cocktail to make at home?",
    # weather & seasons
    "It's grey and drizzly again. How do I stay cheerful?",
    "How should I dress for unpredictable weather?",
    "Why does it always seem to rain on weekends?",
    "What's the best way to dry a soaked coat quickly?",
    # travel & place
    "Any tips for a first-time visit to London?",
    "What should I pack for a rainy hiking trip?",
    "How do I survive a long-haul flight in economy?",
    "Is it rude to talk to strangers on public transport?",
    "What's a good way to spend a day in Edinburgh?",
    "How do I avoid looking like a tourist abroad?",
    # science & how things work
    "Why is the sky blue?",
    "How do noise-cancelling headphones work?",
    "What actually causes jet lag?",
    "Explain how vaccines work, simply.",
    "Why do onions make you cry?",
    "How does Wi-Fi actually reach my laptop?",
    "What makes bread rise?",
    "Why do we get goosebumps?",
    # practical how-to
    "How do I get a red wine stain out of a carpet?",
    "What's the right way to fold a fitted sheet?",
    "How do I unclog a slow drain without chemicals?",
    "How often should I actually water a succulent?",
    "How do I stop my glasses fogging up?",
    "What's the best way to sharpen a kitchen knife?",
    "How do I remove a stripped screw?",
    # money & work
    "How do I start budgeting without it being miserable?",
    "Is it worth buying coffee out every day?",
    "How do I ask for a raise without being awkward?",
    "What's a sensible way to save a little each month?",
    "How do I write a polite but firm email to a late-paying client?",
    # opinions & recommendations
    "Recommend a book for a long train journey.",
    "What's a film that's worth watching twice?",
    "Suggest a hobby I can start with almost no money.",
    "Is it better to read the book or watch the film first?",
    "What's an underrated board game for two people?",
    "Recommend a podcast for someone who likes history.",
    # health & wellbeing
    "How do I build a running habit from zero?",
    "What's a realistic way to drink more water?",
    "How do I stretch after sitting all day?",
    "Any tips for keeping warm without cranking the heating?",
    "How do I stop doomscrolling before bed?",
    # relationships & social
    "How do I make small talk without being awkward?",
    "What's a thoughtful, cheap gift for a friend?",
    "How do I politely leave a party early?",
    "How do I apologise properly after messing up?",
    # culture & curiosities
    "What's the story behind afternoon tea?",
    "Why do the British talk about the weather so much?",
    "What's the difference between ale and lager?",
    "Explain cricket to someone who's never seen it.",
    "What's a ceilidh and should I be nervous about one?",
    "Why is haggis a thing?",
]
