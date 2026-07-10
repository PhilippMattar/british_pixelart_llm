from bpx.router.keywords import detect, hits


def test_detects_british():
    assert detect("You alright mate? Fancy a cuppa, innit") == "british"


def test_detects_scottish():
    assert detect("Aye, it's pure dreich the day, dinnae ye think") == "scottish"


def test_plain_text_no_match():
    assert detect("The weather is pleasant this afternoon.") is None


def test_checkmate_does_not_match_mate():
    # word boundaries: \bmate\b must not fire inside "checkmate"
    assert hits("I won the game with checkmate.")["british"] == 0
    assert detect("I won the game with checkmate.") is None


def test_whiskey_is_not_scottish_whisky():
    # Scottish "whisky" has no 'e'; the Irish/US "whiskey" must not match
    assert hits("I ordered an Irish whiskey.")["scottish"] == 0
    assert detect("I ordered an Irish whiskey.") is None


def test_place_name_does_not_trigger():
    # asking *about* Scotland shouldn't flip persona
    assert detect("What is the capital of Scotland?") is None


def test_equal_hits_is_ambiguous():
    # one british + one scottish keyword -> tie -> None
    assert hits("mate, aye") == {"british": 1, "scottish": 1}
    assert detect("mate, aye") is None


def test_case_insensitive():
    assert detect("INNIT bruv") == "british"
