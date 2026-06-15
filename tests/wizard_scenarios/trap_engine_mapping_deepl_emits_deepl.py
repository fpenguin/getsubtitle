"""Trap: picking DeepL at the engine question must produce DeepL in
the emitted CLI/TOML. A past regression chose DeepL in the UI but
shipped Argos dependency hints downstream."""

from wizard_harness import Scenario

SCENARIO = Scenario(
    name="trap_engine_mapping_deepl_emits_deepl",
    files={},
    # Avoid the "no DeepL key" blocker by pre-seeding a fake key, so
    # the wizard doesn't trip the setup-recommend branch on save.
    keys={"deepl": "fake-key-for-test"},
    inputs=[
        "1,2,3,4",      # all four steps so translate Q fires
        "2",            # URL source
        "https://www.imdb.com/title/tt28299608/",
        "3",            # scope: auto
        "ja,en",
        "2",            # Q6 translate engine: DeepL
        "1",            # reading aids — skip
        "",             # format — accept recommended SRT
        "",             # font size — regular
        "4",            # action: save (URL default)
        "{TMP}/deepl-flow.toml",  # save filename
        "n",            # decline open folder
    ],
    expect_state={
        "mt_engine": "deepl",
    },
    expect_cli_contains=["--translate", "deepl"],
    expect_toml_contains=['engine = "deepl"'],
    expect_cli_lacks=["argos", "ollama"],
)
