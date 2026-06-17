from founder_bot.kb import load_kb


def test_loads_and_concatenates_known_files(tmp_path):
    (tmp_path / "profile.md").write_text("I am Souravh.")
    (tmp_path / "proof.md").write_text("Built Nexus.")
    (tmp_path / "reviews.md").write_text("Great engineer.")
    (tmp_path / "angles.md").write_text("Direct tone.")
    text = load_kb(str(tmp_path))
    assert "I am Souravh." in text
    assert "Built Nexus." in text
    assert "Great engineer." in text
    assert "Direct tone." in text
    # section headers present so the model can tell parts apart
    assert "# profile" in text
    assert "# proof" in text


def test_missing_files_are_skipped(tmp_path):
    (tmp_path / "profile.md").write_text("Only profile.")
    text = load_kb(str(tmp_path))
    assert "Only profile." in text
    assert "# proof" not in text


def test_local_file_overrides_template(tmp_path):
    (tmp_path / "profile.md").write_text("Template profile.")
    (tmp_path / "profile.local.md").write_text("Real private profile.")
    text = load_kb(str(tmp_path))
    assert "Real private profile." in text
    assert "Template profile." not in text
