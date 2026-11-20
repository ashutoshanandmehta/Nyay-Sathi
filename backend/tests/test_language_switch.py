from app.agent.runner import detect_message_language


def test_detect_hindi_devanagari():
    assert detect_message_language("बैंक ने मेरे पैसे रोक रखे हैं") == "hi"
    assert detect_message_language("सामान लौटाया, पर पैसे वापस नहीं मिले") == "hi"
    assert detect_message_language("उपभोक्ता फोरम में शिकायत कैसे दर्ज करें?") == "hi"


def test_detect_hinglish_latin():
    assert (
        detect_message_language(
            "Maine 3 hafte pehle earphones return kiye the, abhi tak refund nahi mila"
        )
        == "hinglish"
    )
    assert (
        detect_message_language("Bank se unauthorised transaction hua hai, kya karun?")
        == "hinglish"
    )
    assert (
        detect_message_language("Cyber crime portal par complaint kaise register karein?")
        == "hinglish"
    )
    assert detect_message_language("Mera paisa account se kat gaya") == "hinglish"
    assert (
        detect_message_language("Police station me FIR darj nahi kar rahe hain")
        == "hinglish"
    )


def test_detect_english():
    assert (
        detect_message_language(
            "The bank has withheld my ₹2,800 refund for three weeks"
        )
        == "en"
    )
    assert (
        detect_message_language("Please help me draft a consumer court complaint")
        == "en"
    )
    assert (
        detect_message_language(
            "What is the limitation period under Consumer Protection Act?"
        )
        == "en"
    )
    assert (
        detect_message_language("Can you write a complaint email to the seller?")
        == "en"
    )


def test_detect_ambiguous_short_input():
    assert detect_message_language("") is None
    assert detect_message_language("ok") is None
    assert detect_message_language("12345") is None
