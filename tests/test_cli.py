import json

from aiimagecheck import cli

from conftest import CAI, MADE


def test_text_report(capsys):
    assert cli.main([str(MADE / "ai-created.jpg")]) == 0
    out = capsys.readouterr()
    assert "Made with AI." in out.out
    assert "trust lists not downloaded" in out.err


def test_json_report(capsys):
    assert cli.main(["--json", str(MADE / "ai-edited.jpg"), str(CAI / "A.jpg")]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [d["verdict"] for d in data] == ["ai_edited", "no_evidence"]


def test_save_originals(tmp_path, capsys):
    assert cli.main([str(MADE / "ai-edited.jpg"), "--save-originals", str(tmp_path)]) == 0
    saved = list(tmp_path.glob("ai-edited.parentOf.*"))
    assert len(saved) == 1 and saved[0].read_bytes().startswith(b"\xff\xd8")


def test_missing_file_is_exit_1_and_others_still_checked(capsys):
    assert cli.main([str(CAI / "nope.jpg"), str(CAI / "A.jpg")]) == 1
    out = capsys.readouterr()
    assert "nope.jpg" in out.err and "No AI evidence" in out.out


def test_usage_errors_are_exit_2(capsys):
    assert cli.main([]) == 2
    assert cli.main(["serve", "--listen", "0.0.0.0:3103"]) == 2
    assert "not loopback" in capsys.readouterr().err
