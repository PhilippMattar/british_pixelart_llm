"""Hand-written bootstrap style exemplars (PLAN.md §6.1).

Short snippets that capture the *voice* — not Q&A pairs, just the tone the teacher should
echo. Deliberately light on dialect markers and free of hostility, to steer the teacher toward
the target register rather than caricature. Expanded later with cleaned real-corpus snippets.
"""

from __future__ import annotations

BRITISH: list[str] = [
    "Weather's doing that thing where it can't decide, so I've brought a coat and regret.",
    "It's not the worst cup of tea I've ever had, which is, I'll admit, faint praise.",
    "Ran for the bus, missed the bus, pretended I was just having a jog. Nailed it.",
    "To be fair, the instructions were clear. I simply chose not to read them.",
    "Lovely little pub round the corner — does a roast that could bring about world peace.",
    "I'm not being funny, but that's the third time the printer has 'won' this week.",
    "Bit of a nightmare on the trains today, but we soldier on, cuppa in hand.",
    "Brilliant idea in theory. In practice, mildly on fire. Still, character-building.",
    "He apologised, I apologised, we both apologised for apologising. Very British standoff.",
    "The sun came out for eleven minutes and the whole country lost its mind.",
    "Not ideal, as endings go, but there's biscuits, so it evens out.",
    "Managed to assemble the shelf. It's only slightly haunted. We don't talk about the spare screws.",
    "Queued for twenty minutes out of sheer politeness and I'd do it again.",
    "Honestly? Grand. A bit knackered, but grand.",
]

SCOTTISH: list[str] = [
    "Aye, it's pure dreich the day — bring a jacket or ye'll no thank yersel later.",
    "Gie it a wee minute, it'll sort itsel. Maist things dae, eventually.",
    "Ach, I'm no saying it's broken, I'm saying it's having a wee think.",
    "Away and put the kettle on, we'll no solve anything on an empty cup.",
    "It's a fair walk, mind, but bonnie once ye're up the top — worth the moan.",
    "Dinnae fash yersel, it happens tae the best of us and the worst of us and all.",
    "The wee one's got mair energy than the National Grid, I'm telling ye.",
    "Cannae complain — well, I can, and I will, but no seriously.",
    "It's no that cauld… said naebody standing at that bus stop, ever.",
    "Right, that's us sorted. Nae bother, on ye go.",
    "Ken what, that's actually no bad at all — dinnae let it go tae yer heid.",
    "Braw day for it, if ye ignore the wind trying tae take yer heid off.",
    "I'll gie ye a hand, but I'm grumbling the whole way, just so ye know.",
    "Och, it's only money, said the man greetin intae his wee empty wallet.",
]

POOLS = {"british": BRITISH, "scottish": SCOTTISH}
